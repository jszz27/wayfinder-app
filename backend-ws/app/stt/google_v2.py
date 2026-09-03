"""Google Cloud Speech-to-Text v2 streaming adapter.

Requires the `google` extra:  pip install ".[google]"

Audio arrives already in the format the widget and this server agreed on
(16 kHz mono PCM16), so it is handed to the API with an explicit decoding
config rather than letting the service sniff a container.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.config import CHANNELS, SAMPLE_RATE_HZ, Settings
from app.stt.base import SttResult, SttStream

# The inline recognizer: recognition settings travel with the request
# instead of being registered as a named resource up front.
_INLINE_RECOGNIZER = "_"


class GoogleSttStream(SttStream):
    def __init__(self, settings: Settings) -> None:
        if not settings.google_project:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT must be set when WAYFINDER_STT=google."
            )
        self._settings = settings
        self._audio: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._closed = False

    async def push(self, pcm: bytes) -> None:
        if self._closed:
            return
        await self._audio.put(pcm)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._audio.put(None)

    async def results(self) -> AsyncIterator[SttResult]:
        from google.api_core.client_options import ClientOptions
        from google.cloud.speech_v2 import SpeechAsyncClient
        from google.cloud.speech_v2.types import cloud_speech

        settings = self._settings
        location = settings.google_location

        client_options = None
        if location != "global":
            client_options = ClientOptions(
                api_endpoint=f"{location}-speech.googleapis.com"
            )
        client = SpeechAsyncClient(client_options=client_options)

        recognizer = (
            f"projects/{settings.google_project}"
            f"/locations/{location}/recognizers/{_INLINE_RECOGNIZER}"
        )
        config = cloud_speech.RecognitionConfig(
            explicit_decoding_config=cloud_speech.ExplicitDecodingConfig(
                encoding=cloud_speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=SAMPLE_RATE_HZ,
                audio_channel_count=CHANNELS,
            ),
            language_codes=[settings.stt_language],
            model=settings.stt_model,
        )
        streaming_config = cloud_speech.StreamingRecognitionConfig(
            config=config,
            streaming_features=cloud_speech.StreamingRecognitionFeatures(
                interim_results=True,
            ),
        )

        async def requests() -> AsyncIterator[cloud_speech.StreamingRecognizeRequest]:
            # The first request carries configuration only; audio follows.
            yield cloud_speech.StreamingRecognizeRequest(
                recognizer=recognizer, streaming_config=streaming_config
            )
            while (chunk := await self._audio.get()) is not None:
                yield cloud_speech.StreamingRecognizeRequest(audio=chunk)

        responses = await client.streaming_recognize(requests=requests())
        async for response in responses:
            for result in response.results:
                if not result.alternatives:
                    continue
                transcript = result.alternatives[0].transcript
                if not transcript:
                    continue
                yield SttResult(text=transcript, is_final=result.is_final)
