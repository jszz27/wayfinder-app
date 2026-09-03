"""Round trip over the Plan.md section 5 message set, against mock STT.

The mock adapter emits one result every 3 chunks and confirms a line
every 3 results, so 9 chunks is exactly one interim/interim/final line.
"""

import pytest
from starlette.websockets import WebSocketDisconnect

from app.stt.base import SttStream

from tests.conftest import SILENT_CHUNK, send_chunks

CHUNKS_PER_RESULT = 3
RESULTS_PER_LINE = 3
CHUNKS_PER_LINE = CHUNKS_PER_RESULT * RESULTS_PER_LINE

SPEC_FIELDS = {
    "caption": {"type", "text", "is_final", "seq"},
    "error": {"type", "message"},
    "stream_ended": {"type", "session_id"},
}


def connect(client, session_id="test-session"):
    return client.websocket_connect(f"/ws/caption?session_id={session_id}")


def test_missing_session_id_is_closed_with_policy_violation(client):
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws/caption") as ws:
            ws.receive_text()

    assert excinfo.value.code == 1008


def test_audio_chunks_produce_an_interim_caption(client):
    with connect(client) as ws:
        send_chunks(ws, CHUNKS_PER_RESULT)
        caption = ws.receive_json()

    assert caption["type"] == "caption"
    assert caption["is_final"] is False
    assert caption["text"]


def test_a_line_runs_interim_interim_final(client):
    with connect(client) as ws:
        send_chunks(ws, CHUNKS_PER_LINE)
        captions = [ws.receive_json() for _ in range(RESULTS_PER_LINE)]

    assert [c["is_final"] for c in captions] == [False, False, True]
    # Interim text keeps getting revised into the confirmed sentence.
    assert captions[0]["text"] != captions[-1]["text"]


def test_seq_is_the_caption_line_ordinal(client):
    """Interim results share their line's seq; it advances after a final."""
    with connect(client) as ws:
        send_chunks(ws, CHUNKS_PER_LINE * 2)
        captions = [ws.receive_json() for _ in range(RESULTS_PER_LINE * 2)]

    first_line, second_line = captions[:RESULTS_PER_LINE], captions[RESULTS_PER_LINE:]
    assert {c["seq"] for c in first_line} == {0}
    assert {c["seq"] for c in second_line} == {1}


def test_server_messages_carry_only_the_spec_fields(client):
    with connect(client) as ws:
        send_chunks(ws, CHUNKS_PER_LINE)
        seen = [ws.receive_json() for _ in range(RESULTS_PER_LINE)]
        ws.send_json({"type": "end_stream"})
        seen.append(ws.receive_json())

    assert {m["type"] for m in seen} == {"caption", "stream_ended"}
    for message in seen:
        assert set(message) == SPEC_FIELDS[message["type"]]


def test_end_stream_flushes_the_open_line_then_acknowledges(client):
    with connect(client) as ws:
        send_chunks(ws, CHUNKS_PER_RESULT)  # one interim, line still open
        assert ws.receive_json()["is_final"] is False

        ws.send_json({"type": "end_stream"})
        flushed = ws.receive_json()
        ack = ws.receive_json()

    assert flushed["type"] == "caption"
    assert flushed["is_final"] is True
    assert flushed["seq"] == 0
    assert ack == {"type": "stream_ended", "session_id": "test-session"}


def test_end_stream_on_a_confirmed_line_acknowledges_directly(client):
    with connect(client) as ws:
        send_chunks(ws, CHUNKS_PER_LINE)
        for _ in range(RESULTS_PER_LINE):
            ws.receive_json()

        ws.send_json({"type": "end_stream"})
        ack = ws.receive_json()

    assert ack["type"] == "stream_ended"


def test_the_socket_closes_after_stream_ended(client):
    with pytest.raises(WebSocketDisconnect):
        with connect(client) as ws:
            ws.send_json({"type": "end_stream"})
            assert ws.receive_json()["type"] == "stream_ended"
            ws.receive_json()


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "start_stream"},
        {"type": "audio_chunk", "data": SILENT_CHUNK, "seq": 0},
        {"type": "audio_chunk", "data": SILENT_CHUNK, "seq": 0, "source": "speaker"},
        {"nope": True},
    ],
)
def test_an_unrecognised_message_errors_without_dropping_the_stream(client, payload):
    with connect(client) as ws:
        ws.send_json(payload)
        error = ws.receive_json()

        assert error["type"] == "error"
        assert error["message"]

        # The connection still works afterwards.
        send_chunks(ws, CHUNKS_PER_RESULT)
        assert ws.receive_json()["type"] == "caption"


def test_a_chunk_that_is_not_base64_errors_without_dropping_the_stream(client):
    with connect(client) as ws:
        ws.send_json(
            {"type": "audio_chunk", "data": "not base64!", "seq": 7, "source": "mic"}
        )
        error = ws.receive_json()

        assert error["type"] == "error"
        assert "7" in error["message"]

        send_chunks(ws, CHUNKS_PER_RESULT)
        assert ws.receive_json()["type"] == "caption"


class _ExplodingStt(SttStream):
    """A recogniser that dies as soon as results are pulled."""

    async def push(self, pcm: bytes) -> None:
        return None

    async def close(self) -> None:
        return None

    async def results(self):
        raise RuntimeError("recogniser died")
        yield  # pragma: no cover -- makes this an async generator


def test_a_recogniser_failure_reports_one_error_then_closes(client, monkeypatch):
    monkeypatch.setattr("app.main.create_stt_stream", lambda _settings: _ExplodingStt())

    with pytest.raises(WebSocketDisconnect):
        with connect(client) as ws:
            error = ws.receive_json()
            assert error["type"] == "error"
            assert set(error) == SPEC_FIELDS["error"]
            # Nothing further arrives: one error, then the socket closes.
            ws.receive_json()
