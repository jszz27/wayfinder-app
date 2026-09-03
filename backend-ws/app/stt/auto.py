"""Streaming recognition that works out the language for itself.

Buffers the opening audio, names the language from it once, then hands
every later chunk to an ordinary streaming session pinned to that
language -- so captions stay word-by-word live after the first moment.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import AsyncIterator

from app.config import CHANNELS, SAMPLE_RATE_HZ, Settings
from app.stt.base import SttResult, SttStream
from app.stt.detect import detect_language

logger = logging.getLogger(__name__)

# Two seconds is enough for chirp_2 to name a language and short enough
# that the wait is not felt as the caption being broken.
DETECT_SECONDS = 2.0
_BYTES_PER_SAMPLE = 2
_DETECT_BYTES = int(DETECT_SECONDS * SAMPLE_RATE_HZ * CHANNELS * _BYTES_PER_SAMPLE)

# Google rejects a streaming chunk over 25 600 bytes, so the buffer cannot
# be replayed in one push. 3 200 bytes is the 100 ms chunk the widget
# already sends, which keeps the replay indistinguishable from live audio.
_REPLAY_CHUNK_BYTES = 3_200


class AutoDetectSttStream(SttStream):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pending = bytearray()
        self._delegate: SttStream | None = None
        self._ready = asyncio.Event()
        self.language: str | None = None

    async def push(self, pcm: bytes) -> None:
        if self._delegate is not None:
            await self._delegate.push(pcm)
            return
        self._pending.extend(pcm)
        if len(self._pending) >= _DETECT_BYTES:
            await self._begin()

    async def close(self) -> None:
        if self._delegate is None:
            if self._pending:
                await self._begin()
            else:
                # Nothing was ever spoken; there is no session to close.
                self._ready.set()
        if self._delegate is not None:
            await self._delegate.close()

    async def results(self) -> AsyncIterator[SttResult]:
        await self._ready.wait()
        if self._delegate is None:
            return
        async for result in self._delegate.results():
            yield dataclasses.replace(result, language=self.language)

    async def _begin(self) -> None:
        """Name the language, open the real stream, replay what was buffered."""
        from app.stt.google_v2 import GoogleSttStream

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

        self._delegate = GoogleSttStream(
            dataclasses.replace(self._settings, stt_language=self.language)
        )
        self._ready.set()
        for start in range(0, len(buffered), _REPLAY_CHUNK_BYTES):
            await self._delegate.push(buffered[start : start + _REPLAY_CHUNK_BYTES])
