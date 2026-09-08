"""Digital guide mode endpoints (Plan.md section 4).

Like captioning, guide mode works with no account. Unlike captioning, the
conversation cannot be entirely stateless: the model needs the earlier
turns to answer a follow-up, so an anonymous conversation is held in this
process for as long as it lasts and then forgotten. Nothing about it
reaches the database, and it does not survive a restart.

A signed-in conversation is rows, and can be read back later.

Plan.md section 10 is the reason the screenshot never reaches storage on
either path: it is decoded, passed to the model for that one question, and
dropped. Only the text of both turns is kept.
"""

from __future__ import annotations

import base64
import binascii
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.auth.dependencies import CurrentUser, CurrentUserOrNone, Db
from app.config import get_settings
from app.db.models import GuideMessage, GuideSession
from app.guide.base import GuideTurn
from app.guide.factory import create_guide_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/guide/sessions", tags=["guide"])

Role = Literal["user", "assistant"]

# A downscaled screenshot is tens of kilobytes; this only exists to stop a
# full-resolution capture from becoming an unbounded request body.
MAX_SCREENSHOT_BYTES = 4 * 1024 * 1024

_SUPPORTED_IMAGE_MIME = {"image/png", "image/jpeg", "image/webp"}
_NOT_FOUND = "No such guide session."


# --- anonymous conversations ------------------------------------------


@dataclass
class _Turn:
    id: str
    role: Role
    content: str
    created_at: datetime


@dataclass
class _Anonymous:
    """A conversation with nobody's name on it, kept only in this process.

    Also how a signed-in conversation is held while auto-save is off: the
    account exists, but this conversation is not part of it until the
    person says so. Either way nothing here reaches a table, and it does
    not survive a restart.
    """

    id: str
    started_at: datetime
    completed_at: datetime | None = None
    messages: list[_Turn] = field(default_factory=list)
    # Set once this conversation has been kept, so saving again adds the
    # turns since rather than writing a second copy of the whole thing.
    saved_as: uuid.UUID | None = None
    saved_turns: int = 0


_anonymous: dict[str, _Anonymous] = {}


def reset_sessions() -> None:
    """Clear the in-process conversations so tests do not leak into each other."""
    _anonymous.clear()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- request and response bodies --------------------------------------


class CreateGuideSessionResponse(BaseModel):
    session_id: str
    # False while signed out, so the widget can say plainly that this
    # conversation is not being kept.
    saved: bool


class RenameGuideSessionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class SendGuideMessageRequest(BaseModel):
    """Plan.md section 4: the text question plus an optional screenshot."""

    content: str = Field(min_length=1, max_length=4000)
    screenshot: str | None = None


class GuideMessageResponse(BaseModel):
    id: str
    role: Role
    content: str
    created_at: datetime


class GuideSessionResponse(BaseModel):
    id: str
    started_at: datetime
    completed_at: datetime | None
    messages: list[GuideMessageResponse]


class GuideSessionSummary(BaseModel):
    """One conversation as it appears in a list.

    `opening` is the first thing the person asked. A conversation has no
    name and nobody would want to give one to "how do I send money?", so
    the question itself is what makes one recognisable a week later.
    """

    id: str
    started_at: datetime
    completed_at: datetime | None
    title: str | None
    opening: str | None
    exchanges: int


# --- screenshot -------------------------------------------------------


def decode_screenshot(raw: str) -> tuple[bytes, str]:
    """Turn the request's base64 string into bytes and a mime type.

    Accepts a bare base64 payload or a data URL, because a canvas hands the
    browser a data URL and making the client strip it would be one more
    thing to get wrong.
    """
    mime = "image/png"
    payload = raw.strip()

    if payload.startswith("data:"):
        header, _, encoded = payload.partition(",")
        if not encoded:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "screenshot looked like a data URL but carried no image data.",
            )
        declared = header[5:].split(";", 1)[0]
        if declared and declared not in _SUPPORTED_IMAGE_MIME:
            supported = ", ".join(sorted(_SUPPORTED_IMAGE_MIME))
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"screenshot type {declared} is not supported; "
                f"expected one of {supported}.",
            )
        mime = declared or mime
        payload = encoded

    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "screenshot was not valid base64.",
        ) from error

    if not data:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "screenshot decoded to no data."
        )
    if len(data) > MAX_SCREENSHOT_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"screenshot is {len(data)} bytes; the limit is "
            f"{MAX_SCREENSHOT_BYTES}. Send a smaller capture.",
        )
    return data, mime


