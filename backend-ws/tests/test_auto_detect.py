"""Automatic language detection: code mapping and the streaming wrapper."""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from app.config import Settings
from app.stt.auto import (
    DETECT_SECONDS,
    NO_FINAL_SECONDS,
    STALL_SECONDS,
    AutoDetectSttStream,
    has_speech,
)
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
        # No database, so nothing this test does is written down.
        database_url="",
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


def test_a_full_tag_with_a_region_is_passed_through():
    assert resolve_language("en-GB") == "en-GB"


@pytest.mark.parametrize(
    "detected,expected",
    [("ar-Latn", "ar-EG"), ("hi-Latn", "hi-IN"), ("ru-Cyrl", "ru-RU")],
)
def test_a_script_subtag_is_replaced_with_a_region(detected, expected):
    # chirp_2 reports Arabic speech as "ar-Latn" as often as "ar". That is
    # the right language in the wrong alphabet, and passing the script on
    # to the streaming model would waste a correct detection.
    assert resolve_language(detected) == expected


def test_a_script_subtag_on_an_unsupported_language_still_falls_back():
    assert resolve_language("xx-Latn") is None


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
        self.done = asyncio.Event()
        FakeStream.instances.append(self)

    async def push(self, pcm: bytes) -> None:
        self.pushed.append(pcm)

    async def close(self) -> None:
        self.closed = True
        self.done.set()

    #: One list of results per instance, in the order they are opened.
    scripts: list[list[SttResult]] = []
    #: When true a stream stays open after its script, as a real one does
    #: while the speaker is still talking, so a stall can be observed.
    blocking = False

    async def results(self):
        index = FakeStream.instances.index(self)
        script = (
            FakeStream.scripts[index]
            if index < len(FakeStream.scripts)
            else [SttResult(text="hello", is_final=True)]
        )
        for result in script:
            yield result
        if FakeStream.blocking:
            await self.done.wait()


@pytest.fixture
def fake_google(monkeypatch):
    FakeStream.instances = []
    FakeStream.scripts = []
    FakeStream.blocking = False
    import app.stt.google_v2 as google_v2

    monkeypatch.setattr(google_v2, "GoogleSttStream", FakeStream)
    return FakeStream


def enough_to_detect() -> bytes:
    """Just past the point where the wrapper stops buffering and detects.

    Derived from DETECT_SECONDS rather than hard-coded, so tuning the
    detection window cannot silently strand these tests below the
    threshold, where results() would wait on a detection that never runs.
    """
    return b"\x00\x00" * int(16_000 * DETECT_SECONDS + 16_000)


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

    await stream.push(enough_to_detect())
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

    audio = enough_to_detect()
    await stream.push(audio)

    pushed = fake_google.instances[0].pushed
    assert b"".join(pushed) == audio  # nothing lost, nothing reordered
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

    await stream.push(enough_to_detect())

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

    await stream.push(enough_to_detect())

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


# --- following a speaker who changes language ------------------------


def detector(*answers):
    """A detect_language stub that answers differently each time."""
    calls = {"n": 0}

    async def detect(pcm, settings):
        index = min(calls["n"], len(answers) - 1)
        calls["n"] += 1
        return answers[index]

    detect.calls = calls
    return detect


@pytest.mark.asyncio
async def test_a_confident_result_never_triggers_a_second_detection(
    fake_google, monkeypatch
):
    detect = detector("en-US")
    monkeypatch.setattr("app.stt.auto.detect_language", detect)
    FakeStream.scripts = [[SttResult(text="hello", is_final=True, confidence=0.97)]]
    stream = AutoDetectSttStream(settings())

    await stream.push(enough_to_detect())
    await drain(stream)

    assert detect.calls["n"] == 1  # the opening detection, and no more
    assert len(fake_google.instances) == 1


