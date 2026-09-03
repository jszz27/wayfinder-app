"""A credential-free guide model.

Answers deterministically so the endpoints, the conversation history, and
the screenshot path can be exercised end to end without a cloud project.
It reports whether it was given a screenshot, which is what makes the
"screen sharing is on" path testable.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.guide.base import GuideModel, GuideTurn


class MockGuideModel(GuideModel):
    async def respond(
        self,
        history: Sequence[GuideTurn],
        question: str,
        screenshot: bytes | None,
        screenshot_mime: str | None,
    ) -> str:
        turn = len([t for t in history if t.role == "user"]) + 1
        if screenshot is None:
            return (
                f"(mock reply {turn}) I cannot see your screen, so I am "
                f'answering from your words alone: "{question}".'
            )
        return (
            f"(mock reply {turn}) I can see your screen "
            f"({len(screenshot)} bytes). Next, press the button at the "
            f'bottom right. You asked: "{question}".'
        )
