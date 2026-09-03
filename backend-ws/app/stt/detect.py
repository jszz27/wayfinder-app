"""Works out which language is being spoken, once, at the top of a session.

Google offers no single streaming model that both detects a language and
returns interim results. The `long` model streams partial text every
100-200 ms but must be told the language up front; `chirp_2` detects a
language from `auto` but emits nothing until an utterance ends, which
would turn live captions into five-second blocks.

So the two are used for what each is good at: one short synchronous
`chirp_2` call names the language, and the streaming session is then
pinned to it. Detection costs about a second, once, rather than a delay
on every sentence.
"""

from __future__ import annotations

import logging

from app.config import CHANNELS, SAMPLE_RATE_HZ, Settings

logger = logging.getLogger(__name__)

# Detection is only offered on regional endpoints; "global" has no chirp_2.
_DETECT_MODEL = "chirp_2"

# chirp_2 answers with a bare subtag ("en"), while the streaming model wants
# a full tag. These are the languages Wayfinder claims to support; anything
# else falls back to STT_LANGUAGE.
_DEFAULT_REGION = {
    "en": "en-US",
    "ko": "ko-KR",
    "es": "es-ES",
    "ja": "ja-JP",
    "fr": "fr-FR",
    "hi": "hi-IN",
    "ar": "ar-EG",
    "pt": "pt-BR",
    "de": "de-DE",
    "ru": "ru-RU",
}


def resolve_language(detected: str | None) -> str | None:
    """Turn a detected code into one the streaming model accepts.

    Returns None when the language is not one we support, which leaves the
    caller to fall back rather than pin the stream to something `long`
    would reject mid-session.
    """
    if not detected:
        return None
    parts = detected.strip().split("-")
    primary = parts[0].lower()
    if not primary:
        return None
    if primary in ("cmn", "zh", "yue"):
        # Mandarin is "cmn-Hans-CN" to the streaming model, never a bare tag.
        return "cmn-Hans-CN"
    if len(parts) > 1 and len(parts[1]) == 4 and parts[1].isalpha():
        # A script subtag, not a region: chirp_2 reports Arabic speech as
        # "ar-Latn" (Arabic written in Latin letters) about as often as
        # "ar". The language is right, so keep it and supply a region the
        # streaming model accepts instead of passing the script through.
        return _DEFAULT_REGION.get(primary)
    if len(parts) > 1:
        return "-".join(parts)
    return _DEFAULT_REGION.get(primary)


async def detect_language(pcm: bytes, settings: Settings) -> str | None:
    """Name the language spoken in `pcm`, or None if it cannot be told."""
    from google.api_core.client_options import ClientOptions
    from google.cloud.speech_v2 import SpeechAsyncClient
    from google.cloud.speech_v2.types import cloud_speech

    location = settings.google_detect_location
    client = SpeechAsyncClient(
        client_options=ClientOptions(api_endpoint=f"{location}-speech.googleapis.com")
    )
    config = cloud_speech.RecognitionConfig(
        explicit_decoding_config=cloud_speech.ExplicitDecodingConfig(
            encoding=cloud_speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=SAMPLE_RATE_HZ,
            audio_channel_count=CHANNELS,
        ),
        language_codes=["auto"],
        model=_DETECT_MODEL,
    )
    response = await client.recognize(
        request=cloud_speech.RecognizeRequest(
            recognizer=(
                f"projects/{settings.google_project}"
                f"/locations/{location}/recognizers/_"
            ),
            config=config,
            content=pcm,
        )
    )
    for result in response.results:
        resolved = resolve_language(result.language_code)
        if resolved:
            return resolved
    return None