@pytest.mark.asyncio
async def test_a_collapsed_confidence_reopens_the_stream_in_the_new_language(
    fake_google, monkeypatch
):
    # Confidence collapses when the audio stops matching the pinned
    # language, which is how a speaker switching mid-session is noticed.
    monkeypatch.setattr(
        "app.stt.auto.detect_language", detector("en-US", "ko-KR")
    )
    FakeStream.scripts = [
        [SttResult(text="annyeonghaseyo", is_final=True, confidence=0.03)],
        [SttResult(text="\uc548\ub155\ud558\uc138\uc694", is_final=True, confidence=0.95)],
    ]
    stream = AutoDetectSttStream(settings())

    await stream.push(enough_to_detect())
    results = await drain(stream)

    assert len(fake_google.instances) == 2
    assert fake_google.instances[0].settings.stt_language == "en-US"
    assert fake_google.instances[1].settings.stt_language == "ko-KR"
    assert stream.language == "ko-KR"
    # The first result was already out before the switch was known, so it
    # keeps the language it was recognised under.
    assert [r.language for r in results] == ["en-US", "ko-KR"]


@pytest.mark.asyncio
async def test_the_misheard_audio_is_replayed_into_the_new_stream(
    fake_google, monkeypatch
):
    monkeypatch.setattr(
        "app.stt.auto.detect_language", detector("en-US", "ko-KR")
    )
    FakeStream.scripts = [
        [SttResult(text="gibberish", is_final=True, confidence=0.04)],
        [SttResult(text="fine", is_final=True, confidence=0.95)],
    ]
    stream = AutoDetectSttStream(settings())

    await stream.push(enough_to_detect())
    await drain(stream)

    # Whatever was misheard is handed to the new stream rather than lost.
    assert b"".join(fake_google.instances[1].pushed)


@pytest.mark.asyncio
async def test_the_old_stream_is_closed_after_a_switch(fake_google, monkeypatch):
    monkeypatch.setattr(
        "app.stt.auto.detect_language", detector("en-US", "ko-KR")
    )
    FakeStream.scripts = [
        [SttResult(text="gibberish", is_final=True, confidence=0.04)],
        [SttResult(text="fine", is_final=True, confidence=0.95)],
    ]
    stream = AutoDetectSttStream(settings())

    await stream.push(enough_to_detect())
    await drain(stream)

    assert fake_google.instances[0].closed is True


@pytest.mark.asyncio
async def test_unclear_audio_in_the_same_language_does_not_reopen_anything(
    fake_google, monkeypatch
):
    # Re-detection returning the language already in use means the speaker
    # mumbled, not that they switched. Restarting would lose their words
    # for no reason.
    detect = detector("en-US", "en-US")
    monkeypatch.setattr("app.stt.auto.detect_language", detect)
    FakeStream.scripts = [
        [SttResult(text="mmm", is_final=True, confidence=0.06)]
    ]
    stream = AutoDetectSttStream(settings())

    await stream.push(enough_to_detect())
    await drain(stream)

    assert detect.calls["n"] == 2  # it did look again
    assert len(fake_google.instances) == 1  # but stayed put
    assert stream.language == "en-US"


@pytest.mark.asyncio
async def test_interim_results_never_trigger_detection(fake_google, monkeypatch):
    # Only finals carry a confidence worth acting on; an interim is still
    # being revised.
    detect = detector("en-US", "ko-KR")
    monkeypatch.setattr("app.stt.auto.detect_language", detect)
    FakeStream.scripts = [
        [SttResult(text="partial", is_final=False, confidence=0.01)]
    ]
    stream = AutoDetectSttStream(settings())

    await stream.push(enough_to_detect())
    await drain(stream)

    assert detect.calls["n"] == 1
    assert len(fake_google.instances) == 1


@pytest.mark.asyncio
async def test_a_missing_confidence_is_not_read_as_a_bad_one(
    fake_google, monkeypatch
):
    # The mock adapter reports no confidence at all; that must not be
    # mistaken for a hopeless result and send the session re-detecting.
    detect = detector("en-US", "ko-KR")
    monkeypatch.setattr("app.stt.auto.detect_language", detect)
    FakeStream.scripts = [[SttResult(text="hello", is_final=True)]]
    stream = AutoDetectSttStream(settings())

    await stream.push(enough_to_detect())
    await drain(stream)

    assert detect.calls["n"] == 1
    assert len(fake_google.instances) == 1


# --- noticing a switch when no final ever arrives --------------------


def loud(seconds: float) -> bytes:
    """Audio with speech-level energy, so a stall is not read as a pause."""
    return b"\x00\x40" * int(16_000 * seconds)


