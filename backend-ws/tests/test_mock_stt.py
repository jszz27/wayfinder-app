from app.stt.mock import CHUNKS_PER_RESULT, MockSttStream


async def drain(stream):
    return [result async for result in stream.results()]


async def test_no_audio_yields_no_results():
    stream = MockSttStream()
    await stream.close()

    assert await drain(stream) == []


async def test_close_confirms_a_line_left_open():
    stream = MockSttStream()
    for _ in range(CHUNKS_PER_RESULT):
        await stream.push(b"\x00" * 3200)
    await stream.close()

    results = await drain(stream)

    assert [r.is_final for r in results] == [False, True]


async def test_partial_chunks_do_not_emit_a_result():
    stream = MockSttStream()
    for _ in range(CHUNKS_PER_RESULT - 1):
        await stream.push(b"\x00" * 3200)
    await stream.close()

    assert await drain(stream) == []
