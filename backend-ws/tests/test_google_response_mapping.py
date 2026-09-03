"""How one Google response maps to caption lines.

Google returns consecutive portions of the audio in a single response, so
the mapping is not one caption per result. Regression cover for captions
that flickered because each portion overwrote the one before it.
"""

import pytest

pytest.importorskip("google.cloud.speech_v2")

from google.cloud.speech_v2.types import cloud_speech  # noqa: E402

from app.stt.google_v2 import results_from_response  # noqa: E402


def _response(*parts: tuple[str, bool]) -> cloud_speech.StreamingRecognizeResponse:
    return cloud_speech.StreamingRecognizeResponse(
        results=[
            cloud_speech.StreamingRecognitionResult(
                alternatives=[
                    cloud_speech.SpeechRecognitionAlternative(transcript=text)
                ],
                is_final=is_final,
            )
            for text, is_final in parts
        ]
    )


def test_consecutive_interim_portions_become_one_caption():
    # The bug: these were emitted separately, so "되고" replaced the long
    # portion on screen and the caption appeared to blink.
    out = results_from_response(_response(("긴 문장을 계속해서 얘기하게", False), (" 되고", False)))

    assert [(r.text, r.is_final) for r in out] == [
        ("긴 문장을 계속해서 얘기하게 되고", False)
    ]


def test_settled_portion_is_kept_separate_from_the_interim_tail():
    out = results_from_response(_response(("안녕하세요", True), ("잘 부탁", False)))

    assert [(r.text, r.is_final) for r in out] == [
        ("안녕하세요", True),
        ("잘 부탁", False),
    ]


def test_a_single_interim_is_unchanged():
    out = results_from_response(_response(("안녕", False)))

    assert [(r.text, r.is_final) for r in out] == [("안녕", False)]


def test_empty_and_alternative_less_results_are_skipped():
    response = cloud_speech.StreamingRecognizeResponse(
        results=[
            cloud_speech.StreamingRecognitionResult(alternatives=[], is_final=False),
            cloud_speech.StreamingRecognitionResult(
                alternatives=[cloud_speech.SpeechRecognitionAlternative(transcript="")],
                is_final=False,
            ),
            cloud_speech.StreamingRecognitionResult(
                alternatives=[
                    cloud_speech.SpeechRecognitionAlternative(transcript="실제")
                ],
                is_final=False,
            ),
        ]
    )

    assert [(r.text, r.is_final) for r in results_from_response(response)] == [
        ("실제", False)
    ]


def test_a_response_with_nothing_usable_yields_nothing():
    assert results_from_response(_response()) == []
