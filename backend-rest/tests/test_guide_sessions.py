"""Plan.md section 4: the four /api/guide/* routes.

The mock guide model backs these, so the endpoints, the conversation
history, and the screenshot path are all covered without a cloud project.
"""

import base64
import uuid

import pytest

from app.routers.guide_sessions import MAX_SCREENSHOT_BYTES

# A real 1x1 PNG, so the decode path is exercised on actual image bytes.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
    "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PNG_1X1_B64 = base64.b64encode(PNG_1X1).decode()


def start(client) -> str:
    response = client.post("/api/guide/sessions")
    assert response.status_code == 201
    return response.json()["session_id"]


def send(client, session_id, content="Which button do I press?", screenshot=None):
    payload = {"content": content}
    if screenshot is not None:
        payload["screenshot"] = screenshot
    return client.post(f"/api/guide/sessions/{session_id}/messages", json=payload)


# --- starting a session -----------------------------------------------


def test_start_returns_a_uuid(client):
    session_id = start(client)
    uuid.UUID(session_id)


def test_each_session_gets_a_distinct_id(client):
    assert start(client) != start(client)


def test_a_new_session_has_no_messages(client):
    session_id = start(client)

    body = client.get(f"/api/guide/sessions/{session_id}").json()

    assert body["messages"] == []
    assert body["completed_at"] is None


# --- sending a message ------------------------------------------------


def test_sending_a_question_returns_the_assistant_reply(client):
    session_id = start(client)

    response = send(client, session_id, "How do I send money?")

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "assistant"
    assert body["content"]
    uuid.UUID(body["id"])


def test_both_turns_are_recorded_in_order(client):
    session_id = start(client)
    send(client, session_id, "How do I send money?")

    messages = client.get(f"/api/guide/sessions/{session_id}").json()["messages"]

    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "How do I send money?"


def test_history_accumulates_across_turns(client):
    session_id = start(client)
    send(client, session_id, "First question")
    send(client, session_id, "Second question")

    messages = client.get(f"/api/guide/sessions/{session_id}").json()["messages"]

    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert [m["content"] for m in messages][::2] == [
        "First question",
        "Second question",
    ]


def test_earlier_turns_are_passed_to_the_model(client):
    # The mock counts user turns, so a rising count proves the history
    # reached it rather than each question being answered in isolation.
    session_id = start(client)
    first = send(client, session_id, "First").json()["content"]
    second = send(client, session_id, "Second").json()["content"]

    assert "reply 1" in first
    assert "reply 2" in second


@pytest.mark.parametrize("content", ["", "x" * 4001])
def test_an_empty_or_oversized_question_is_rejected(client, content):
    session_id = start(client)

    response = send(client, session_id, content)

    assert response.status_code == 422


def test_a_question_for_an_unknown_session_is_404(client):
    response = send(client, str(uuid.uuid4()))

    assert response.status_code == 404


# --- the screenshot path (Plan.md section 10) -------------------------


def test_a_screenshot_reaches_the_model(client):
    session_id = start(client)

    without = send(client, session_id, "Help").json()["content"]
    with_shot = send(client, session_id, "Help", screenshot=PNG_1X1_B64).json()[
        "content"
    ]

    assert "cannot see your screen" in without
    assert "I can see your screen" in with_shot


def test_a_data_url_screenshot_is_accepted(client):
    # A canvas hands the browser a data URL, so the server takes one as-is.
    session_id = start(client)

    response = send(
        client, session_id, "Help", screenshot=f"data:image/png;base64,{PNG_1X1_B64}"
    )

    assert response.status_code == 201
    assert "I can see your screen" in response.json()["content"]


def test_the_screenshot_is_never_stored(client):
    # Plan.md section 10: only the response text is logged, so sensitive
    # on-screen content is not retained.
    session_id = start(client)
    send(client, session_id, "Help", screenshot=PNG_1X1_B64)

    body = client.get(f"/api/guide/sessions/{session_id}").json()

    assert "screenshot" not in str(body)
    for message in body["messages"]:
        assert set(message) == {"id", "role", "content", "created_at"}
        assert PNG_1X1_B64 not in message["content"]


def test_a_malformed_screenshot_is_rejected(client):
    session_id = start(client)

    response = send(client, session_id, "Help", screenshot="not base64 at all!!")

    assert response.status_code == 422


def test_an_unsupported_image_type_is_rejected(client):
    session_id = start(client)

    response = send(
        client, session_id, "Help", screenshot=f"data:image/gif;base64,{PNG_1X1_B64}"
    )

    assert response.status_code == 422


def test_an_oversized_screenshot_is_rejected(client):
    session_id = start(client)
    too_big = base64.b64encode(b"\x00" * (MAX_SCREENSHOT_BYTES + 1)).decode()

    response = send(client, session_id, "Help", screenshot=too_big)

    assert response.status_code == 413


# --- completing a session ---------------------------------------------


def test_completing_sets_completed_at(client):
    session_id = start(client)

    response = client.patch(f"/api/guide/sessions/{session_id}/complete")

    assert response.status_code == 200
    assert response.json()["completed_at"] is not None


def test_completing_twice_keeps_the_first_timestamp(client):
    session_id = start(client)
    first = client.patch(f"/api/guide/sessions/{session_id}/complete").json()
    second = client.patch(f"/api/guide/sessions/{session_id}/complete").json()

    assert first["completed_at"] == second["completed_at"]


def test_a_completed_session_takes_no_more_questions(client):
    session_id = start(client)
    client.patch(f"/api/guide/sessions/{session_id}/complete")

    response = send(client, session_id)

    assert response.status_code == 409


def test_a_completed_session_still_returns_its_history(client):
    session_id = start(client)
    send(client, session_id, "Before completing")
    client.patch(f"/api/guide/sessions/{session_id}/complete")

    body = client.get(f"/api/guide/sessions/{session_id}").json()

    assert len(body["messages"]) == 2


@pytest.mark.parametrize("method,suffix", [("get", ""), ("patch", "/complete")])
def test_unknown_sessions_are_404(client, method, suffix):
    response = getattr(client, method)(f"/api/guide/sessions/{uuid.uuid4()}{suffix}")

    assert response.status_code == 404
