"""Environment-backed settings for the REST API server."""

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

_DEFAULT_CORS_ORIGINS = "http://localhost:5173"


@dataclass(frozen=True)
class Settings:
    """Values read once from the environment at startup."""

    cors_origins: tuple[str, ...]

    # Guide mode (Plan.md section 4). "mock" needs no cloud project.
    llm_backend: str
    google_project: str | None
    gemini_location: str
    gemini_model: str
    gemini_max_output_tokens: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    raw = os.getenv("CORS_ORIGINS", _DEFAULT_CORS_ORIGINS)
    origins = tuple(origin.strip() for origin in raw.split(",") if origin.strip())
    return Settings(
        cors_origins=origins,
        llm_backend=os.getenv("WAYFINDER_LLM", "mock").lower(),
        google_project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        # Gemini is served from regional endpoints; "global" also works but
        # us-central1 is where the speech models this project uses already live.
        gemini_location=os.getenv("GEMINI_LOCATION", "us-central1"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        gemini_max_output_tokens=int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "400")),
    )
