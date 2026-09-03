"""The interface every STT adapter implements.

Keeping the WebSocket layer behind this seam is what lets the whole
mic -> caption path run against the mock adapter with no cloud
credentials, and lets Sprint 5 add retry/fallback in one place.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(frozen=True)
class SttResult:
    """One transcription result.

    `is_final` maps straight onto Plan.md section 5: False marks an
    interim result that may still be revised, True a confirmed sentence.
    `language` is the BCP-47 tag the text was recognised as, set only when
    the language was detected rather than configured.
    """

    text: str
    is_final: bool
    language: str | None = None
    # How sure the recogniser is, on finals only. It collapses when the
    # stream is pinned to the wrong language, which is how a speaker
    # switching language mid-session is noticed. None when not reported.
    confidence: float | None = None


class SttStream(abc.ABC):
    """A single session's streaming recognition."""

    @abc.abstractmethod
    async def push(self, pcm: bytes) -> None:
        """Feed one chunk of 16 kHz mono PCM16 audio."""

    @abc.abstractmethod
    def results(self) -> AsyncIterator[SttResult]:
        """Yield results until the stream is closed and drained."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Signal end of audio; `results()` finishes after the last result."""
