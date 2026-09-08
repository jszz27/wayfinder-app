"""Wayfinder WebSocket caption server (Plan.md section 3).

Endpoint and message set follow Plan.md section 5:
    ws://<host>/ws/caption?session_id={session_id}[&language={tag}]

`language` and the `auth` frame were both added in Sprint 3; see
docs/sprint-3.md. The token is a message rather than a query parameter
because query strings are written to every access log.
"""

from __future__ import annotations

import dataclasses
import logging
import re

from fastapi import FastAPI, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.protocol import ErrorMessage
from app.session import CaptionStreamSession
from app.store import CaptionStore
from app.stt.factory import create_stt_stream

logger = logging.getLogger(__name__)

app = FastAPI(title="Wayfinder WebSocket caption server", version="0.1.0")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Policy-violation close code, used for a handshake we accept and then
# reject because a required parameter is missing.
WS_POLICY_VIOLATION = 1008

# Deliberately a shape, not a list, matching the same check on
# PATCH /api/users/me: pinning a language the recogniser supports but
# detection does not is a legitimate thing to want, and this service is
# not the place to decide which those are.
_LANGUAGE_TAG = re.compile(r"^[A-Za-z]{2,8}(-[A-Za-z0-9]{2,8})*$")


def for_language(settings: Settings, language: str | None) -> Settings:
    """Settings pinned to `language`, or unchanged if there is none.

    Pinning turns detection off. That is the whole meaning of the setting:
    someone who has said which language they are speaking is telling us not
    to guess, and a detector that could still override them would make the
    choice advisory. A tag that is not one is ignored rather than fatal --
    a preference should never be the reason captions do not start.
    """
    if language is None:
        return settings
    tag = language.strip()
    if not tag or not _LANGUAGE_TAG.match(tag):
        logger.warning("ignoring malformed language %r; detecting instead", language)
        return settings
    return dataclasses.replace(settings, stt_language=tag, stt_auto_detect=False)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws/caption")
async def caption_stream(
    websocket: WebSocket,
    session_id: str | None = Query(default=None),
    # Plan.md section 5, amended in Sprint 3: the caption language the
    # listener has pinned. Absent means detect it, which is what every
    # session did before the setting existed.
    language: str | None = Query(default=None),
) -> None:
    # Accept first so the client sees a close code rather than a bare
    # handshake rejection.
    await websocket.accept()

    if not session_id:
        await websocket.close(
            code=WS_POLICY_VIOLATION, reason="session_id is required"
        )
        return

    try:
        stt = create_stt_stream(for_language(get_settings(), language))
    except Exception:
        logger.exception("could not start speech recognition")
        await websocket.send_text(
            ErrorMessage(message="Speech recognition is unavailable.").model_dump_json()
        )
        await websocket.close()
        return

    settings = get_settings()
    store = CaptionStore(settings, session_id)
    await CaptionStreamSession(
        websocket, session_id, stt, store, jwt_secret=settings.jwt_secret
    ).run()
