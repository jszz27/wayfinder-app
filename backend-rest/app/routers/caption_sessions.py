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
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
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
    # Null until renamed; the interface shows the date instead.
    title: str | None
    # True when the text has been edited or saved by hand, so the interface
    # can be honest that it is no longer purely what was recognised.
    edited: bool


class CaptionSessionDetail(CaptionSessionSummary):
    # What to show: the kept text if there is one, otherwise the recognised
    # lines joined. Callers wanting the machine's own words can still read
    # `lines`, which is never rewritten.
    text: str
    lines: list[CaptionLineResponse]


class SaveTranscriptRequest(BaseModel):
    """A transcript the widget was holding, saved on request.

    Used when auto-save is off: with no session row, backend-ws wrote
    nothing, so the text exists only in the browser until this arrives.
    """

    audio_source: AudioSource
    text: str = Field(min_length=1, max_length=200_000)
    title: str | None = Field(default=None, max_length=120)


class UpdateCaptionSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    text: str | None = Field(default=None, max_length=200_000)


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
    return [_summary(row) for row in rows]


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
        title=session.title,
        edited=session.edited_text is not None,
        text=_readable_text(session),
        lines=[
            CaptionLineResponse(
                seq=line.seq, text=line.text, created_at=line.created_at
            )
            for line in session.lines
        ],
    )


def _summary(row: CaptionSession) -> CaptionSessionSummary:
    return CaptionSessionSummary(
        id=row.id,
        started_at=row.started_at,
        ended_at=row.ended_at,
        language=row.language,
        audio_source=row.audio_source,
        title=row.title,
        edited=row.edited_text is not None,
    )


def _readable_text(session: CaptionSession) -> str:
    """What the person kept, or failing that what the recogniser heard."""
    if session.edited_text is not None:
        return session.edited_text
    return "\n".join(line.text for line in session.lines)


@router.post(
    "/saved", status_code=status.HTTP_201_CREATED, response_model=CaptionSessionSummary
)
async def save_transcript(
    db: Db, user: CurrentUser, payload: SaveTranscriptRequest
) -> CaptionSessionSummary:
    """Keep a transcript the widget was holding.

    This is the one place the server stores words it did not hear itself,
    so the text lands in `edited_text` rather than in `caption_lines`. The
    lines table stays what a recogniser produced, and nothing else.
    """
    session = CaptionSession(
        user_id=user.id,
        audio_source=payload.audio_source,
        title=(payload.title or None),
        edited_text=payload.text,
        # Saved after the fact, so it was over before it was kept.
        ended_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.flush()
    return _summary(session)


@router.patch("/{session_id}", response_model=CaptionSessionSummary)
async def update_caption_session(
    db: Db,
    user: CurrentUser,
    session_id: uuid.UUID,
    payload: UpdateCaptionSessionRequest,
) -> CaptionSessionSummary:
    """Rename a session, or keep an edited version of its text.

    Partial in the real sense: only the fields actually sent are touched,
    so renaming cannot quietly discard an edit, and editing cannot quietly
    discard a name.
    """
    session = await db.scalar(
        select(CaptionSession).where(
            CaptionSession.id == session_id, CaptionSession.user_id == user.id
        )
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)

    sent = payload.model_dump(exclude_unset=True)
    if not sent:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Send a title or some text."
        )
    if "title" in sent:
        title = (payload.title or "").strip()
        # An empty name is not a name: it goes back to being shown by date.
        session.title = title or None
    if "text" in sent:
        if payload.text is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "text cannot be cleared; delete the session instead.",
            )
        session.edited_text = payload.text

    await db.flush()
    return _summary(session)


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
