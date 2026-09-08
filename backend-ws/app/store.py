"""Writing a caption session's transcript, when there is one to write to.

This service holds a deliberately narrow connection. It does three things:
find out whether a session is one that gets saved, append confirmed lines,
and stamp the session as finished. The schema and its migrations belong to
backend-rest; nothing here creates or alters a table, and the SQL is
written out rather than mapped, so there is no second copy of the models
to drift from the first.

Whether a session is saved is not something this service is told. It looks
for the row: backend-rest writes one only for a signed-in user, so finding
none is what says the speaker is anonymous and their words are not to be
kept. Nothing here can override that.

Persistence is never allowed to interrupt captioning. Every failure is
logged and swallowed, and a session that fails once stops trying, because
a live caption that keeps working matters more than a saved copy of it.
"""

from __future__ import annotations

import logging
import uuid
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import Settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_engine(database_url: str) -> AsyncEngine:
    # Small pool: this service holds one long-lived socket per listener and
    # writes a row every few seconds, not a request per user action.
    return create_async_engine(
        database_url, pool_pre_ping=True, pool_size=5, max_overflow=5
    )


class CaptionStore:
    """The transcript side of one caption session."""

    def __init__(self, settings: Settings, session_id: str) -> None:
        self._settings = settings
        self._session_id = session_id
        self._uuid: uuid.UUID | None = None
        self._saving = False

    @property
    def saving(self) -> bool:
        """True once a row has been found and writing has not since failed."""
        return self._saving

    async def open(self) -> bool:
        """Look for the session's row. False means nothing will be written."""
        if not self._settings.database_url:
            return False
        try:
            # An anonymous session id is a UUID too, but any client can send
            # anything, so this is parsed rather than trusted.
            self._uuid = uuid.UUID(self._session_id)
        except ValueError:
            return False

        try:
            engine = get_engine(self._settings.database_url)
            async with engine.connect() as connection:
                found = await connection.scalar(
                    text("select 1 from caption_sessions where id = :id"),
                    {"id": self._uuid},
                )
        except Exception:
            logger.exception(
                "caption session %s: could not reach the database", self._session_id
            )
            return False

        self._saving = found is not None
        return self._saving

    async def add_line(self, seq: int, line: str) -> None:
        """Record one confirmed line (Plan.md section 5)."""
        if not self._saving:
            return
        try:
            engine = get_engine(self._settings.database_url)
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "insert into caption_lines (id, session_id, seq, text) "
                        "values (:id, :session_id, :seq, :text) "
                        # A reconnect can replay a line ordinal that was
                        # already written; the transcript should not gain a
                        # duplicate because the socket blinked.
                        "on conflict (session_id, seq) "
                        "do update set text = excluded.text"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "session_id": self._uuid,
                        "seq": seq,
                        "text": line,
                    },
                )
        except Exception:
            logger.exception(
                "caption session %s: could not save line %s; stopping saving",
                self._session_id,
                seq,
            )
            self._saving = False

    async def finish(self, language: str | None) -> None:
        """Close the session off with when it ended and what was recognised."""
        if not self._saving:
            return
        try:
            engine = get_engine(self._settings.database_url)
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "update caption_sessions "
                        "set ended_at = now(), "
                        # Only fill the language in; a detected value should
                        # not be wiped by a session that ended before
                        # anything was recognised.
                        "    language = coalesce(:language, language) "
                        "where id = :id"
                    ),
                    {"id": self._uuid, "language": language},
                )
        except Exception:
            logger.exception(
                "caption session %s: could not close the session off", self._session_id
            )
            self._saving = False
