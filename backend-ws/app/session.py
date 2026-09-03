"""Bridges one WebSocket connection to one STT stream.

Receiving audio and emitting captions run as separate tasks: a streaming
recogniser answers on its own schedule, so the receive loop must never
block waiting for a result.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import logging

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.protocol import (
    AudioChunkMessage,
    CaptionMessage,
    EndStreamMessage,
    ErrorMessage,
    StreamEndedMessage,
    client_message_adapter,
)
from app.stt.base import SttStream

logger = logging.getLogger(__name__)

_UNRECOGNISED = "Unrecognised message; expected audio_chunk or end_stream."


class CaptionStreamSession:
    def __init__(
        self, websocket: WebSocket, session_id: str, stt: SttStream
    ) -> None:
        self._websocket = websocket
        self._session_id = session_id
        self._stt = stt
        # Caption line ordinal, shared by every interim result for the
        # line being formed and incremented once it is confirmed. See
        # docs/sprint-1.md for why caption.seq is read this way.
        self._line_seq = 0
        self._failed = False

    async def run(self) -> None:
        forward = asyncio.create_task(self._forward_captions())
        try:
            await self._receive_loop()
        except WebSocketDisconnect:
            await self._abandon(forward)
            return
        except Exception:
            logger.exception("caption session %s failed while receiving", self._session_id)
            await self._abandon(forward)
            await self._fail("The caption stream stopped unexpectedly.")
            return

        # The client sent end_stream: flush the recogniser, let the
        # forwarder drain the last captions, then acknowledge.
        try:
            await self._stt.close()
            await forward
        except Exception:
            logger.exception("caption session %s failed while draining", self._session_id)
            await self._fail("Speech recognition stopped unexpectedly.")
            return

        await self._send(StreamEndedMessage(session_id=self._session_id))
        with contextlib.suppress(RuntimeError):
            await self._websocket.close()

    async def _receive_loop(self) -> None:
        while True:
            raw = await self._websocket.receive_text()
            try:
                message = client_message_adapter.validate_json(raw)
            except ValidationError:
                # A malformed frame is the client's problem, not a reason
                # to tear down a working audio stream.
                await self._send(ErrorMessage(message=_UNRECOGNISED))
                continue

            if isinstance(message, EndStreamMessage):
                return
            await self._handle_audio_chunk(message)

    async def _handle_audio_chunk(self, message: AudioChunkMessage) -> None:
        try:
            pcm = base64.b64decode(message.data, validate=True)
        except (binascii.Error, ValueError):
            await self._send(
                ErrorMessage(
                    message=f"audio_chunk seq {message.seq} was not valid base64."
                )
            )
            return
        await self._stt.push(pcm)

    async def _forward_captions(self) -> None:
        try:
            async for result in self._stt.results():
                await self._send(
                    CaptionMessage(
                        text=result.text,
                        is_final=result.is_final,
                        seq=self._line_seq,
                        language=result.language,
                    )
                )
                if result.is_final:
                    self._line_seq += 1
        except Exception:
            # Surface it now: the receive loop is blocked on the socket and
            # would not notice until the client happened to stop talking.
            logger.exception(
                "caption session %s: recognition failed", self._session_id
            )
            await self._fail("Speech recognition stopped unexpectedly.")
            raise

    async def _abandon(self, forward: asyncio.Task[None]) -> None:
        forward.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await forward
        with contextlib.suppress(Exception):
            await self._stt.close()

    async def _fail(self, message: str) -> None:
        if self._failed:
            return
        self._failed = True
        # Sprint 5 adds retry and fallback; for now one error, then close.
        with contextlib.suppress(Exception):
            await self._send(ErrorMessage(message=message))
        with contextlib.suppress(Exception):
            await self._websocket.close()

    async def _send(self, message: CaptionMessage | ErrorMessage | StreamEndedMessage) -> None:
        await self._websocket.send_text(message.model_dump_json())
