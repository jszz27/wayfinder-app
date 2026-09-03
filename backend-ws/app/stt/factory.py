"""Chooses the STT adapter named by WAYFINDER_STT."""

from __future__ import annotations

from app.config import Settings
from app.stt.base import SttStream
from app.stt.mock import MockSttStream


def create_stt_stream(settings: Settings) -> SttStream:
    backend = settings.stt_backend
    if backend == "mock":
        return MockSttStream()
    if backend == "google":
        # Imported lazily so the mock path needs no google-cloud-speech.
        from app.stt.google_v2 import GoogleSttStream

        return GoogleSttStream(settings)
    raise ValueError(
        f"Unknown WAYFINDER_STT value {backend!r}; expected 'mock' or 'google'."
    )
