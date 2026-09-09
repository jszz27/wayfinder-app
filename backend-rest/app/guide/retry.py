"""Asking again when the model was merely busy.

Wraps any GuideModel, so the endpoints, the mock and the Gemini adapter
all stay unaware that retrying happens at all.

Two things are deliberately small. Only errors the adapter calls transient
are retried -- a request the model has already refused will be refused
again, and asking twice only makes the person wait longer for the same
answer. And the waits are short: guide mode is someone standing at a cash
machine wondering what to press, so the whole retry budget is under a
second and a half. A slow answer is worth having; a slow failure is not.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from app.guide.base import GuideModel, GuideTurn

logger = logging.getLogger(__name__)

# Two extra attempts, and the gaps between them. Long enough for a quota
# queue to drain or a load balancer to pick another backend, short enough
# that a failure still arrives while the user is looking at the screen.
RETRY_DELAYS_SECONDS = (0.4, 1.0)


class RetryingGuideModel(GuideModel):
    """A model that asks again when the answer was "busy", not "no"."""

    def __init__(self, inner: GuideModel, delays: Sequence[float] | None = None) -> None:
        self._inner = inner
        self._delays = tuple(RETRY_DELAYS_SECONDS if delays is None else delays)

    async def respond(
        self,
        history: Sequence[GuideTurn],
        question: str,
        screenshot: bytes | None,
        screenshot_mime: str | None,
    ) -> str:
        attempts = len(self._delays) + 1
        for attempt in range(1, attempts + 1):
            try:
                return await self._inner.respond(
                    history=history,
                    question=question,
                    screenshot=screenshot,
                    screenshot_mime=screenshot_mime,
                )
            except Exception as error:
                last = attempt == attempts
                if last or not self._inner.is_transient(error):
                    raise
                delay = self._delays[attempt - 1]
                logger.warning(
                    "guide model attempt %s of %s failed (%s); retrying in %ss",
                    attempt,
                    attempts,
                    error,
                    delay,
                )
                await asyncio.sleep(delay)
        # Unreachable: the loop either returns or raises on its last pass.
        raise AssertionError("retry loop ended without returning or raising")

    def is_transient(self, error: Exception) -> bool:
        return self._inner.is_transient(error)
