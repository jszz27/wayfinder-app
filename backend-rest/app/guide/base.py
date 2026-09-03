"""The interface every guide model implements.

Keeping the LLM behind this seam is what lets the whole guide flow -- the
endpoints, the conversation history, the screenshot path -- be built and
tested with no cloud credentials, the same way SttStream does for
captions in backend-ws.
"""

from __future__ import annotations

import abc
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

Role = Literal["user", "assistant"]


@dataclass(frozen=True)
class GuideTurn:
    """One earlier turn of the conversation, as stored in guide_messages."""

    role: Role
    content: str


class GuideModel(abc.ABC):
    """Generates the next-step guidance for one question."""

    @abc.abstractmethod
    async def respond(
        self,
        history: Sequence[GuideTurn],
        question: str,
        screenshot: bytes | None,
        screenshot_mime: str | None,
    ) -> str:
        """Answer `question`, optionally looking at the screen it came with.

        The screenshot arrives as bytes and is never returned or stored;
        Plan.md section 10 keeps it out of guide_messages on purpose.
        """
