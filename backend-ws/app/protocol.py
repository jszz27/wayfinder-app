"""The WebSocket message set from Plan.md section 5.

This module is the single place the wire format is defined. Five of the
message types below are the ones in the spec; `caption.language` and the
`auth` frame were added since -- for automatic language detection, and for
proving who a stream belongs to. Both are recorded in Plan.md section 5.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter

AudioSource = Literal["mic", "tab_audio"]


# --- client -> server ------------------------------------------------


class AudioChunkMessage(BaseModel):
    type: Literal["audio_chunk"]
    data: str
    seq: int
    source: AudioSource


class EndStreamMessage(BaseModel):
    type: Literal["end_stream"]


class AuthMessage(BaseModel):
    """Who this stream belongs to (Plan.md section 5, added in Sprint 3).

    Optional, and only meaningful as the very first frame. The token
    travels in a message rather than the query string because a query
    string is written to every access log; a message body is not.
    """

    type: Literal["auth"]
    token: str


ClientMessage = Annotated[
    Union[AudioChunkMessage, EndStreamMessage, AuthMessage],
    Field(discriminator="type"),
]

client_message_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


# --- server -> client ------------------------------------------------


class CaptionMessage(BaseModel):
    type: Literal["caption"] = "caption"
    text: str
    is_final: bool
    seq: int
    # Added after Sprint 1 for automatic language detection: the tag the
    # text was recognised as, or null when the language was configured
    # rather than detected. See Plan.md section 5.
    language: str | None = None


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    message: str


class StreamEndedMessage(BaseModel):
    type: Literal["stream_ended"] = "stream_ended"
    session_id: str


ServerMessage = Union[CaptionMessage, ErrorMessage, StreamEndedMessage]
