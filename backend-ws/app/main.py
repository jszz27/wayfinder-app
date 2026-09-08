"""Wayfinder WebSocket caption server (Plan.md section 3).

Endpoint and message set follow Plan.md section 5:
    ws://<host>/ws/caption?session_id={session_id}
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
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


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws/caption")
async def caption_stream(
    websocket: WebSocket,
    session_id: str | None = Query(default=None),
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
        stt = create_stt_stream(get_settings())
    except Exception:
        logger.exception("could not start speech recognition")
        await websocket.send_text(
            ErrorMessage(message="Speech recognition is unavailable.").model_dump_json()
        )
        await websocket.close()
        return

    store = CaptionStore(get_settings(), session_id)
    await CaptionStreamSession(websocket, session_id, stt, store).run()
