"""Streaming recognition that works out the language for itself.

Buffers the opening audio, names the language from it, then hands every
later chunk to an ordinary streaming session pinned to that language --
so captions stay word-by-word live after the first moment.

The pinning is not permanent. Google's streaming models transcribe one
language per stream: given several language codes they pick one and drop
the rest, so a speaker who switches language mid-session cannot be
followed by a single stream. What they can be followed by is the
recogniser's own confidence, which collapses when the audio stops
matching the language it was told to expect -- measured at 0.93 to 0.99
on matching speech against 0.03 to 0.13 on mismatched. A final that far
down is the cue to work the language out again and, if it really has
changed, open a fresh stream and replay the audio that was misheard.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import time
from collections import deque
from collections.abc import AsyncIterator

from app.config import CHANNELS, SAMPLE_RATE_HZ, Settings
from app.stt.base import SttResult, SttStream
from app.stt.detect import detect_language

logger = logging.getLogger(__name__)

# Three seconds, not two. Measured across all eleven supported languages,
# two seconds identified ten of them but read Arabic as Hindi; three
# identified every one. The extra second is paid once per session, not per
# sentence.
DETECT_SECONDS = 3.0
_BYTES_PER_SAMPLE = 2
_BYTES_PER_SECOND = SAMPLE_RATE_HZ * CHANNELS * _BYTES_PER_SAMPLE
_DETECT_BYTES = int(DETECT_SECONDS * _BYTES_PER_SECOND)

# Google rejects a streaming chunk over 25 600 bytes, so a buffer cannot be
# replayed in one push. 3 200 bytes is the 100 ms chunk the widget already
# sends, which keeps a replay indistinguishable from live audio.
_REPLAY_CHUNK_BYTES = 3_200

# Enough recent audio to re-detect from, with a little margin so a switch
# is judged on the new language rather than the tail of the old one.
_RECENT_BYTES = int((DETECT_SECONDS + 1.0) * _BYTES_PER_SECOND)

# Well below the confidence of correctly matched speech and well above
# mismatched speech, so neither case lands near the line.
LOW_CONFIDENCE = 0.5

# A wrong-language stretch produces several poor finals in a row. Checking
# on every one would mean a detection call per sentence, so they are rate
# limited; the first check happens immediately.
RECHECK_INTERVAL_SECONDS = 8.0


class AutoDetectSttStream(SttStream):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pending = bytearray()
        self._recent: deque[bytes] = deque()
        self._recent_bytes = 0
        self._delegate: SttStream | None = None
        self._ready = asyncio.Event()
        self._out: asyncio.Queue[SttResult | None] = asyncio.Queue()
        self._pump: asyncio.Task[None] | None = None
        self._closing = False
        self._last_check = 0.0
        self.language: str | None = None

    # --- the SttStream interface --------------------------------------

    async def push(self, pcm: bytes) -> None:
        self._remember(pcm)
        if self._delegate is not None:
            await self._delegate.push(pcm)
            return
        self._pending.extend(pcm)
        if len(self._pending) >= _DETECT_BYTES:
            await self._begin()

    async def close(self) -> None:
        self._closing = True
        if self._delegate is None:
            if self._pending:
                await self._begin()
            else:
                # Nothing was ever spoken; there is no session to close.
                self._ready.set()
                await self._out.put(None)
        if self._delegate is not None:
            await self._delegate.close()
        if self._pump is not None:
            with contextlib.suppress(Exception):
                await self._pump

    async def results(self) -> AsyncIterator[SttResult]:
        await self._ready.wait()
        while True:
            item = await self._out.get()
            if item is None:
                return
            yield item

    # --- audio kept for a second opinion ------------------------------

    def _remember(self, pcm: bytes) -> None:
        self._recent.append(pcm)
        self._recent_bytes += len(pcm)
        while self._recent_bytes > _RECENT_BYTES and len(self._recent) > 1:
            self._recent_bytes -= len(self._recent.popleft())

    def _recent_audio(self) -> bytes:
        return b"".join(self._recent)

    # --- starting, and starting again ---------------------------------

    async def _begin(self) -> None:
        """Name the language, open the real stream, replay what was buffered."""
        buffered = bytes(self._pending)
        self._pending.clear()

        detected: str | None = None
        try:
            detected = await detect_language(buffered, self._settings)
        except Exception:
            # Detection is a convenience, not the feature. Falling back to
            # the configured language beats failing the whole session.
            logger.exception("language detection failed; using STT_LANGUAGE")

        self.language = detected or self._settings.stt_language
        logger.info("caption language: %s (detected=%s)", self.language, detected)

        self._delegate = self._open(self.language)
        self._ready.set()
        self._pump = asyncio.create_task(self._forward())
        await self._replay(buffered)

    def _open(self, language: str) -> SttStream:
        from app.stt.google_v2 import GoogleSttStream

        return GoogleSttStream(
            dataclasses.replace(self._settings, stt_language=language)
        )

    async def _replay(self, audio: bytes) -> None:
        delegate = self._delegate
        if delegate is None:
            return
        for start in range(0, len(audio), _REPLAY_CHUNK_BYTES):
            await delegate.push(audio[start : start + _REPLAY_CHUNK_BYTES])

    async def _forward(self) -> None:
        """Pump the delegate's results out, swapping it if the language changed."""
        try:
            while True:
                delegate = self._delegate
                if delegate is None:
                    return
                switch_to: str | None = None
                results = delegate.results()
                try:
                    async for result in results:
                        await self._out.put(
                            dataclasses.replace(result, language=self.language)
                        )
                        switch_to = await self._language_now(result)
                        if switch_to is not None:
                            break
                finally:
                    with contextlib.suppress(Exception):
                        await results.aclose()
                if switch_to is None:
                    return
                await self._swap(switch_to)
        finally:
            await self._out.put(None)

    async def _language_now(self, result: SttResult) -> str | None:
        """The language the speaker has moved to, or None to carry on."""
        if self._closing or not result.is_final:
            return None
        if result.confidence is None or result.confidence >= LOW_CONFIDENCE:
            return None

        now = time.monotonic()
        if self._last_check and now - self._last_check < RECHECK_INTERVAL_SECONDS:
            return None
        self._last_check = now

        audio = self._recent_audio()
        if len(audio) < _DETECT_BYTES:
            return None

        try:
            detected = await detect_language(audio, self._settings)
        except Exception:
            logger.exception("re-detection failed; staying on %s", self.language)
            return None

        # A poor result in the language already in use means the audio was
        # unclear, not that the speaker switched.
        if detected is None or detected == self.language:
            return None
        return detected

    async def _swap(self, language: str) -> None:
        """Move to a new language without dropping the audio in flight."""
        logger.info("caption language changed: %s -> %s", self.language, language)
        previous = self._delegate
        audio = self._recent_audio()

        self.language = language
        # Replaced before the old one is closed, so a chunk arriving from
        # the receive loop mid-swap always has somewhere to go.
        self._delegate = self._open(language)
        await self._replay(audio)

        if previous is not None:
            with contextlib.suppress(Exception):
                await previous.close()
