"""Environment-backed settings for the REST API server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

_DEFAULT_CORS_ORIGINS = "http://localhost:5173"


@dataclass(frozen=True)
class Settings:
    """Values read once from the environment at startup."""

    cors_origins: tuple[str, ...]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    raw = os.getenv("CORS_ORIGINS", _DEFAULT_CORS_ORIGINS)
    origins = tuple(origin.strip() for origin in raw.split(",") if origin.strip())
    return Settings(cors_origins=origins)
