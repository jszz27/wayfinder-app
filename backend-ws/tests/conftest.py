import base64
import os

import pytest

# Every test in this suite runs against the credential-free adapter.
os.environ.setdefault("WAYFINDER_STT", "mock")

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402

# 100 ms of 16 kHz mono PCM16 silence -- the agreed chunk size.
SILENT_CHUNK = base64.b64encode(b"\x00" * 3200).decode("ascii")


@pytest.fixture(autouse=True)
def _mock_stt_backend(monkeypatch):
    monkeypatch.setenv("WAYFINDER_STT", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    return TestClient(app)


def send_chunks(ws, count, *, start_seq=0, source="mic"):
    """Push `count` audio_chunk messages in the Plan.md section 5 shape."""
    for offset in range(count):
        ws.send_json(
            {
                "type": "audio_chunk",
                "data": SILENT_CHUNK,
                "seq": start_seq + offset,
                "source": source,
            }
        )
