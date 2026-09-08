"""Caption session endpoints (Plan.md section 4).

Captioning does not require an account. Starting a session while signed
out returns an id and writes nothing: there is no row, so backend-ws finds
none and does not persist the transcript. Nobody's speech is kept unless
they asked for an account, and the widget's "Save as text file" is how an
anonymous user keeps their own copy.

Signing in is what turns saving on. From then on a session is a row, its
confirmed lines are written by backend-ws, and these endpoints can hand
the log back.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.auth.dependencies import CurrentUser, CurrentUserOrNone, Db
from app.db.models import CaptionSession

router = APIRouter(prefix="/api/caption-sessions", tags=["caption-sessions"])

AudioSource = Literal["mic", "tab_audio"]

# Someone else's session is not found rather than forbidden: answering
# "forbidden" would confirm that the id exists.
_NOT_FOUND = "No such caption session."


# --- bodies -----------------------------------------------------------


class CreateCaptionSessionRequest(BaseModel):
    audio_source: AudioSource


class CreateCaptionSessionResponse(BaseModel):
    session_id: str
    # False while signed out, so the widget can say plainly that this
    # transcript is not being kept anywhere.
    saved: bool


class CaptionLineResponse(BaseModel):
    seq: int
    text: str
    created_at: datetime


class CaptionSessionSummary(BaseModel):
    id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None
    language: str | None
    audio_source: str


class CaptionSessionDetail(CaptionSessionSummary):
    lines: list[CaptionLineResponse]


# --- endpoints --------------------------------------------------------


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=CreateCaptionSessionResponse
)
async def create_caption_session(
    db: Db, user: CurrentUserOrNone, payload: CreateCaptionSessionRequest
) -> CreateCaptionSessionResponse:
    """Start a session (Plan.md section 4).

    Signed out this is only an id: backend-ws needs one to key the stream,
    but with no row behind it there is nowhere for a transcript to go.
    """
    if user is None:
        return CreateCaptionSessionResponse(session_id=str(uuid.uuid4()), saved=False)

    session = CaptionSession(user_id=user.id, audio_source=payload.audio_source)
    db.add(session)
    await db.flush()
    return CreateCaptionSessionResponse(session_id=str(session.id), saved=True)


@router.get("", response_model=list[CaptionSessionSummary])
async def list_caption_sessions(
    db: Db, user: CurrentUser
) -> list[CaptionSessionSummary]:
    """List my sessions, most recent first."""
    rows = (
        await db.scalars(
            select(CaptionSession)
            .where(CaptionSession.user_id == user.id)
            .order_by(CaptionSession.started_at.desc())
        )
    ).all()
    return [
        CaptionSessionSummary.model_validate(row, from_attributes=True) for row in rows
    ]


@router.get("/{session_id}", response_model=CaptionSessionDetail)
async def get_caption_session(
    db: Db, user: CurrentUser, session_id: uuid.UUID
) -> CaptionSessionDetail:
    """Get a session's caption log."""
    session = await db.scalar(
        select(CaptionSession)
        .where(CaptionSession.id == session_id, CaptionSession.user_id == user.id)
        .options(selectinload(CaptionSession.lines))
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)

    return CaptionSessionDetail(
        id=session.id,
        started_at=session.started_at,
        ended_at=session.ended_at,
        language=session.language,
        audio_source=session.audio_source,
        lines=[
            CaptionLineResponse(
                seq=line.seq, text=line.text, created_at=line.created_at
            )
            for line in session.lines
        ],
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_caption_session(
    db: Db, user: CurrentUser, session_id: uuid.UUID
) -> None:
    """Delete a session and its lines."""
    result = await db.execute(
        delete(CaptionSession).where(
            CaptionSession.id == session_id, CaptionSession.user_id == user.id
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
