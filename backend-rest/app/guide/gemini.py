"""Gemini on Vertex AI, the vision-capable model behind guide mode.

Requires the `gemini` extra:  pip install ".[gemini]"

Vertex is used rather than the public Gemini endpoint so the server
authenticates with the Application Default Credentials this project
already uses for speech-to-text -- no second API key to hold.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from app.config import Settings
from app.guide.base import GuideModel, GuideTurn
from app.guide.prompt import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class GeminiGuideModel(GuideModel):
    def __init__(self, settings: Settings) -> None:
        if not settings.google_project:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT must be set when WAYFINDER_LLM=gemini."
            )
        self._settings = settings

    async def respond(
        self,
        history: Sequence[GuideTurn],
        question: str,
        screenshot: bytes | None,
        screenshot_mime: str | None,
    ) -> str:
        from google import genai
        from google.genai import types

        settings = self._settings
        client = genai.Client(
            vertexai=True,
            project=settings.google_project,
            location=settings.gemini_location,
        )

        contents: list[types.Content] = [
            types.Content(
                role="user" if turn.role == "user" else "model",
                parts=[types.Part.from_text(text=turn.content)],
            )
            for turn in history
        ]

        # The screenshot goes with this question only. It is never added to
        # the stored history, so it cannot leak into a later request either.
        parts: list[types.Part] = []
        if screenshot is not None:
            parts.append(
                types.Part.from_bytes(
                    data=screenshot, mime_type=screenshot_mime or "image/png"
                )
            )
        parts.append(types.Part.from_text(text=question))
        contents.append(types.Content(role="user", parts=parts))

        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.2,
                max_output_tokens=settings.gemini_max_output_tokens,
                # Gemini 2.5 spends part of the output budget on internal
                # reasoning, which truncated the visible answer mid-sentence.
                # Guide replies are two or three sentences; they do not need it.
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )

        text = (response.text or "").strip()
        if not text:
            logger.warning("gemini returned no text; finish=%s", response.candidates)
            raise RuntimeError("The guide model returned an empty answer.")
        return text
