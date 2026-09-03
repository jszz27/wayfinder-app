"""Environment-backed settings for the WebSocket caption server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Load the repository's .env before any setting is read. Real environment
# variables win (override=False), so a deployment's configuration is never
# overridden by a developer's local file.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

# The audio wire format agreed with the widget; see docs/sprint-1.md.
SAMPLE_RATE_HZ = 16_000
CHANNELS = 1

_DEFAULT_CORS_ORIGINS = "http://localhost:5173"


@dataclass(frozen=True)
class Settings:
    """Values read once from the environment at startup."""

    stt_backend: str
    stt_language: str
    """Pinned language, and the fallback when detection cannot name one."""

    stt_model: str
    stt_auto_detect: bool
    google_project: str | None
    google_location: str
    google_detect_location: str
    cors_origins: tuple[str, ...]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    raw_origins = os.getenv("CORS_ORIGINS", _DEFAULT_CORS_ORIGINS)
    origins = tuple(o.strip() for o in raw_origins.split(",") if o.strip())
    return Settings(
        stt_backend=os.getenv("WAYFINDER_STT", "mock").lower(),
        stt_language=os.getenv("STT_LANGUAGE", "ko-KR"),
        stt_model=os.getenv("STT_MODEL", "long"),
        stt_auto_detect=os.getenv("STT_AUTO_DETECT", "false").lower() == "true",
        google_project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        google_location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
        # Language detection needs a regional endpoint; "global" has no chirp_2.
        google_detect_location=os.getenv("GOOGLE_DETECT_LOCATION", "us-central1"),
        cors_origins=origins,
    )
