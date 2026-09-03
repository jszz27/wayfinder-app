import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.caption_sessions import reset_sessions
from app.routers.guide_sessions import reset_sessions as reset_guide_sessions


@pytest.fixture
def client() -> TestClient:
    reset_sessions()
    reset_guide_sessions()
    return TestClient(app)
