"""Carrying a caption session across the end of a recognition stream.

Google's streaming recognition does not run forever -- a stream is capped
at a few minutes -- and this app exists to caption lectures, which are
longer than that. Before this, the end of a stream ended the session: if
it raised, the socket closed mid-sentence; if it simply finished, the
forwarding task ran out and captions stopped with no error and no
explanation, which is worse.

So the stream is not the session. This wraps one and opens another when it
ends early, replaying the last couple of seconds of audio into the new one
so that a sentence spoken across the seam is not lost. The listener sees a
short gap; they do not see the session die.

Reopening is bounded. A recogniser that fails instantly every time is
broken rather than busy, and retrying it forever would hide that behind a
stream of empty captions.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import AsyncIterator, Callable

from app.config import CHANNELS, SAMPLE_RATE_HZ
from app.stt.base import SttResult, SttStream

logger = logging.getLogger(__name__)

_BYTES_PER_SECOND = SAMPLE_RATE_HZ * CHANNELS * 2

# Two seconds of audio, replayed into the replacement stream. Enough to
# carry a word that straddled the seam, short enough not to repeat a whole
# sentence the listener has already read.
REPLAY_SECONDS = 2.0
_RECENT_BYTES = int(REPLAY_SECONDS * _BYTES_PER_SECOND)

# Google rejects a request carrying more than 25,600 bytes of audio, so
# the replay goes in chunks the size the client already sends. Learned in
# Sprint 1 by having a replay rejected for being one buffer too big.
_REPLAY_CHUNK_BYTES = 3_200

# A stream that ends immediately, repeatedly, is not going to start
# working. Past this the session gives up and says so.
MAX_REOPENS = 5


class ResilientSttStream(SttStream):
    """One session's recognition, across however many streams it takes."""

    def __init__(self, open_stream: Callable[[], SttStream]) -> None:
        self._open_stream = open_stream
        self._inner: SttStream = open_stream()
        self._closed = False
        self._reopens = 0
        self._recent: deque[bytes] = deque()
        self._recent_bytes = 0

    async def push(self, pcm: bytes) -> None:
        self._remember(pcm)
        await self._inner.push(pcm)

    def _remember(self, pcm: bytes) -> None:
        self._recent.append(pcm)
        self._recent_bytes += len(pcm)
        # Trim to a full window rather than below it, so what is replayed
        # is always at least REPLAY_SECONDS long.
        while (
            len(self._recent) > 1
            and self._recent_bytes - len(self._recent[0]) >= _RECENT_BYTES
        ):
            self._recent_bytes -= len(self._recent.popleft())

    async def results(self) -> AsyncIterator[SttResult]:
        while True:
            ended_early = False
            try:
                async for result in self._inner.results():
                    yield result
            except Exception:
                if self._closed:
                    # Ending during a close is the close working.
                    return
                logger.exception("recognition stream failed; opening another")
                ended_early = True
            else:
                # A stream that finishes on its own has either been closed
                # by us -- which is the end of the session -- or hit the
                # service's own duration limit, which is not.
                ended_early = not self._closed

            if self._closed or not ended_early:
                return
            if not await self._reopen():
                return

    async def _reopen(self) -> bool:
        """Swap in a fresh stream and replay the recent audio. False to stop."""
        if self._reopens >= MAX_REOPENS:
            logger.error(
                "recognition stream ended %s times; giving up on this session",
                self._reopens,
            )
            return False
        self._reopens += 1
        logger.info("reopening recognition stream (%s)", self._reopens)

        try:
            await self._inner.close()
        except Exception:
            # The old stream is being discarded; how it took that is not
            # worth ending the session over.
            logger.debug("closing the old stream raised", exc_info=True)

        self._inner = self._open_stream()
        audio = b"".join(self._recent)
        for start in range(0, len(audio), _REPLAY_CHUNK_BYTES):
            await self._inner.push(audio[start : start + _REPLAY_CHUNK_BYTES])
        return True

    async def close(self) -> None:
        self._closed = True
        await self._inner.close()
