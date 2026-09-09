"""Chooses the guide model named by WAYFINDER_LLM."""

from __future__ import annotations

from app.config import Settings
from app.guide.base import GuideModel
from app.guide.mock import MockGuideModel
from app.guide.retry import RetryingGuideModel


def create_guide_model(settings: Settings) -> GuideModel:
    """The configured model, wrapped so a busy service is asked again.

    Every model is wrapped, including the mock. The mock calls nothing and
    never reports a transient error, so wrapping it changes no behaviour
    -- but it means the tests exercise the same object the product uses,
    rather than a shorter path that happens to work.
    """
    backend = settings.llm_backend
    if backend == "mock":
        return RetryingGuideModel(MockGuideModel())
    if backend == "gemini":
        # Imported lazily so the mock path needs no google-genai.
        from app.guide.gemini import GeminiGuideModel

        return RetryingGuideModel(GeminiGuideModel(settings))
    raise ValueError(
        f"Unknown WAYFINDER_LLM value {backend!r}; expected 'mock' or 'gemini'."
    )
