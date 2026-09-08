"""Proving who a caption stream belongs to.

Plan.md section 5, amended in Sprint 3. Until this existed, a session id
was the whole authorisation: anyone holding one could stream audio and
have lines written into that person's transcript. An id is a name for a
stream, and names travel.

The token rides in a message rather than the query string because query
strings are written to every access log -- this project's own uvicorn logs
the full request line, `language` parameter and all.
"""

import time

import jwt
import pytest
from starlette.websockets import WebSocketDisconnect

from app.tokens import InvalidToken, read_access_token

from tests.conftest import send_chunks

SECRET = "test-secret-for-signing"
USER = "0f4d3d8e-6f2c-4a3a-9c9e-2f5a1b7c8d90"


def token(
    *,
    user=USER,
    kind="access",
    secret=SECRET,
    expires_in=900,
):
    now = int(time.time())
    payload = {"sub": user, "type": kind, "iat": now, "exp": now + expires_in}
    return jwt.encode(payload, secret, algorithm="HS256")


# --- reading a token --------------------------------------------------


def test_a_good_access_token_names_its_user():
    assert read_access_token(token(), SECRET) == USER


def test_a_token_signed_with_another_secret_is_refused():
    with pytest.raises(InvalidToken):
        read_access_token(token(secret="not-the-secret"), SECRET)


def test_an_expired_token_is_refused():
    with pytest.raises(InvalidToken):
        read_access_token(token(expires_in=-60), SECRET)


def test_a_refresh_token_is_not_an_access_token():
    # The signature would verify; the type claim is what stops it.
    with pytest.raises(InvalidToken):
        read_access_token(token(kind="refresh"), SECRET)


def test_a_token_with_no_subject_is_refused():
    now = int(time.time())
    naked = jwt.encode(
        {"type": "access", "iat": now, "exp": now + 900}, SECRET, algorithm="HS256"
    )
    with pytest.raises(InvalidToken):
        read_access_token(naked, SECRET)


def test_nonsense_is_refused():
    with pytest.raises(InvalidToken):
        read_access_token("not-a-jwt-at-all", SECRET)


def test_a_blank_secret_refuses_everything():
    # Refusing loudly beats verifying nothing: a service started without
    # JWT_SECRET must not quietly accept whatever it is handed.
    with pytest.raises(InvalidToken):
        read_access_token(token(), "")


# --- over the wire ----------------------------------------------------


@pytest.fixture
def signing(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("JWT_SECRET", SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def connect(client, session_id="auth-session"):
    return client.websocket_connect(f"/ws/caption?session_id={session_id}")


def test_a_stream_with_a_good_token_captions_normally(client, signing):
    with connect(client) as ws:
        ws.send_json({"type": "auth", "token": token()})
        send_chunks(ws, 9)
        captions = [ws.receive_json() for _ in range(3)]

    assert [c["is_final"] for c in captions] == [False, False, True]


def test_a_stream_with_no_token_still_captions(client, signing):
    # Anonymous captioning is a feature, not an oversight. It simply
    # reaches no database.
    with connect(client) as ws:
        send_chunks(ws, 9)
        captions = [ws.receive_json() for _ in range(3)]

    assert captions[-1]["is_final"] is True


def test_a_bad_token_is_refused_out_loud(client, signing):
    # Silence here would let someone caption for ten minutes and find
    # nothing saved, with no way to learn why.
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with connect(client) as ws:
            ws.send_json({"type": "auth", "token": token(secret="wrong")})
            problem = ws.receive_json()
            assert problem["type"] == "error"
            assert "sign" in problem["message"].lower()
            ws.receive_json()

    assert excinfo.value.code == 1008


def test_an_expired_token_is_refused_out_loud(client, signing):
    with pytest.raises(WebSocketDisconnect):
        with connect(client) as ws:
            ws.send_json({"type": "auth", "token": token(expires_in=-1)})
            assert ws.receive_json()["type"] == "error"
            ws.receive_json()


def test_no_audio_is_recognised_from_a_rejected_stream(client, signing):
    # The stream is closed before the receive loop starts, so a rejected
    # client cannot spend recognition quota either.
    with pytest.raises(WebSocketDisconnect):
        with connect(client) as ws:
            ws.send_json({"type": "auth", "token": "rubbish"})
            first = ws.receive_json()
            assert first["type"] == "error"
            send_chunks(ws, 9)
            ws.receive_json()


def test_identity_cannot_change_hands_mid_stream(client, signing):
    # auth is the opening frame or nothing. Accepting it later would mean
    # lines already recognised under one identity could be claimed by
    # another.
    with connect(client) as ws:
        send_chunks(ws, 3)
        ws.receive_json()
        ws.send_json({"type": "auth", "token": token()})
        problem = ws.receive_json()

    assert problem["type"] == "error"
    assert "first message" in problem["message"]


def test_a_late_auth_does_not_drop_the_stream(client, signing):
    # A confused client is not a reason to cut off someone's captions.
    with connect(client) as ws:
        send_chunks(ws, 3)
        ws.receive_json()
        ws.send_json({"type": "auth", "token": token()})
        ws.receive_json()

        send_chunks(ws, 6)
        captions = [ws.receive_json() for _ in range(2)]

    assert captions[-1]["is_final"] is True
