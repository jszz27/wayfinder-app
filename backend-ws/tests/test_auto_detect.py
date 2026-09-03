"""Automatic language detection: code mapping and the streaming wrapper."""

from __future__ import annotations

import dataclasses

import pytest

from app.config import Settings
from app.stt.auto import AutoDetectSttStream
from app.stt.base import SttResult, SttStream
from app.stt.detect import resolve_language


def settings(**overrides) -> Settings:
    base = dict(
        stt_backend="google",
        stt_language="en-US",
        stt_model="long",
        stt_auto_detect=True,
        google_project="demo",
        google_location="global",
        google_detect_location="us-central1",
        cors_origins=("http://localhost:5173",),
    )
    return Settings(**{**base, **overrides})


# --- code mapping -----------------------------------------------------


@pytest.mark.parametrize(
    "detected,expected",
    [
        ("en", "en-US"),
        ("ko", "ko-KR"),
        ("es", "es-ES"),
        ("ja", "ja-JP"),
        ("fr", "fr-FR"),
        ("hi", "hi-IN"),
        ("ar", "ar-EG"),
        ("pt", "pt-BR"),
        ("de", "de-DE"),
        ("ru", "ru-RU"),
    ],
)
def test_bare_subtags_gain_the_region_the_streaming_model_wants(detected, expected):
    assert resolve_language(detected) == expected


@pytest.mark.parametrize("detected", ["cmn", "zh", "cmn-Hans", "yue"])
def test_chinese_is_normalised_to_the_one_tag_the_model_accepts(detected):
    assert resolve_language(detected) == "cmn-Hans-CN"


def test_a_full_tag_is_passed_through():
    assert resolve_language("en-GB") == "en-GB"


@pytest.mark.parametrize("detected", [None, "", "   ", "xx"])
def test_unknown_languages_return_none_so_the_caller_can_fall_back(detected):
    assert resolve_language(detected) is None


# --- the streaming wrapper --------------------------------------------


class FakeStream(SttStream):
    """Stands in for GoogleSttStream, recording what it was handed."""

    instances: list["FakeStream"] = []

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.pushed: list[bytes] = []
        self.closed = False
        FakeStream.instances.append(self)

    async def push(self, pcm: bytes) -> None:
        self.pushed.append(pcm)

    async def close(self) -> None:
        self.closed = True

    async def results(self):
        yield SttResult(text="hello", is_final=True)


@pytest.fixture
def fake_google(monkeypatch):
    FakeStream.instances = []
    import app.stt.google_v2 as google_v2

    monkeypatch.setattr(google_v2, "GoogleSttStream", FakeStream)
    return FakeStream


def one_second() -> bytes:
    return b"\x00\x00" * 16_000


async def drain(stream: AutoDetectSttStream) -> list[SttResult]:
    return [r async for r in stream.results()]


@pytest.mark.asyncio
async def test_nothing_is_sent_upstream_until_enough_audio_to_detect(
    fake_google, monkeypatch
):
    async def never_called(pcm, settings):  # pragma: no cover - must not run
        raise AssertionError("detection ran before the buffer was full")

    monkeypatch.setattr("app.stt.auto.detect_language", never_called)
    stream = AutoDetectSttStream(settings())

    await stream.push(b"\x00\x00" * 8_000)  # half a second

    assert fake_google.instances == []


@pytest.mark.asyncio
async def test_detected_language_pins_the_stream_and_tags_results(
    fake_google, monkeypatch
):
    async def detects_korean(pcm, settings):
        return "ko-KR"

    monkeypatch.setattr("app.stt.auto.detect_language", detects_korean)
    stream = AutoDetectSttStream(settings(stt_language="en-US"))

    await stream.push(one_second())
    await stream.push(one_second())
    results = await drain(stream)

    assert stream.language == "ko-KR"
    assert fake_google.instances[0].settings.stt_language == "ko-KR"
    assert [r.language for r in results] == ["ko-KR"]


@pytest.mark.asyncio
async def test_buffered_audio_is_replayed_so_the_opening_words_survive(
    fake_google, monkeypatch
):
    async def detects(pcm, settings):
        return "en-US"

    monkeypatch.setattr("app.stt.auto.detect_language", detects)
    stream = AutoDetectSttStream(settings())

    await stream.push(one_second())
    await stream.push(one_second())

    pushed = fake_google.instances[0].pushed
    assert b"".join(pushed) == one_second() * 2  # nothing lost, nothing reordered
    # Google rejects a streaming chunk over 25 600 bytes, so the replay has
    # to be split; pushing the whole buffer at once fails the live stream.
    assert pushed and max(len(chunk) for chunk in pushed) <= 25_600


@pytest.mark.asyncio
async def test_a_failed_detection_falls_back_instead_of_killing_the_session(
    fake_google, monkeypatch
):
    async def explodes(pcm, settings):
        raise RuntimeError("detection unavailable")

    monkeypatch.setattr("app.stt.auto.detect_language", explodes)
    stream = AutoDetectSttStream(settings(stt_language="ko-KR"))

    await stream.push(one_second())
    await stream.push(one_second())

    assert stream.language == "ko-KR"
    assert fake_google.instances[0].settings.stt_language == "ko-KR"


@pytest.mark.asyncio
async def test_an_unrecognised_language_falls_back_to_the_configured_one(
    fake_google, monkeypatch
):
    async def detects_nothing(pcm, settings):
        return None

    monkeypatch.setattr("app.stt.auto.detect_language", detects_nothing)
    stream = AutoDetectSttStream(settings(stt_language="en-US"))

    await stream.push(one_second())
    await stream.push(one_second())

    assert stream.language == "en-US"


@pytest.mark.asyncio
async def test_a_short_utterance_still_detects_when_the_stream_closes(
    fake_google, monkeypatch
):
    async def detects(pcm, settings):
        return "fr-FR"

    monkeypatch.setattr("app.stt.auto.detect_language", detects)
    stream = AutoDetectSttStream(settings())

    await stream.push(b"\x00\x00" * 4_000)  # a quarter second, then stop
    await stream.close()

    assert stream.language == "fr-FR"
    assert fake_google.instances[0].closed is True


@pytest.mark.asyncio
async def test_closing_without_any_audio_yields_nothing_and_opens_no_session(
    fake_google, monkeypatch
):
    async def never_called(pcm, settings):  # pragma: no cover - must not run
        raise AssertionError("detection ran with no audio")

    monkeypatch.setattr("app.stt.auto.detect_language", never_called)
    stream = AutoDetectSttStream(settings())

    await stream.close()

    assert await drain(stream) == []
    assert fake_google.instances == []
