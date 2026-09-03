"""Digital guide mode endpoints (Plan.md section 4).

Sprint 2 implements the four guide routes and holds conversations in
memory; PostgreSQL arrives in Sprint 3 alongside auth, so `user_id` is a
placeholder here rather than a real foreign key.

Plan.md section 10 is the reason the screenshot never reaches storage: it
is decoded, passed to the model for that one question, and dropped. Only
the text of both turns is kept.
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

from app.config import get_settings
from app.guide.base import GuideTurn
from app.guide.factory import create_guide_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/guide/sessions", tags=["guide"])

Role = Literal["user", "assistant"]

# Auth is Sprint 3 (Plan.md section 7 step 3). Until then every guide
# session belongs to this stand-in, so guide_sessions.user_id has the shape
# section 6 calls for without inventing a login.
PLACEHOLDER_USER_ID = "local-user"

# A downscaled screenshot is tens of kilobytes; this only exists to stop a
# full-resolution capture from becoming an unbounded request body.
MAX_SCREENSHOT_BYTES = 4 * 1024 * 1024

_SUPPORTED_IMAGE_MIME = {"image/png", "image/jpeg", "image/webp"}


# --- storage ----------------------------------------------------------


@dataclass
class GuideMessage:
    """One row of `guide_messages` (Plan.md section 6)."""

    id: str
    role: Role
    content: str
    created_at: datetime


@dataclass
class GuideSession:
    """One row of `guide_sessions`, with its messages alongside."""

    id: str
    user_id: str
    started_at: datetime
    completed_at: datetime | None = None
    messages: list[GuideMessage] = field(default_factory=list)


# Process-local, deliberately: replaced by PostgreSQL in Sprint 3.
_sessions: dict[str, GuideSession] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _append(session: GuideSession, role: Role, content: str) -> GuideMessage:
    message = GuideMessage(
        id=str(uuid.uuid4()), role=role, content=content, created_at=_now()
    )
    session.messages.append(message)
    return message


# --- request and response bodies --------------------------------------


class CreateGuideSessionResponse(BaseModel):
    session_id: str


class SendGuideMessageRequest(BaseModel):
    """Plan.md section 4: the text question plus an optional screenshot."""

    content: str = Field(min_length=1, max_length=4000)
    # Base64, with or without a `data:image/...;base64,` prefix. Present
    # only while screen sharing is on (Plan.md section 10).
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


def _to_response(session: GuideSession) -> GuideSessionResponse:
    return GuideSessionResponse(
        id=session.id,
        started_at=session.started_at,
        completed_at=session.completed_at,
        messages=[
            GuideMessageResponse(
                id=m.id, role=m.role, content=m.content, created_at=m.created_at
            )
            for m in session.messages
        ],
    )


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


def _require_open(session_id: str) -> GuideSession:
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such guide session.")
    if session.completed_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This guide session is already complete; start a new one.",
        )
    return session


# --- endpoints --------------------------------------------------------


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=CreateGuideSessionResponse
)
def create_guide_session() -> CreateGuideSessionResponse:
    """Start a guide session (Plan.md section 4)."""
    session = GuideSession(
        id=str(uuid.uuid4()), user_id=PLACEHOLDER_USER_ID, started_at=_now()
    )
    _sessions[session.id] = session
    return CreateGuideSessionResponse(session_id=session.id)


@router.post(
    "/{session_id}/messages",
    status_code=status.HTTP_201_CREATED,
    response_model=GuideMessageResponse,
)
async def send_guide_message(
    session_id: str, payload: SendGuideMessageRequest
) -> GuideMessageResponse:
    """Send a situation description, get the next step back.

    The screenshot, when there is one, is used for this question and then
    discarded (Plan.md section 10).
    """
    session = _require_open(session_id)

    screenshot: bytes | None = None
    screenshot_mime: str | None = None
    if payload.screenshot is not None:
        screenshot, screenshot_mime = decode_screenshot(payload.screenshot)

    history = [GuideTurn(role=m.role, content=m.content) for m in session.messages]
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

    _append(session, "user", payload.content)
    assistant = _append(session, "assistant", answer)
    return GuideMessageResponse(
        id=assistant.id,
        role=assistant.role,
        content=assistant.content,
        created_at=assistant.created_at,
    )


@router.get("/{session_id}", response_model=GuideSessionResponse)
def get_guide_session(session_id: str) -> GuideSessionResponse:
    """Get conversation history (Plan.md section 4)."""
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such guide session.")
    return _to_response(session)


@router.patch("/{session_id}/complete", response_model=GuideSessionResponse)
def complete_guide_session(session_id: str) -> GuideSessionResponse:
    """Mark the session complete (Plan.md section 4). Completing twice is fine."""
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such guide session.")
    if session.completed_at is None:
        session.completed_at = _now()
    return _to_response(session)


def reset_sessions() -> None:
    """Clear the store so tests do not leak state into each other."""
    _sessions.clear()