@pytest.fixture
def clock(monkeypatch):
    """Drives the time-based triggers without touching the event loop."""

    class Clock:
        def __init__(self) -> None:
            self.now = 1_000.0

        def __call__(self) -> float:
            return self.now

        def advance(self, seconds: float) -> None:
            self.now += seconds

    ticker = Clock()
    monkeypatch.setattr("app.stt.auto._now", ticker)
    return ticker


async def push_chunks(stream, audio: bytes) -> None:
    """Feed audio the way the widget does, in 100 ms chunks."""
    for start in range(0, len(audio), 3_200):
        await stream.push(audio[start : start + 3_200])


async def settle() -> None:
    """Let the forwarder react to a stream that was ended under it."""
    for _ in range(12):
        await asyncio.sleep(0)


def test_speech_is_told_apart_from_a_quiet_room():
    assert has_speech(loud(0.5)) is True
    assert has_speech(b"\x00\x00" * 8_000) is False
    assert has_speech(b"") is False


@pytest.mark.asyncio
async def test_silence_from_the_recogniser_while_speaking_reopens_the_stream(
    fake_google, monkeypatch, clock
):
    # Korean into an English-pinned stream produces no results at all, so
    # there is never a final whose confidence could give the game away.
    FakeStream.blocking = True
    FakeStream.scripts = [[], [SttResult(text="fine", is_final=True, confidence=0.95)]]
    monkeypatch.setattr("app.stt.auto.detect_language", detector("en-US", "ko-KR"))
    stream = AutoDetectSttStream(settings())

    await push_chunks(stream, loud(DETECT_SECONDS + 1))
    clock.advance(STALL_SECONDS + 1)
    await push_chunks(stream, loud(0.2))
    await settle()

    assert len(fake_google.instances) == 2
    assert fake_google.instances[1].settings.stt_language == "ko-KR"
    assert stream.language == "ko-KR"


@pytest.mark.asyncio
async def test_a_line_that_never_settles_while_speaking_reopens_the_stream(
    fake_google, monkeypatch, clock
):
    # French into a German-pinned stream keeps producing plausible interims
    # and never finalises, so neither silence nor confidence appears.
    FakeStream.blocking = True
    FakeStream.scripts = [
        [SttResult(text="revising", is_final=False)],
        [SttResult(text="fine", is_final=True, confidence=0.95)],
    ]
    monkeypatch.setattr("app.stt.auto.detect_language", detector("de-DE", "fr-FR"))
    stream = AutoDetectSttStream(settings())

    await push_chunks(stream, loud(DETECT_SECONDS + 1))
    clock.advance(NO_FINAL_SECONDS + 1)
    await push_chunks(stream, loud(0.2))
    await settle()

    assert len(fake_google.instances) == 2
    assert fake_google.instances[1].settings.stt_language == "fr-FR"


@pytest.mark.asyncio
async def test_a_quiet_room_is_not_mistaken_for_a_stall(
    fake_google, monkeypatch, clock
):
    # Nobody talking also produces no results. Re-detecting on that would
    # spend a call on silence and could pin the session to a wrong guess.
    detect = detector("en-US", "ko-KR")
    monkeypatch.setattr("app.stt.auto.detect_language", detect)
    FakeStream.blocking = True
    FakeStream.scripts = [[]]
    stream = AutoDetectSttStream(settings())

    await push_chunks(stream, loud(DETECT_SECONDS + 1))
    clock.advance(STALL_SECONDS + 1)
    await stream.push(b"\x00\x00" * int(16_000 * (DETECT_SECONDS + 1)))
    await settle()

    assert detect.calls["n"] == 1  # the opening detection only
    assert len(fake_google.instances) == 1


@pytest.mark.asyncio
async def test_a_stall_in_the_same_language_does_not_reopen_anything(
    fake_google, monkeypatch, clock
):
    detect = detector("en-US", "en-US")
    monkeypatch.setattr("app.stt.auto.detect_language", detect)
    FakeStream.blocking = True
    FakeStream.scripts = [[]]
    stream = AutoDetectSttStream(settings())

    await push_chunks(stream, loud(DETECT_SECONDS + 1))
    clock.advance(STALL_SECONDS + 1)
    await push_chunks(stream, loud(0.2))
    await settle()

    assert detect.calls["n"] == 2  # it did look again
    assert len(fake_google.instances) == 1  # but stayed put
