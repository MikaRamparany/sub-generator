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

# Word-snap tolerance: only snap segment.start forward if the first word
# starts within this many seconds AFTER the declared segment start.
# Larger shifts → probably a misaligned word → keep original.
_WORD_SNAP_MAX_SHIFT = 1.5  # seconds


def _snap_segment_starts(
    segments: list[SubtitleSegment],
    words: list[dict],
) -> tuple[list[SubtitleSegment], int]:
    """Snap each segment's start to the actual first-word onset.

    Whisper's segment.start is anchored to the attention window, which often
    predates the first spoken word by 0.1–0.5 s (or more at the very start of
    the audio). Word-level timestamps are aligned to actual speech onset.

    We only snap FORWARD (make start later) — never backward.  This eliminates
    the "subtitle appears before the character speaks" artefact without risk of
    making things worse.

    Returns (snapped_segments, count_of_snapped).
    """
    if not words:
        return segments, 0

    result: list[SubtitleSegment] = []
    snapped = 0

    for seg in segments:
        # Words whose start falls in [seg.start - 0.3, seg.end).
        # The 0.3 s tolerance covers minor misalignment between the two arrays.
        seg_words = [
            w for w in words
            if w.get("start", 0.0) >= seg.start - 0.3
            and w.get("start", 0.0) < seg.end
        ]

        if seg_words:
            first_word_start = float(seg_words[0].get("start", seg.start))
            shift = first_word_start - seg.start

            if 0.0 < shift <= _WORD_SNAP_MAX_SHIFT:
                # Move start forward to real speech onset; preserve min 100 ms duration
                new_start = min(first_word_start, seg.end - 0.1)
                result.append(SubtitleSegment(
                    id=seg.id, start=new_start, end=seg.end, text=seg.text
                ))
                snapped += 1
                continue

        result.append(seg)

    return result, snapped


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

        Both modes request word-level timestamps in addition to segment-level
        ones so we can snap segment starts to actual speech onset.
        """
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")

        model = settings.get_stt_model(quality_mode)
        logger.info(
            f"Transcribing with model={model}, language={source_language}, mode={quality_mode}"
        )

        # httpx accepts a list as dict value to repeat a field name in multipart,
        # which is what Groq expects for timestamp_granularities[].
        data: dict[str, object] = {
            "model": model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": ["segment", "word"],  # both → word-snap
        }
        if source_language and source_language != "auto":
            data["language"] = source_language
        if quality_mode == "high_quality":
            data["temperature"] = "0"

        response: httpx.Response | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=300) as client:
                    with open(audio_path, "rb") as f:
                        files = {"file": (audio_path.split("/")[-1], f, "audio/wav")}
                        response = await client.post(
                            GROQ_API_URL,
                            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                            data=data,
                            files=files,
                        )
            except (httpx.TransportError, httpx.TimeoutException) as e:
                if attempt < _MAX_RETRIES:
                    wait = _RETRY_BACKOFF[attempt]
                    logger.warning(
                        f"Groq STT network error: {type(e).__name__}: {e} "
                        f"(attempt {attempt + 1}/{_MAX_RETRIES + 1}) — retrying in {wait}s"
                    )
                    await asyncio.sleep(wait)
                    continue
                raise RuntimeError(
                    f"Groq STT failed after {_MAX_RETRIES + 1} attempts: "
                    f"{type(e).__name__}: {e or 'connection lost'}"
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
        raw_words = result.get("words", [])  # word-level timestamps (may be absent)

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

        # Snap segment starts to actual word onset.
        # This fixes the classic Whisper artefact where a subtitle appears
        # 0.1–0.5 s before the character actually starts speaking.
        if isinstance(raw_words, list) and raw_words:
            subtitle_segments, snapped = _snap_segment_starts(subtitle_segments, raw_words)
            if snapped:
                logger.info(
                    f"Word-snap: corrected start time on {snapped}/{len(subtitle_segments)} segment(s)"
                )
        else:
            logger.debug("No word-level timestamps in STT response — skipping start-snap")

        logger.info(
            f"Transcription complete: {len(subtitle_segments)} segments "
            f"(model={model}, mode={quality_mode})"
        )
        return subtitle_segments
