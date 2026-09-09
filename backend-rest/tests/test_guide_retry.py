"""Asking the model again when it was busy, and not when it refused.

Plan.md section 12, Sprint 5. The distinction is the whole point: a
service having a moment is worth a second attempt, a request the model has
already refused is not, and someone standing at a cash machine waiting for
the next step notices the difference.
"""

import time

import pytest

from app.guide.base import GuideModel, GuideTurn
from app.guide.retry import RetryingGuideModel


class Flaky(GuideModel):
    """Fails a set number of times, then answers."""

    def __init__(self, failures, error=None, transient=True):
        self.failures = failures
        self.error = error or RuntimeError("service unavailable")
        self.transient = transient
        self.calls = 0

    async def respond(self, history, question, screenshot, screenshot_mime):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return f"answered on attempt {self.calls}"

    def is_transient(self, error):
        return self.transient


async def ask(model):
    return await model.respond(
        history=[GuideTurn(role="user", content="earlier")],
        question="What do I press?",
        screenshot=None,
        screenshot_mime=None,
    )


# --- when it is worth asking again ------------------------------------


@pytest.mark.asyncio
async def test_one_hiccup_is_not_a_failure(api):
    inner = Flaky(failures=1)

    answer = await ask(RetryingGuideModel(inner, delays=(0, 0)))

    assert answer == "answered on attempt 2"
    assert inner.calls == 2


@pytest.mark.asyncio
async def test_two_hiccups_are_still_survivable(api):
    inner = Flaky(failures=2)

    answer = await ask(RetryingGuideModel(inner, delays=(0, 0)))

    assert answer == "answered on attempt 3"


@pytest.mark.asyncio
async def test_a_model_that_answers_first_time_is_asked_once(api):
    inner = Flaky(failures=0)

    await ask(RetryingGuideModel(inner, delays=(0, 0)))

    assert inner.calls == 1


# --- when it is not --------------------------------------------------


@pytest.mark.asyncio
async def test_a_refusal_is_not_retried(api):
    # The model already decided. Asking again spends the user's time to
    # reach the same answer.
    inner = Flaky(failures=99, transient=False)

    with pytest.raises(RuntimeError):
        await ask(RetryingGuideModel(inner, delays=(0, 0)))

    assert inner.calls == 1


@pytest.mark.asyncio
async def test_retrying_gives_up_rather_than_hanging_on(api):
    inner = Flaky(failures=99, transient=True)

    with pytest.raises(RuntimeError):
        await ask(RetryingGuideModel(inner, delays=(0, 0)))

    # Three attempts in total, not an unbounded loop.
    assert inner.calls == 3


@pytest.mark.asyncio
async def test_the_original_error_is_what_surfaces(api):
    # Not a retry-wrapper error: whatever the endpoint logs should be the
    # thing that actually went wrong.
    boom = ValueError("the model said no")
    inner = Flaky(failures=99, error=boom, transient=False)

    with pytest.raises(ValueError) as caught:
        await ask(RetryingGuideModel(inner, delays=(0, 0)))

    assert caught.value is boom


# --- how long the user waits ------------------------------------------


@pytest.mark.asyncio
async def test_the_whole_retry_budget_stays_under_two_seconds(api):
    # Sprint 1 settled that a five-second delay makes the product feel
    # broken. A failing answer must not take longer than a working one
    # plus a moment.
    from app.guide.retry import RETRY_DELAYS_SECONDS

    assert sum(RETRY_DELAYS_SECONDS) < 2.0


@pytest.mark.asyncio
async def test_a_failure_does_not_stall_the_request(api):
    inner = Flaky(failures=99, transient=True)
    started = time.monotonic()

    with pytest.raises(RuntimeError):
        await ask(RetryingGuideModel(inner))

    assert time.monotonic() - started < 2.0


# --- which Gemini failures count as busy ------------------------------


def gemini():
    """The adapter, constructed without touching the SDK.

    google-genai is imported inside respond(), so classifying an error
    needs no cloud project reachable and no credentials.
    """
    import dataclasses

    from app.config import get_settings
    from app.guide.gemini import GeminiGuideModel

    settings = dataclasses.replace(get_settings(), google_project="a-project")
    return GeminiGuideModel(settings)


class ApiError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


@pytest.mark.parametrize("code", [429, 500, 503, 504])
def test_a_busy_service_is_worth_asking_again(code):
    assert gemini().is_transient(ApiError("busy", code=code)) is True


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_a_refusal_is_not(code):
    # 400 is a request it will refuse again; 403 is a permission that will
    # not appear by itself.
    assert gemini().is_transient(ApiError("no", code=code)) is False


def test_a_status_carried_only_in_the_message_still_counts():
    # Some google-genai versions raise without a code attribute.
    error = Exception("503 UNAVAILABLE: The service is currently unavailable.")
    assert gemini().is_transient(error) is True


def test_a_safety_block_is_a_decision_not_a_hiccup():
    error = Exception("Response blocked by safety filters")
    assert gemini().is_transient(error) is False


def test_an_empty_answer_is_not_retried():
    # Raised by the adapter itself when the model returns nothing. Asking
    # again would probably get nothing again.
    assert gemini().is_transient(RuntimeError("The guide model returned an empty answer.")) is False
