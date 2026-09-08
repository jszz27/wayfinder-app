"""Pinning a caption language, and what it turns off.

Plan.md section 5, amended in Sprint 3: the socket takes an optional
`language`. The property worth protecting is that pinning *replaces*
detection rather than sitting alongside it -- a detector that could still
override the choice would make the setting advisory.
"""

import dataclasses

import pytest

from app.config import Settings
from app.main import for_language

from tests.conftest import send_chunks


def settings(**changes) -> Settings:
    base = Settings(
        stt_backend="mock",
        stt_language="ko-KR",
        stt_model="long",
        stt_auto_detect=True,
        google_project=None,
        google_location="global",
        google_detect_location="us-central1",
        cors_origins=(),
        database_url="",
        jwt_secret="",
    )
    return dataclasses.replace(base, **changes)


# --- what pinning does ------------------------------------------------


def test_no_language_leaves_the_server_configuration_alone():
    configured = settings()

    assert for_language(configured, None) is configured


def test_a_pinned_language_is_the_one_the_recogniser_gets():
    pinned = for_language(settings(), "ja-JP")

    assert pinned.stt_language == "ja-JP"


def test_pinning_turns_detection_off():
    # The whole point: someone who has said what they are speaking is
    # telling us not to guess.
    pinned = for_language(settings(stt_auto_detect=True), "ja-JP")

    assert pinned.stt_auto_detect is False


def test_pinning_changes_nothing_else():
    configured = settings()

    pinned = for_language(configured, "de-DE")

    assert dataclasses.replace(
        pinned, stt_language=configured.stt_language, stt_auto_detect=True
    ) == configured


@pytest.mark.parametrize("tag", ["cmn-Hans-CN", "pt-BR", "ar-EG", "en"])
def test_the_tags_the_widget_offers_are_all_accepted(tag):
    assert for_language(settings(), tag).stt_language == tag


# --- what it refuses to break -----------------------------------------


@pytest.mark.parametrize("tag", ["", "   ", "en_US", "!!", "en-US;drop"])
def test_a_tag_that_is_not_one_is_ignored_rather_than_fatal(tag):
    # A preference must never be the reason captions do not start.
    configured = settings()

    assert for_language(configured, tag) is configured


def test_whitespace_around_a_tag_is_forgiven():
    assert for_language(settings(), " ko-KR ").stt_language == "ko-KR"


# --- over the wire ----------------------------------------------------


def test_captioning_still_runs_with_a_language_pinned(client):
    with client.websocket_connect(
        "/ws/caption?session_id=pinned-session&language=ko-KR"
    ) as ws:
        send_chunks(ws, 9)
        captions = [ws.receive_json() for _ in range(3)]

    assert [c["is_final"] for c in captions] == [False, False, True]
    # Plan.md section 5: language is reported only when it was detected.
    # It was configured here, so there is nothing to report.
    assert all(c["language"] is None for c in captions)


def test_a_malformed_language_does_not_stop_the_session(client):
    with client.websocket_connect(
        "/ws/caption?session_id=bad-language&language=%21%21"
    ) as ws:
        send_chunks(ws, 9)
        captions = [ws.receive_json() for _ in range(3)]

    assert captions[-1]["is_final"] is True
