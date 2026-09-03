"""Caption session endpoints (Plan.md section 4).

Sprint 1 implements only session creation, and holds sessions in memory.
Retrieval, listing, and deletion arrive in Sprint 3 alongside PostgreSQL;
see docs/sprint-1.md.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel

router = APIRouter(prefix="/api/caption-sessions", tags=["caption-sessions"])

AudioSource = Literal["mic", "tab_audio"]


@dataclass
class CaptionSession:
    """In-memory stand-in for the `caption_sessions` row of Plan.md section 6."""

    id: str
    audio_source: AudioSource
    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# Process-local, deliberately: this disappears on restart and is replaced
# by PostgreSQL in Sprint 3.
_sessions: dict[str, CaptionSession] = {}


class CreateCaptionSessionRequest(BaseModel):
    audio_source: AudioSource


class CreateCaptionSessionResponse(BaseModel):
    session_id: str


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateCaptionSessionResponse,
)
def create_caption_session(
    payload: CreateCaptionSessionRequest,
) -> CreateCaptionSessionResponse:
    """Start a caption session and hand back the id the widget puts on the
    WebSocket query string (Plan.md section 5)."""
    session = CaptionSession(id=str(uuid.uuid4()), audio_source=payload.audio_source)
    _sessions[session.id] = session
    return CreateCaptionSessionResponse(session_id=session.id)


def get_session(session_id: str) -> CaptionSession | None:
    """Read access for tests; the retrieval endpoints land in Sprint 3."""
    return _sessions.get(session_id)


def reset_sessions() -> None:
    """Clear the store so tests do not leak state into each other."""
    _sessions.clear()