# --- finding a conversation -------------------------------------------


async def _find(db: Db, user, session_id: str) -> GuideSession | _Anonymous:
    """The conversation, from the database or from this process.

    A signed-in caller only ever reaches their own rows; an anonymous
    conversation is reachable by anyone holding its id, which is only
    guessable if the id is.
    """
    if user is not None:
        try:
            wanted = uuid.UUID(session_id)
        except ValueError:
            wanted = None
        if wanted is not None:
            found = await db.scalar(
                select(GuideSession)
                .where(GuideSession.id == wanted, GuideSession.user_id == user.id)
                .options(selectinload(GuideSession.messages))
            )
            if found is not None:
                return found

    anonymous = _anonymous.get(session_id)
    if anonymous is not None:
        return anonymous
    raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)


def _as_response(conversation: GuideSession | _Anonymous) -> GuideSessionResponse:
    return GuideSessionResponse(
        id=str(conversation.id),
        started_at=conversation.started_at,
        completed_at=conversation.completed_at,
        messages=[
            GuideMessageResponse(
                id=str(message.id),
                role=message.role,
                content=message.content,
                created_at=message.created_at,
            )
            for message in conversation.messages
        ],
    )


# --- endpoints --------------------------------------------------------


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=CreateGuideSessionResponse
)
async def create_guide_session(
    db: Db, user: CurrentUserOrNone
) -> CreateGuideSessionResponse:
    """Start a guide session (Plan.md section 4)."""
    if user is None:
        conversation = _Anonymous(id=str(uuid.uuid4()), started_at=_now())
        _anonymous[conversation.id] = conversation
        return CreateGuideSessionResponse(session_id=conversation.id, saved=False)

    session = GuideSession(user_id=user.id)
    db.add(session)
    await db.flush()
    return CreateGuideSessionResponse(session_id=str(session.id), saved=True)


@router.get("", response_model=list[GuideSessionSummary])
async def list_guide_sessions(db: Db, user: CurrentUser) -> list[GuideSessionSummary]:
    """List my conversations, most recent first.

    Not in Plan.md section 4 as written; added in Sprint 3 alongside the
    saved text pages. Without it a signed-in user's conversations were
    stored and unreachable -- the endpoint to read one needs an id, and
    nothing handed out ids after the tab was closed.

    Anonymous conversations cannot appear here and are not looked for:
    they are held in this process, belong to nobody, and are forgotten.
    """
    rows = (
        await db.scalars(
            select(GuideSession)
            .where(GuideSession.user_id == user.id)
            .order_by(GuideSession.started_at.desc())
            .options(selectinload(GuideSession.messages))
        )
    ).all()
    return [_summary(row) for row in rows]


def _summary(session: GuideSession) -> GuideSessionSummary:
    asked = [m for m in session.messages if m.role == "user"]
    return GuideSessionSummary(
        id=str(session.id),
        started_at=session.started_at,
        completed_at=session.completed_at,
        title=session.title,
        opening=asked[0].content if asked else None,
        # Counted in questions rather than messages, because "4 messages"
        # for two questions and two answers reads as twice the
        # conversation it was.
        exchanges=len(asked),
    )


@router.post(
    "/{session_id}/messages",
    status_code=status.HTTP_201_CREATED,
    response_model=GuideMessageResponse,
)
async def send_guide_message(
    db: Db, user: CurrentUserOrNone, session_id: str, payload: SendGuideMessageRequest
) -> GuideMessageResponse:
    """Send a situation description, get the next step back.

    The screenshot, when there is one, is used for this question and then
    discarded (Plan.md section 10).
    """
    conversation = await _find(db, user, session_id)
    if conversation.completed_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This guide session is already complete; start a new one.",
        )

    screenshot: bytes | None = None
    screenshot_mime: str | None = None
    if payload.screenshot is not None:
        screenshot, screenshot_mime = decode_screenshot(payload.screenshot)

    history = [
        GuideTurn(role=message.role, content=message.content)
        for message in conversation.messages
    ]
    model = create_guide_model(get_settings())

    try:
        answer = await model.respond(
            history=history,
            question=payload.content,
            screenshot=screenshot,
            screenshot_mime=screenshot_mime,
        )
    except Exception as error:
        # Nothing is written on failure, so a retry does not leave a
        # question stranded without an answer. Retry logic is Sprint 5.
        logger.exception("guide session %s: model call failed", session_id)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The guide could not answer just now. Please try again.",
        ) from error

    if isinstance(conversation, _Anonymous):
        conversation.messages.append(
            _Turn(str(uuid.uuid4()), "user", payload.content, _now())
        )
        assistant: _Turn | GuideMessage = _Turn(
            str(uuid.uuid4()), "assistant", answer, _now()
        )
        conversation.messages.append(assistant)
    else:
        db.add(
            GuideMessage(
                guide_session_id=conversation.id, role="user", content=payload.content
            )
        )
        assistant = GuideMessage(
            guide_session_id=conversation.id, role="assistant", content=answer
        )
        db.add(assistant)
        await db.flush()

    return GuideMessageResponse(
        id=str(assistant.id),
        role="assistant",
        content=assistant.content,
        created_at=assistant.created_at,
    )


