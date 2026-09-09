"""One caption session, across however many recognition streams it takes.

Plan.md section 12, Sprint 5. Google caps a streaming recognition at a few
minutes and this app captions lectures, so the end of a stream cannot be
the end of the session. Before this it was: a raising stream closed the
socket mid-sentence, and a stream that merely finished stopped the
captions with no error at all, which is the worse of the two.

The fake below ends on demand, so the recovery is provable in a
millisecond rather than in five minutes.
"""

import pytest

from app.stt.base import SttResult, SttStream
from app.stt.resilient import MAX_REOPENS, ResilientSttStream


class Ending(SttStream):
    """Yields a few results, then ends the way a capped stream does.

    The count is `emits`, not `results`: an attribute called `results`
    would shadow the `results()` method this class exists to provide, and
    the wrapper would call an integer.
    """

    def __init__(self, label, emits=2, raises=None):
        self.label = label
        self.emits = emits
        self.raises = raises
        self.pushed = []
        self.closed = False

    async def push(self, pcm):
        self.pushed.append(pcm)

    async def results(self):
        for index in range(self.emits):
            yield SttResult(text=f"{self.label}-{index}", is_final=True)
        if self.raises:
            raise self.raises

    async def close(self):
        self.closed = True


def opener(streams):
    """Hands out the given streams in order, then silent ones for ever.

    Never exhausts: raising StopIteration inside a coroutine turns into a
    confusing RuntimeError, which says nothing about the recogniser.
    """
    made = list(streams)
    handed = []

    def open_stream():
        stream = made.pop(0) if made else Ending("spare", emits=0)
        handed.append(stream)
        return stream

    open_stream.handed = handed
    return open_stream


async def collect(stream, limit=50):
    out = []
    async for result in stream.results():
        out.append(result.text)
        if len(out) >= limit:
            break
    return out


# --- surviving the end of a stream ------------------------------------


@pytest.mark.asyncio
async def test_a_stream_that_simply_ends_does_not_end_the_session():
    # The silent case: no exception, just a finished iterator. This is
    # what made captions stop with nothing on screen to explain it.
    first, second = Ending("a"), Ending("b", emits=0)
    resilient = ResilientSttStream(opener([first, second]))

    texts = await collect(resilient, limit=2)
    assert texts == ["a-0", "a-1"]


@pytest.mark.asyncio
async def test_captions_carry_on_into_the_replacement_stream():
    first, second = Ending("a"), Ending("b")
    resilient = ResilientSttStream(opener([first, second, Ending("c", emits=0)]))

    assert await collect(resilient, limit=4) == ["a-0", "a-1", "b-0", "b-1"]


@pytest.mark.asyncio
async def test_a_stream_that_raises_is_replaced_too():
    first = Ending("a", raises=RuntimeError("stream broke"))
    resilient = ResilientSttStream(opener([first, Ending("b")]))

    assert await collect(resilient, limit=4) == ["a-0", "a-1", "b-0", "b-1"]


@pytest.mark.asyncio
async def test_the_old_stream_is_closed_when_it_is_replaced():
    first, second = Ending("a"), Ending("b")
    resilient = ResilientSttStream(opener([first, second]))

    await collect(resilient, limit=3)

    assert first.closed is True


# --- not losing what was said across the seam -------------------------


@pytest.mark.asyncio
async def test_recent_audio_is_replayed_into_the_replacement():
    # A word spoken as the stream ended would otherwise be dropped: the
    # old stream is gone and the new one never heard it.
    first, second = Ending("a"), Ending("b")
    resilient = ResilientSttStream(opener([first, second, Ending("c", emits=0)]))
    for _ in range(4):
        await resilient.push(b"\x01" * 3200)

    await collect(resilient, limit=3)

    assert second.pushed, "the replacement stream heard nothing of what came before"
    assert b"".join(second.pushed) == b"\x01" * 12800


@pytest.mark.asyncio
async def test_the_replay_is_split_small_enough_for_the_api():
    # Google rejects a request carrying more than 25,600 bytes of audio.
    first, second = Ending("a"), Ending("b")
    resilient = ResilientSttStream(opener([first, second, Ending("c", emits=0)]))
    for _ in range(30):
        await resilient.push(b"\x02" * 3200)

    await collect(resilient, limit=3)

    assert second.pushed
    assert max(len(chunk) for chunk in second.pushed) <= 25_600


@pytest.mark.asyncio
async def test_only_the_recent_past_is_replayed():
    # Replaying the whole session would repeat sentences the listener has
    # already read, and would grow without limit.
    first, second = Ending("a"), Ending("b")
    resilient = ResilientSttStream(opener([first, second, Ending("c", emits=0)]))
    for _ in range(200):
        await resilient.push(b"\x03" * 3200)

    await collect(resilient, limit=3)

    replayed = sum(len(chunk) for chunk in second.pushed)
    assert replayed < 200 * 3200
    # Two seconds of 16 kHz mono PCM16, give or take one chunk.
    assert replayed <= 64_000 + 3_200


# --- knowing when to stop ---------------------------------------------


@pytest.mark.asyncio
async def test_a_recogniser_that_keeps_dying_is_given_up_on():
    # Reopening forever would hide a broken recogniser behind an endless
    # stream of nothing.
    streams = [Ending(str(n), emits=0) for n in range(MAX_REOPENS + 5)]
    resilient = ResilientSttStream(opener(streams))

    assert await collect(resilient) == []
    assert sum(1 for s in streams if s.closed) <= MAX_REOPENS


@pytest.mark.asyncio
async def test_closing_the_session_does_not_open_another_stream():
    # The ordinary end of a session: the caller closed it, so a stream
    # ending is the close working, not a failure to recover from.
    first = Ending("a", emits=0)
    resilient = ResilientSttStream(opener([first]))
    await resilient.close()

    assert await collect(resilient) == []
    assert first.closed is True
