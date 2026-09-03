"""Chooses the guide model named by WAYFINDER_LLM."""

from __future__ import annotations

from app.config import Settings
from app.guide.base import GuideModel
from app.guide.mock import MockGuideModel


def create_guide_model(settings: Settings) -> GuideModel:
    backend = settings.llm_backend
    if backend == "mock":
        return MockGuideModel()
    if backend == "gemini":
        # Imported lazily so the mock path needs no google-genai.
        from app.guide.gemini import GeminiGuideModel

        return GeminiGuideModel(settings)
    raise ValueError(
        f"Unknown WAYFINDER_LLM value {backend!r}; expected 'mock' or 'gemini'."
    )