@router.post(
    "/{session_id}/save",
    status_code=status.HTTP_201_CREATED,
    response_model=GuideSessionSummary,
)
async def save_guide_session(
    db: Db, user: CurrentUser, session_id: str
) -> GuideSessionSummary:
    """Keep a conversation that was not being kept.

    Not in Plan.md section 4 as written; added in Sprint 3 for auto-save
    off. What gets written is the copy this service is already holding,
    not one the browser sends back -- the same reason a caption
    transcript's lines are what the recogniser produced. The client cannot
    put words in the assistant's mouth by asking for them to be saved.

    Saving twice adds the turns since the last time rather than writing a
    second copy, so carrying on and saving again keeps one conversation.
    """
    conversation = _anonymous.get(session_id)
    if conversation is None:
        # Held in this process, so a restart loses it. Better to say so
        # than to write an empty conversation and call it kept.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "That conversation is no longer available to save.",
        )

    if conversation.saved_as is None:
        session = GuideSession(
            user_id=user.id,
            started_at=conversation.started_at,
            completed_at=conversation.completed_at,
        )
        db.add(session)
        await db.flush()
        conversation.saved_as = session.id
    else:
        session = await db.scalar(
            select(GuideSession)
            .where(
                GuideSession.id == conversation.saved_as,
                GuideSession.user_id == user.id,
            )
            .options(selectinload(GuideSession.messages))
        )
        if session is None:
            # Deleted from the list since it was saved; keeping it again
            # would resurrect something the person threw away.
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                "That conversation was deleted; it cannot be saved again.",
            )
        session.completed_at = conversation.completed_at

    for turn in conversation.messages[conversation.saved_turns :]:
        db.add(
            GuideMessage(
                guide_session_id=session.id,
                role=turn.role,
                content=turn.content,
                created_at=turn.created_at,
            )
        )
    conversation.saved_turns = len(conversation.messages)
    await db.flush()
    await db.refresh(session, ["messages"])
    return _summary(session)


@router.patch("/{session_id}", response_model=GuideSessionSummary)
async def rename_guide_session(
    db: Db, user: CurrentUser, session_id: uuid.UUID, payload: RenameGuideSessionRequest
) -> GuideSessionSummary:
    """Give a conversation a name (added in Sprint 3, as for caption sessions)."""
    session = await db.scalar(
        select(GuideSession)
        .where(GuideSession.id == session_id, GuideSession.user_id == user.id)
        .options(selectinload(GuideSession.messages))
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)

    title = (payload.title or "").strip()
    # An empty name is not a name: it goes back to being shown by the
    # question that started it.
    session.title = title or None
    await db.flush()
    return _summary(session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_guide_session(
    db: Db, user: CurrentUser, session_id: uuid.UUID
) -> None:
    """Delete a conversation and its messages (added in Sprint 3)."""
    result = await db.execute(
        delete(GuideSession).where(
            GuideSession.id == session_id, GuideSession.user_id == user.id
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)


@router.get("/{session_id}", response_model=GuideSessionResponse)
async def get_guide_session(
    db: Db, user: CurrentUserOrNone, session_id: str
) -> GuideSessionResponse:
    """Get conversation history (Plan.md section 4)."""
    return _as_response(await _find(db, user, session_id))


@router.patch("/{session_id}/complete", response_model=GuideSessionResponse)
async def complete_guide_session(
    db: Db, user: CurrentUserOrNone, session_id: str
) -> GuideSessionResponse:
    """Mark the session complete (Plan.md section 4). Completing twice is fine."""
    conversation = await _find(db, user, session_id)
    if conversation.completed_at is None:
        conversation.completed_at = _now()
        if not isinstance(conversation, _Anonymous):
            await db.flush()
    return _as_response(conversation)
