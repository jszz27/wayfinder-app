"""What actually happens when a speaker changes language mid-session.

The README claims captions follow a speaker who switches language, and
until now that claim rested on three pairs out of a hundred and ten. This
runs the rest.

For each ordered pair it synthesises a few seconds of speech in the first
language and a few in the second, joins them, streams the result through a
real caption server at the speed a microphone would, and records which
languages came back. The answer is either evidence for the claim or a list
of pairs that do not work -- both of which are better than silence.

    # a caption server with the real recogniser, on a clean port
    WAYFINDER_STT=google STT_AUTO_DETECT=true \
      uvicorn app.main:app --port 8021

    python tests/language_matrix.py --url ws://127.0.0.1:8021 --out results/

It is slow on purpose. Recognition behaves differently when audio arrives
faster than it is spoken -- the detector reads three seconds of it, and
two of the three switch triggers are wall-clock -- so the audio is paced
like a microphone. A full matrix is roughly forty minutes and costs real
money in speech API calls. `--pairs en-US:ko-KR,de-DE:fr-FR` runs a
subset.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import pathlib
import sys
import uuid
import wave
from datetime import datetime, timezone

import websockets

SAMPLE_RATE_HZ = 16_000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
CHUNK_MS = 100
CHUNK_BYTES = SAMPLE_RATE_HZ * CHUNK_MS // 1000 * SAMPLE_WIDTH_BYTES

# A beat between the two languages, so the switch is a switch rather than
# one word running into the next.
GAP_SECONDS = 0.6

# After the audio ends the recogniser still has results to finalise.
DRAIN_SECONDS = 6.0

# The eleven Wayfinder claims to support, as the streaming model names
# them. The synthesis tag differs for two: Google speaks Arabic as the
# pan-regional ar-XA, and Mandarin as cmn-CN.
LANGUAGES: dict[str, dict[str, str]] = {
    "en-US": {
        "tts": "en-US",
        "text": "Good morning everyone. Today we are going to talk about "
        "how the payment system works, and what you need to bring with you.",
    },
    "ko-KR": {
        "tts": "ko-KR",
        "text": "안녕하세요 여러분. 오늘은 결제 시스템이 어떻게 작동하는지, "
        "그리고 무엇을 가져오셔야 하는지 말씀드리겠습니다.",
    },
    "es-ES": {
        "tts": "es-ES",
        "text": "Buenos días a todos. Hoy vamos a hablar sobre cómo funciona "
        "el sistema de pagos y qué necesitan traer con ustedes.",
    },
    "cmn-Hans-CN": {
        "tts": "cmn-CN",
        "text": "大家早上好。今天我们要讲一讲支付系统是如何运作的，以及您需要带些什么。",
    },
    "ja-JP": {
        "tts": "ja-JP",
        "text": "皆さん、おはようございます。今日は決済システムの仕組みと、"
        "何を持ってくる必要があるかについてお話しします。",
    },
    "fr-FR": {
        "tts": "fr-FR",
        "text": "Bonjour à tous. Aujourd'hui, nous allons parler du "
        "fonctionnement du système de paiement et de ce que vous devez apporter.",
    },
    "hi-IN": {
        "tts": "hi-IN",
        "text": "सभी को सुप्रभात। आज हम बात करेंगे कि भुगतान प्रणाली कैसे काम करती है, "
        "और आपको अपने साथ क्या लाना होगा।",
    },
    "ar-EG": {
        "tts": "ar-XA",
        "text": "صباح الخير جميعا. اليوم سوف نتحدث عن كيفية عمل نظام الدفع، "
        "وما الذي تحتاج إلى إحضاره معك.",
    },
    "pt-BR": {
        "tts": "pt-BR",
        "text": "Bom dia a todos. Hoje vamos falar sobre como funciona o "
        "sistema de pagamento e o que vocês precisam trazer.",
    },
    "de-DE": {
        "tts": "de-DE",
        "text": "Guten Morgen zusammen. Heute sprechen wir darüber, wie das "
        "Zahlungssystem funktioniert und was Sie mitbringen müssen.",
    },
    "ru-RU": {
        "tts": "ru-RU",
        "text": "Доброе утро всем. Сегодня мы поговорим о том, как работает "
        "платёжная система и что вам нужно взять с собой.",
    },
}


def synthesise(tag: str, cache: pathlib.Path) -> bytes:
    """Speech in one language, as raw 16 kHz mono PCM16. Cached on disk.

    Eleven syntheses serve a hundred and ten pairs, so the cache is worth
    keeping between runs -- and it makes the matrix reproducible, since
    every pair then hears exactly the same audio.
    """
    from google.cloud import texttospeech

    path = cache / f"{tag}.wav"
    if path.exists():
        with wave.open(str(path), "rb") as wav:
            return wav.readframes(wav.getnframes())

    spec = LANGUAGES[tag]
    client = texttospeech.TextToSpeechClient()
    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=spec["text"]),
        voice=texttospeech.VoiceSelectionParams(language_code=spec["tts"]),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=SAMPLE_RATE_HZ,
        ),
    )
    # LINEAR16 comes back with a WAV header. Read it back rather than
    # guessing where the header ends.
    cache.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.audio_content)
    with wave.open(str(path), "rb") as wav:
        return wav.readframes(wav.getnframes())


async def run_pair(url: str, first: bytes, second: bytes) -> list[dict]:
    """Stream one language then another, and collect what came back."""
    silence = b"\x00" * (int(GAP_SECONDS * SAMPLE_RATE_HZ) * SAMPLE_WIDTH_BYTES)
    pcm = first + silence + second
    seen: list[dict] = []

    async with websockets.connect(
        f"{url}/ws/caption?session_id={uuid.uuid4()}", max_size=None
    ) as ws:

        async def receive() -> None:
            async for raw in ws:
                message = json.loads(raw)
                if message["type"] == "caption":
                    seen.append(
                        {
                            "text": message["text"],
                            "language": message.get("language"),
                            "is_final": message["is_final"],
                        }
                    )
                elif message["type"] == "stream_ended":
                    return

        reader = asyncio.create_task(receive())
        for seq, start in enumerate(range(0, len(pcm), CHUNK_BYTES)):
            await ws.send(
                json.dumps(
                    {
                        "type": "audio_chunk",
                        "data": base64.b64encode(
                            pcm[start : start + CHUNK_BYTES]
                        ).decode("ascii"),
                        "seq": seq,
                        "source": "mic",
                    }
                )
            )
            # Paced like a microphone: recognition behaves differently
            # when audio arrives faster than it is spoken.
            await asyncio.sleep(CHUNK_MS / 1000)

        await asyncio.sleep(DRAIN_SECONDS)
        await ws.send(json.dumps({"type": "end_stream"}))
        try:
            await asyncio.wait_for(reader, timeout=15)
        except asyncio.TimeoutError:
            reader.cancel()
    return seen


def score(source: str, target: str, seen: list[dict]) -> dict:
    """Did it hear the first language, and then follow to the second?"""
    languages = [r["language"] for r in seen if r["language"]]
    ordered: list[str] = []
    for language in languages:
        if not ordered or ordered[-1] != language:
            ordered.append(language)

    heard_source = source in ordered
    heard_target = target in ordered
    followed = (
        heard_source and heard_target and ordered.index(target) > ordered.index(source)
    )
    return {
        "from": source,
        "to": target,
        "sequence": ordered,
        "heard_from": heard_source,
        "heard_to": heard_target,
        "switched": followed,
        "captions": len([r for r in seen if r["is_final"]]),
    }


def render(results: list[dict], tags: list[str]) -> str:
    """A grid: rows are the language spoken first, columns the one after."""
    by_pair = {(r["from"], r["to"]): r for r in results}
    short = {t: t.split("-")[0] for t in tags}
    lines = ["| from \\ to | " + " | ".join(short[t] for t in tags) + " |"]
    lines.append("| --- |" + " --- |" * len(tags))
    for source in tags:
        cells = []
        for target in tags:
            if source == target:
                cells.append("·")
                continue
            result = by_pair.get((source, target))
            cells.append(
                "—" if result is None else ("yes" if result["switched"] else "no")
            )
        lines.append(f"| **{short[source]}** | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="ws://127.0.0.1:8021")
    parser.add_argument("--out", default="results")
    parser.add_argument(
        "--pairs", help="Comma-separated from:to pairs. Omit to run all 110."
    )
    args = parser.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "audio"

    tags = list(LANGUAGES)
    if args.pairs:
        wanted = [tuple(p.split(":")) for p in args.pairs.split(",")]
    else:
        wanted = [(a, b) for a in tags for b in tags if a != b]

    print(f"synthesising {len(tags)} languages...", flush=True)
    audio = {tag: synthesise(tag, cache) for tag in tags}
    for tag in tags:
        seconds = len(audio[tag]) / (SAMPLE_RATE_HZ * SAMPLE_WIDTH_BYTES)
        print(f"  {tag:12} {seconds:.1f}s", flush=True)

    results: list[dict] = []
    for index, (source, target) in enumerate(wanted, start=1):
        print(f"[{index}/{len(wanted)}] {source} -> {target}", end="", flush=True)
        try:
            seen = await run_pair(args.url, audio[source], audio[target])
            result = score(source, target, seen)
        except Exception as error:  # noqa: BLE001 - a failed pair is a result
            result = {
                "from": source,
                "to": target,
                "sequence": [],
                "heard_from": False,
                "heard_to": False,
                "switched": False,
                "error": str(error)[:200],
            }
        results.append(result)
        print(
            f"  {'followed' if result['switched'] else 'did not follow'}"
            f"  {result['sequence']}",
            flush=True,
        )
        # Written after every pair, so a run that is interrupted still
        # leaves everything it learned.
        (out / "matrix.json").write_text(
            json.dumps(
                {
                    "generated": datetime.now(timezone.utc).isoformat(),
                    "pairs": results,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (out / "matrix.md").write_text(render(results, tags), encoding="utf-8")

    followed = sum(1 for r in results if r["switched"])
    print(f"\n{followed} of {len(results)} pairs followed the speaker.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
