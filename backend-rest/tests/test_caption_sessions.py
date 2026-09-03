"""Plan.md section 4: POST /api/caption-sessions with an audio_source body."""

import uuid

import pytest

from app.routers.caption_sessions import get_session


@pytest.mark.parametrize("audio_source", ["mic", "tab_audio"])
def test_create_session_returns_a_uuid(client, audio_source):
    response = client.post(
        "/api/caption-sessions", json={"audio_source": audio_source}
    )

    assert response.status_code == 201
    session_id = response.json()["session_id"]
    # Raises if the id is not a well-formed UUID.
    uuid.UUID(session_id)
    assert get_session(session_id).audio_source == audio_source


def test_each_session_gets_a_distinct_id(client):
    first = client.post("/api/caption-sessions", json={"audio_source": "mic"})
    second = client.post("/api/caption-sessions", json={"audio_source": "mic"})

    assert first.json()["session_id"] != second.json()["session_id"]


@pytest.mark.parametrize(
    "payload",
    [
        {"audio_source": "speaker"},
        {"audio_source": None},
        {},
    ],
)
def test_invalid_audio_source_is_rejected(client, payload):
    response = client.post("/api/caption-sessions", json=payload)

    assert response.status_code == 422


def test_cors_allows_the_widget_dev_origin(client):
    response = client.post(
        "/api/caption-sessions",
        json={"audio_source": "mic"},
        headers={"Origin": "http://localhost:5173"},
    )

    assert (
        response.headers["access-control-allow-origin"] == "http://localhost:5173"
    )
