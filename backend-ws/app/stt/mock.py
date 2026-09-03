"""A credential-free STT adapter.

It produces the same interim-then-final shape a real provider does, so
the widget, the WebSocket layer, and the caption UI can all be exercised
end to end without a cloud account.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.stt.base import SttResult, SttStream

# One canned utterance, revealed a piece at a time so the widget's
# "interim text keeps getting rewritten, then freezes" behaviour is
# visible. The last element is the confirmed sentence.
_UTTERANCE = (
    "오늘 회의는",
    "오늘 회의는 세 시에",
    "오늘 회의는 세 시에 시작합니다.",
)

# ~100 ms per chunk, so a result roughly every 300 ms.
CHUNKS_PER_RESULT = 3


class _Sentinel:
    """Marks the end of the result queue."""


class MockSttStream(SttStream):
    def __init__(self) -> None:
        self._queue: asyncio.Queue[SttResult | _Sentinel] = asyncio.Queue()
        self._chunks = 0
        self._results_emitted = 0
        self._line_open = False
        self._closed = False

    async def push(self, pcm: bytes) -> None:
        if self._closed:
            return
        self._chunks += 1
        if self._chunks % CHUNKS_PER_RESULT:
            return

        step = self._results_emitted % len(_UTTERANCE)
        is_final = step == len(_UTTERANCE) - 1
        self._results_emitted += 1
        self._line_open = not is_final
        await self._queue.put(SttResult(text=_UTTERANCE[step], is_final=is_final))

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # A real provider flushes whatever it was still forming when the
        # audio stops; mirror that so no caption line is left unconfirmed.
        if self._line_open:
            self._line_open = False
            await self._queue.put(SttResult(text=_UTTERANCE[-1], is_final=True))
        await self._queue.put(_Sentinel())

    async def results(self) -> AsyncIterator[SttResult]:
        while True:
            item = await self._queue.get()
            if isinstance(item, _Sentinel):
                return
            yield item
