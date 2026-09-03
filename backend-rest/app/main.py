"""Wayfinder REST API server (Plan.md section 3).

Sprint 1 scope is a health check plus caption session creation. Auth,
guide mode, and user settings are later sprints.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import caption_sessions

app = FastAPI(title="Wayfinder REST API", version="0.1.0")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(caption_sessions.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
