"""Chooses the STT adapter named by WAYFINDER_STT."""

from __future__ import annotations

from app.config import Settings
from app.stt.base import SttStream
from app.stt.mock import MockSttStream
from app.stt.resilient import ResilientSttStream


def create_stt_stream(settings: Settings) -> SttStream:
    """The configured recogniser, wrapped so one session outlives one stream.

    Only the Google path is wrapped. The mock stream ends when it is told
    to and never early, so wrapping it would add a layer that can only
    ever pass audio through -- and would make the tests exercise recovery
    that cannot happen.
    """
    backend = settings.stt_backend
    if backend == "mock":
        return MockSttStream()
    if backend == "google":
        # Imported lazily so the mock path needs no google-cloud-speech.
        if settings.stt_auto_detect:
            from app.stt.auto import AutoDetectSttStream

            return ResilientSttStream(lambda: AutoDetectSttStream(settings))
        from app.stt.google_v2 import GoogleSttStream

        return ResilientSttStream(lambda: GoogleSttStream(settings))
    raise ValueError(
        f"Unknown WAYFINDER_STT value {backend!r}; expected 'mock' or 'google'."
    )
