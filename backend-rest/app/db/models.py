"""The tables of Plan.md section 6.

Two additions to that schema, both gaps rather than preferences.

`users` gains the accessibility settings that section 4's
`PATCH /api/users/me` is meant to update; section 6 gives that table
nowhere to keep them.

`refresh_tokens` exists so that section 4's `DELETE /api/auth/logout` can
mean something. A JWT cannot be withdrawn once issued, so logging out has
to revoke the refresh token instead, and revoking needs somewhere to write.

Ownership: a row here belongs to a signed-in user. Captioning works with no
account at all, and in that case no session row is written, which is what
stops a transcript being retained for someone who never asked for one.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

AUDIO_SOURCES = ("mic", "tab_audio")
MESSAGE_ROLES = ("user", "assistant")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Stored lower-cased, so the unique index is a real guarantee rather
    # than one that Ann@example.com can walk around.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # --- accessibility settings (Plan.md section 8) ---------------------
    font_size: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    # Whether stopping a recording saves it without being asked. Off means
    # the widget holds the transcript until the user presses Save.
    auto_save: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    # NULL means detect the language rather than pin it, which is what the
    # caption pipeline already does by default.
    caption_language: Mapped[str | None] = mapped_column(String(35), nullable=True)

    caption_sessions: Mapped[list["CaptionSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    guide_sessions: Mapped[list["GuideSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("font_size between 8 and 96", name="ck_users_font_size"),
    )


class CaptionSession(Base):
    __tablename__ = "caption_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Both filled in by backend-ws when the stream finishes: nothing else
    # knows when the audio stopped, or what language was recognised.
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    language: Mapped[str | None] = mapped_column(String(35), nullable=True)
    audio_source: Mapped[str] = mapped_column(String(16), nullable=False)

    # What the person called it. Null means it has not been renamed, and
    # the interface shows the date instead.
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # What the person kept, when that differs from what was recognised.
    # caption_lines stays exactly what the recogniser produced, so an edit
    # can be undone and it remains clear which text came from where. Null
    # until a session is edited or saved by hand.
    edited_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="caption_sessions")
    lines: Mapped[list["CaptionLine"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="CaptionLine.seq",
    )

    __table_args__ = (
        CheckConstraint(
            "audio_source in ('mic', 'tab_audio')", name="ck_caption_sessions_source"
        ),
        Index("ix_caption_sessions_user_started", "user_id", "started_at"),
    )


class CaptionLine(Base):
    __tablename__ = "caption_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("caption_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The caption line ordinal, not an audio chunk number; see
    # docs/sprint-1.md. Only confirmed lines are written (section 5), so a
    # given seq is written once per session.
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped["CaptionSession"] = relationship(back_populates="lines")

    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_caption_lines_session_seq"),
    )


class GuideSession(Base):
    __tablename__ = "guide_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Null until renamed, like a caption session's. The list shows the
    # first question asked instead, which is what makes a conversation
    # recognisable when nobody has named it.
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)

    user: Mapped["User"] = relationship(back_populates="guide_sessions")
    messages: Mapped[list["GuideMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="GuideMessage.created_at",
    )

    __table_args__ = (Index("ix_guide_sessions_user_started", "user_id", "started_at"),)


class GuideMessage(Base):
    __tablename__ = "guide_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    guide_session_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("guide_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # Text only. The screenshot that came with a question is never stored
    # (Plan.md section 10), so there is deliberately no column for it.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped["GuideSession"] = relationship(back_populates="messages")

    __table_args__ = (
        CheckConstraint("role in ('user', 'assistant')", name="ck_guide_messages_role"),
    )


class RefreshToken(Base):
    """One issued refresh token, so that logging out can revoke it."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # The hash, never the token itself. A leaked database should not hand
    # over working credentials, which is why password_hash exists too.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")

    __table_args__ = (Index("ix_refresh_tokens_user", "user_id"),)
