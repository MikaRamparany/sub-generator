from __future__ import annotations

import asyncio

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.models.schemas import SubtitleSegment
from app.providers.base import SpeechToTextProvider

GROQ_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

_RETRYABLE_STATUS = {502, 503, 504}
_MAX_RETRIES = 3
_RETRY_BACKOFF = [2, 5, 10]  # seconds between attempts


class GroqSTTProvider(SpeechToTextProvider):
    async def transcribe(
        self,
        audio_path: str,
        source_language: str | None = None,
        quality_mode: str = "fast",
    ) -> list[SubtitleSegment]:
        """Transcribe audio using Groq Whisper API.

        fast mode:
          - uses groq_stt_fast_model (whisper-large-v3-turbo by default)
          - temperature=1 (Groq default, fast decoding)

        high_quality mode:
          - uses groq_stt_quality_model (whisper-large-v3 by default)
          - temperature=0 (deterministic, more accurate)
        """
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")

        model = settings.get_stt_model(quality_mode)
        logger.info(
            f"Transcribing with model={model}, language={source_language}, mode={quality_mode}"
        )

        data: dict[str, str] = {
            "model": model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": "segment",
        }
        if source_language and source_language != "auto":
            data["language"] = source_language
        if quality_mode == "high_quality":
            # Deterministic decoding — higher accuracy, slower
            data["temperature"] = "0"

        response: httpx.Response | None = None
        for attempt in range(_MAX_RETRIES + 1):
            async with httpx.AsyncClient(timeout=300) as client:
                with open(audio_path, "rb") as f:
                    files = {"file": (audio_path.split("/")[-1], f, "audio/wav")}
                    response = await client.post(
                        GROQ_API_URL,
                        headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                        data=data,
                        files=files,
                    )

            if response.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                wait = _RETRY_BACKOFF[attempt]
                logger.warning(
                    f"Groq STT returned {response.status_code} "
                    f"(attempt {attempt + 1}/{_MAX_RETRIES + 1}) — retrying in {wait}s"
                )
                await asyncio.sleep(wait)
                continue
            break

        assert response is not None
        if response.status_code == 429:
            raise RuntimeError("API rate limit reached. Please wait and try again.")
        if response.status_code != 200:
            raise RuntimeError(
                f"Groq STT API error {response.status_code}: {response.text[:300]}"
            )

        result = response.json()
        raw_segments = result.get("segments", [])

        if not isinstance(raw_segments, list):
            raise RuntimeError(
                f"Unexpected STT response format: 'segments' is {type(raw_segments)}"
            )

        subtitle_segments: list[SubtitleSegment] = []
        for i, seg in enumerate(raw_segments, start=1):
            text = seg.get("text", "").strip()
            if not text:
                continue
            try:
                subtitle_segments.append(
                    SubtitleSegment(
                        id=i,
                        start=float(seg["start"]),
                        end=float(seg["end"]),
                        text=text,
                    )
                )
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping malformed STT segment {i}: {e} — {seg}")

        logger.info(
            f"Transcription complete: {len(subtitle_segments)} segments "
            f"(model={model}, mode={quality_mode})"
        )
        return subtitle_segments
