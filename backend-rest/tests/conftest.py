import os

import pytest
from fastapi.testclient import TestClient

# Every test in this suite runs against the credential-free model. This is
# set before app.config is imported, because that import is where .env is
# read, and a real environment variable takes precedence over the file --
# otherwise a developer with WAYFINDER_LLM=gemini in .env would silently
# point the whole suite at a paid API.
os.environ.setdefault("WAYFINDER_LLM", "mock")

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.caption_sessions import reset_sessions  # noqa: E402
from app.routers.guide_sessions import (  # noqa: E402
    reset_sessions as reset_guide_sessions,
)


@pytest.fixture(autouse=True)
def _mock_guide_model(monkeypatch):
    monkeypatch.setenv("WAYFINDER_LLM", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    reset_sessions()
    reset_guide_sessions()
    return TestClient(app)
