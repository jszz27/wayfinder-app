"""Drive the caption WebSocket from a WAV file, with no browser or mic.

Splits the file into the agreed 100 ms PCM16 chunks, sends them in the
Plan.md section 5 shape, and prints every caption that comes back. Useful
for telling a backend problem apart from a frontend one.

    python tests/manual_client.py sample.wav
    python tests/manual_client.py sample.wav --url ws://localhost:8001

The WAV must already be 16 kHz mono PCM16:
    ffmpeg -i input.mp3 -ar 16000 -ac 1 -c:a pcm_s16le sample.wav
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import uuid
import wave

import websockets

SAMPLE_RATE_HZ = 16_000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
CHUNK_MS = 100
FRAMES_PER_CHUNK = SAMPLE_RATE_HZ * CHUNK_MS // 1000


def read_pcm(path: str) -> bytes:
    with wave.open(path, "rb") as wav:
        if (
            wav.getframerate() != SAMPLE_RATE_HZ
            or wav.getnchannels() != CHANNELS
            or wav.getsampwidth() != SAMPLE_WIDTH_BYTES
        ):
            raise SystemExit(
                f"{path} is {wav.getframerate()} Hz, {wav.getnchannels()} ch, "
                f"{wav.getsampwidth() * 8}-bit; need 16000 Hz mono 16-bit. "
                "Convert it with: ffmpeg -i in.wav -ar 16000 -ac 1 "
                "-c:a pcm_s16le out.wav"
            )
        return wav.readframes(wav.getnframes())


async def receive(ws) -> None:
    async for raw in ws:
        message = json.loads(raw)
        kind = message["type"]
        if kind == "caption":
            marker = "FINAL" if message["is_final"] else "  ..."
            print(f"[{marker}] seq={message['seq']}  {message['text']}")
        elif kind == "stream_ended":
            print(f"[ END ] session {message['session_id']}")
            return
        else:
            print(f"[ERROR] {message.get('message')}")


async def stream(path: str, url: str, session_id: str, realtime: bool) -> None:
    pcm = read_pcm(path)
    chunk_bytes = FRAMES_PER_CHUNK * SAMPLE_WIDTH_BYTES

    async with websockets.connect(f"{url}/ws/caption?session_id={session_id}") as ws:
        reader = asyncio.create_task(receive(ws))

        for seq, start in enumerate(range(0, len(pcm), chunk_bytes)):
            await ws.send(
                json.dumps(
                    {
                        "type": "audio_chunk",
                        "data": base64.b64encode(
                            pcm[start : start + chunk_bytes]
                        ).decode("ascii"),
                        "seq": seq,
                        "source": "mic",
                    }
                )
            )
            if realtime:
                # Pace it like a live mic so the recogniser behaves the
                # way it will in the browser.
                await asyncio.sleep(CHUNK_MS / 1000)

        await ws.send(json.dumps({"type": "end_stream"}))
        await reader


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", help="16 kHz mono PCM16 WAV file")
    parser.add_argument("--url", default="ws://localhost:8001")
    parser.add_argument("--session-id", default=None)
    parser.add_argument(
        "--fast",
        action="store_true",
        help="send as fast as possible instead of at real-time pace",
    )
    args = parser.parse_args()

    session_id = args.session_id or str(uuid.uuid4())
    asyncio.run(stream(args.wav, args.url, session_id, realtime=not args.fast))
    return 0


if __name__ == "__main__":
    sys.exit(main())
