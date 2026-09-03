"""The WebSocket message set from Plan.md section 5.

This module is the single place the wire format is defined. The five
message types below are the ones in the spec; `caption.language` is the
one field added since, for automatic language detection.
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


ClientMessage = Annotated[
    Union[AudioChunkMessage, EndStreamMessage],
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
