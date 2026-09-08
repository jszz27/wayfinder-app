"""Profile and accessibility settings (Plan.md section 4).

Section 4 describes PATCH here as updating *accessibility settings*, so
that is all it updates: text size, and whether the caption language is
pinned or detected. Email and display name are identity rather than
settings, and changing an email is a flow of its own -- confirmation, and
what happens to the old address -- rather than a field on this endpoint.

Both settings already exist client-side. Storing them is what makes them
follow someone to another device, which for a tool whose users need larger
text is the difference between setting it once and setting it every time.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.auth.dependencies import CurrentUser, Db

router = APIRouter(prefix="/api/users", tags=["users"])

# The bounds the database enforces, repeated here so an impossible value is
# a clear 422 rather than an integrity error surfacing as a 500.
MIN_FONT_SIZE = 8
MAX_FONT_SIZE = 96

# Deliberately loose: a BCP-47 tag, not a list of the languages detection
# happens to cover. Pinning a language the recogniser supports but
# detection does not is a legitimate thing to want.
_LANGUAGE_TAG = re.compile(r"^[A-Za-z]{2,8}(-[A-Za-z0-9]{2,8})*$")


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    created_at: datetime
    font_size: int
    # None means detect the language rather than pin it, which is what the
    # caption pipeline does by default.
    caption_language: str | None
    # Whether stopping a recording keeps it without being asked.
    auto_save: bool


class UpdateSettingsRequest(BaseModel):
    font_size: int | None = Field(default=None, ge=MIN_FONT_SIZE, le=MAX_FONT_SIZE)
    caption_language: str | None = None
    auto_save: bool | None = None

    @field_validator("caption_language")
    @classmethod
    def _check_tag(cls, value: str | None) -> str | None:
        if value is None:
            return None
        tag = value.strip()
        if not tag:
            # An empty string is how a form sends "no language chosen", and
            # it means the same as null: go back to detecting.
            return None
        if not _LANGUAGE_TAG.match(tag):
            raise ValueError("not a language tag, for example en-US or ko-KR")
        return tag


@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUser) -> UserResponse:
    """Profile and settings for the signed-in user."""
    return UserResponse.model_validate(user, from_attributes=True)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    db: Db, user: CurrentUser, payload: UpdateSettingsRequest
) -> UserResponse:
    """Update accessibility settings.

    A partial update in the real sense: only the fields actually sent are
    touched. That matters for `caption_language`, where sending null means
    "go back to detecting" and leaving it out means "do not touch it" --
    two intentions that look identical after parsing unless the fields that
    were actually sent are inspected.
    """
    sent = payload.model_dump(exclude_unset=True)
    if not sent:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Send at least one setting to change.",
        )

    if "font_size" in sent:
        if sent["font_size"] is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "font_size cannot be cleared; choose a size.",
            )
        user.font_size = sent["font_size"]

    if "caption_language" in sent:
        user.caption_language = payload.caption_language

    if "auto_save" in sent:
        if payload.auto_save is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "auto_save is on or off; it cannot be cleared.",
            )
        user.auto_save = payload.auto_save

    await db.flush()
    return UserResponse.model_validate(user, from_attributes=True)
