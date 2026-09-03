import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.caption_sessions import reset_sessions


@pytest.fixture
def client() -> TestClient:
    reset_sessions()
    return TestClient(app)
