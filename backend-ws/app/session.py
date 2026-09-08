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
    AuthMessage,
    CaptionMessage,
    EndStreamMessage,
    ErrorMessage,
    StreamEndedMessage,
    client_message_adapter,
)
from app.store import CaptionStore
from app.stt.base import SttStream
from app.tokens import InvalidToken, read_access_token

logger = logging.getLogger(__name__)

_UNRECOGNISED = "Unrecognised message; expected audio_chunk or end_stream."
_BAD_TOKEN = "Your sign-in has expired. Sign in again and restart captions."
_LATE_AUTH = "auth must be the first message; this stream has already begun."

# Policy-violation close code, for a stream that claimed an identity it
# could not prove.
WS_POLICY_VIOLATION = 1008


class CaptionStreamSession:
    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        stt: SttStream,
        store: CaptionStore | None = None,
        jwt_secret: str = "",
    ) -> None:
        self._websocket = websocket
        self._session_id = session_id
        self._stt = stt
        self._jwt_secret = jwt_secret
        # Absent when captions are not being saved, which is the ordinary
        # case: only a signed-in listener's session has a row to write to.
        self._store = store
        self._language: str | None = None
        # Caption line ordinal, shared by every interim result for the
        # line being formed and incremented once it is confirmed. See
        # docs/sprint-1.md for why caption.seq is read this way.
        self._line_seq = 0
        self._failed = False

    async def run(self) -> None:
        # Started before the handshake, so a recogniser that is unavailable
        # says so at once rather than after the listener has spoken. It
        # cannot outrun the handshake: results come only from pushed audio,
        # and no audio is pushed until the receive loop is running.
        forward = asyncio.create_task(self._forward_captions())

        # Who is speaking has to be settled before anything can be written,
        # so the first frame is read here rather than in the receive loop.
        # A stream that sends no auth is anonymous, which is the ordinary
        # case and needs no ceremony.
        try:
            first = await self._receive_message()
        except WebSocketDisconnect:
            await self._abandon(forward)
            return

        user_id: str | None = None
        if isinstance(first, AuthMessage):
            try:
                user_id = read_access_token(first.token, self._jwt_secret)
            except InvalidToken as error:
                # Loud, not silent. Someone who believes they are signed in
                # would otherwise caption for ten minutes, find nothing
                # saved, and never learn why.
                logger.info(
                    "caption session %s: rejecting token (%s)", self._session_id, error
                )
                await self._abandon(forward)
                await self._send(ErrorMessage(message=_BAD_TOKEN))
                with contextlib.suppress(RuntimeError):
                    await self._websocket.close(code=WS_POLICY_VIOLATION)
                return
            first = None

        if self._store is not None:
            await self._store.open(user_id)
        try:
            await self._receive_loop(first)
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

        if self._store is not None:
            await self._store.finish(self._language)

        await self._send(StreamEndedMessage(session_id=self._session_id))
        with contextlib.suppress(RuntimeError):
            await self._websocket.close()

    async def _receive_message(self):
        """One frame, or None when it was not a message we know."""
        raw = await self._websocket.receive_text()
        try:
            return client_message_adapter.validate_json(raw)
        except ValidationError:
            # A malformed frame is the client's problem, not a reason to
            # tear down a working audio stream.
            await self._send(ErrorMessage(message=_UNRECOGNISED))
            return None

    async def _receive_loop(self, pending=None) -> None:
        """`pending` is the opening frame, when it was not an auth frame."""
        message = pending
        while True:
            if message is not None:
                if isinstance(message, EndStreamMessage):
                    return
                if isinstance(message, AuthMessage):
                    # Identity is settled before the first chunk and never
                    # changes hands mid-stream.
                    await self._send(ErrorMessage(message=_LATE_AUTH))
                else:
                    await self._handle_audio_chunk(message)
            message = await self._receive_message()

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
                if result.language:
                    self._language = result.language
                if result.is_final:
                    # Only confirmed sentences are written down
                    # (Plan.md section 5); interim text is still being revised.
                    if self._store is not None:
                        await self._store.add_line(self._line_seq, result.text)
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
