from __future__ import annotations

import asyncio
import json

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.models.context import TranscriptContext
from app.models.schemas import SubtitleSegment, TranslatedSubtitleSegment
from app.providers.base import SubtitleTranslationProvider

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

LANGUAGE_NAMES = {
    "fr": "French",
    "en": "English",
    "es": "Spanish",
    "de": "German",
    "pt": "Portuguese",
    "ar": "Arabic",
}

_RETRYABLE_STATUS = {502, 503, 504}

# Per-mode settings
# fast     — default, short files, low 429 risk
# balanced — recommended for long films: stays within ~6k TPM budget at 8s/batch
# safe     — maximum patience, very long files where quality > speed
_MODE_BATCH_SIZE        = {"fast": 10, "balanced": 7,  "safe": 5}
# balanced: 8s keeps throughput ≤ 6 req/min × ~800 tokens ≈ 4800 TPM — within free tier
# safe: 12s is even more conservative
_MODE_INTER_BATCH_DELAY = {"fast": 1.5, "balanced": 8.0, "safe": 12.0}  # seconds between batches
_MODE_PRE_BATCH_DELAY   = {"fast": 0.0, "balanced": 2.0, "safe": 3.0}   # delay before first batch
_MODE_MAX_RETRIES       = {"fast": 4,   "balanced": 3,   "safe": 5}
_MODE_RETRY_BACKOFF = {
    "fast":     [3, 6, 15, 30],        # max wait before fallback: 54s
    "balanced": [5, 15, 30],           # max wait before fallback: 50s — fail fast, move on
    "safe":     [5, 12, 25, 60, 120],  # max wait before fallback: 222s — very patient
}
# After exhausting 429 retries on a batch, wait this long before the NEXT batch.
_MODE_RATE_LIMIT_RECOVERY = {"fast": 45, "balanced": 75, "safe": 120}  # seconds

# Dynamic max_tokens per batch: ~110 tokens per segment for verbose languages (French, German…)
# This avoids reserving 2048 tokens when 7 segments only need ~400, which burns TPM quota.
_TOKENS_PER_SEGMENT = 110
_MAX_TOKENS_FLOOR = 400
_MAX_TOKENS_CAP = 2048


def _max_tokens_for_batch(batch_size: int) -> int:
    return max(_MAX_TOKENS_FLOOR, min(_MAX_TOKENS_CAP, batch_size * _TOKENS_PER_SEGMENT))


def _parse_retry_after(response: httpx.Response) -> float | None:
    """Read Groq's retry-after header and return seconds to wait, or None."""
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(1.0, float(value))
    except (ValueError, TypeError):
        return None


def _extract_json_from_content(content: str) -> str:
    """Strip markdown code fences if present and return raw JSON string."""
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        inner = lines[1:] if len(lines) > 1 else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        content = "\n".join(inner).strip()
    return content


def _validate_translation_item(item: object) -> tuple[int, str] | None:
    """Return (id, text) if the item is a valid translation dict, else None."""
    if not isinstance(item, dict):
        return None
    id_val = item.get("id")
    text_val = item.get("text")
    if not isinstance(id_val, int) or not isinstance(text_val, str):
        return None
    if not text_val.strip():
        return None
    return (id_val, text_val)


class GroqTranslationProvider(SubtitleTranslationProvider):
    async def translate_segments(
        self,
        segments: list[SubtitleSegment],
        target_language: str,
        source_language: str | None = None,
        translation_mode: str = "fast",
        transcript_context: TranscriptContext | None = None,
    ) -> list[TranslatedSubtitleSegment]:
        """Translate segments using Groq LLM API, batch by batch.

        translation_mode:
          - "fast": batch_size=10, 1.5s inter-batch delay — good for short files
          - "safe": batch_size=5, 4s inter-batch delay, longer retries — for long films
        """
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")

        mode = translation_mode if translation_mode in _MODE_BATCH_SIZE else "fast"
        batch_size = _MODE_BATCH_SIZE[mode]
        inter_batch_delay = _MODE_INTER_BATCH_DELAY[mode]
        pre_batch_delay = _MODE_PRE_BATCH_DELAY[mode]

        lang_name = LANGUAGE_NAMES.get(target_language, target_language)
        logger.info(
            f"Translating {len(segments)} segments to {lang_name} "
            f"(mode={mode}, batch_size={batch_size})"
        )

        # In safe mode, add a delay before the very first batch too
        if pre_batch_delay > 0:
            await asyncio.sleep(pre_batch_delay)

        all_translated: list[TranslatedSubtitleSegment] = []

        recovery_sleep = 0.0  # set when a batch hits 429 wall — applied before next batch

        for batch_idx, batch_start in enumerate(range(0, len(segments), batch_size)):
            batch = segments[batch_start : batch_start + batch_size]

            # Normal inter-batch delay (skip before first batch)
            if batch_idx > 0:
                delay = recovery_sleep if recovery_sleep > 0 else inter_batch_delay
                if recovery_sleep > 0:
                    logger.warning(
                        f"Rate-limit wall hit on previous batch — "
                        f"waiting {recovery_sleep:.0f}s before continuing..."
                    )
                    recovery_sleep = 0.0
                await asyncio.sleep(delay)

            try:
                translated_batch = await self._translate_batch_safe(
                    batch, target_language, lang_name, source_language, mode,
                    transcript_context=transcript_context,
                )
            except _RateLimitExhaustedFallback as exc:
                # Batch fell back to source text due to exhausted 429 retries.
                # Use server's retry-after if available; otherwise use our mode default.
                translated_batch = exc.fallback_segments
                recovery_sleep = exc.retry_after or _MODE_RATE_LIMIT_RECOVERY[mode]

            all_translated.extend(translated_batch)

        logger.info(f"Translation complete: {len(all_translated)} segments to {lang_name}")
        return all_translated

    async def _translate_batch_safe(
        self,
        segments: list[SubtitleSegment],
        target_language: str,
        lang_name: str,
        source_language: str | None,
        mode: str = "fast",
        transcript_context: TranscriptContext | None = None,
    ) -> list[TranslatedSubtitleSegment]:
        """Translate a batch, splitting in half on truncation, falling back to source on error."""
        inter_batch_delay = _MODE_INTER_BATCH_DELAY[mode]
        try:
            return await self._translate_batch(
                segments, target_language, lang_name, source_language, mode,
                transcript_context=transcript_context,
            )
        except _TruncatedResponseError:
            # Output was truncated — split batch in half and retry each part
            if len(segments) <= 2:
                logger.warning(
                    f"Translation truncated even with {len(segments)} segments "
                    f"— falling back to source text"
                )
                return self._fallback_to_source(segments, target_language)

            mid = len(segments) // 2
            logger.warning(
                f"Translation truncated for {len(segments)} segments "
                f"— splitting into {mid} + {len(segments) - mid} and retrying"
            )
            await asyncio.sleep(inter_batch_delay)
            first = await self._translate_batch_safe(
                segments[:mid], target_language, lang_name, source_language, mode,
                transcript_context=transcript_context,
            )
            await asyncio.sleep(inter_batch_delay)
            second = await self._translate_batch_safe(
                segments[mid:], target_language, lang_name, source_language, mode,
                transcript_context=transcript_context,
            )
            return first + second
        except _RateLimitExhaustedError as e:
            # 429 retries exhausted — fall back to source text and re-raise so the
            # batch loop knows to insert a recovery sleep before the next request
            logger.warning(
                f"Translation batch failed ({len(segments)} segments, "
                f"lang={target_language}): {e} — using source text as fallback"
            )
            raise _RateLimitExhaustedFallback(
                self._fallback_to_source(segments, target_language),
                retry_after=e.retry_after,
            )
        except RuntimeError as e:
            # Any other translation error — log and fall back to source text
            logger.warning(
                f"Translation batch failed ({len(segments)} segments, "
                f"lang={target_language}): {e} — using source text as fallback"
            )
            return self._fallback_to_source(segments, target_language)

    async def _translate_batch(
        self,
        segments: list[SubtitleSegment],
        target_language: str,
        lang_name: str,
        source_language: str | None,
        mode: str = "fast",
        transcript_context: TranscriptContext | None = None,
    ) -> list[TranslatedSubtitleSegment]:
        model = settings.groq_translation_model
        segments_data = [{"id": s.id, "text": s.text} for s in segments]

        source_hint = ""
        if source_language and source_language != "auto":
            src_name = LANGUAGE_NAMES.get(source_language, source_language)
            source_hint = f" The source language is {src_name}."

        context_block = ""
        if transcript_context and transcript_context.is_useful():
            hint = transcript_context.to_glossary_hint(target_language)
            context_block = f"\n\nTranscript context (inferred — use to improve consistency):\n{hint}\n"

        prompt = (
            f"Translate the following movie/series subtitle segments to {lang_name}.{source_hint}\n"
            f"Return ONLY a JSON array of objects with 'id' (integer) and 'text' (string) fields.\n"
            f"Do not add any explanation, markdown, or wrapper — just the raw JSON array.\n\n"
            f"Translation rules:\n"
            f"- Natural and idiomatic — write as a native {lang_name} speaker would say it\n"
            f"- Never translate word-for-word; adapt idioms and expressions culturally\n"
            f"- Keep it concise: subtitles must be readable in the time available\n"
            f"- Preserve character names, place names, and proper nouns unchanged\n"
            f"- Match the emotional tone and register (casual, formal, urgent, etc.)\n"
            f"- For exclamations and interjections, use natural {lang_name} equivalents\n"
            f"{context_block}\n"
            f"Segments:\n{json.dumps(segments_data, ensure_ascii=False)}"
        )

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a professional subtitle localizer specializing in film and TV series. "
                        "You produce natural, idiomatic translations — never literal. "
                        "You output only valid JSON arrays, no markdown."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": _max_tokens_for_batch(len(segments)),
        }

        response = await self._request_with_retry(payload, mode)
        body = response.json()
        choice = body["choices"][0]

        # Detect truncation before parsing JSON
        if choice.get("finish_reason") == "length":
            raise _TruncatedResponseError("Response truncated by max_tokens limit")

        raw_content = choice["message"]["content"]
        json_str = _extract_json_from_content(raw_content)

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            # Truncation can also manifest as invalid JSON without finish_reason=length
            raise _TruncatedResponseError(
                f"Translation response is not valid JSON (likely truncated): {e} — "
                f"raw: {json_str[:200]}"
            )

        if not isinstance(parsed, list):
            raise RuntimeError(
                f"Translation response must be a JSON array, got {type(parsed).__name__}: "
                f"{json_str[:200]}"
            )

        # Build id→text map with strict validation per item
        translation_map: dict[int, str] = {}
        anomalies = 0
        for item in parsed:
            valid = _validate_translation_item(item)
            if valid is None:
                anomalies += 1
                logger.warning(f"Skipping malformed translation item: {item!r}")
            else:
                id_val, text_val = valid
                translation_map[id_val] = text_val

        if anomalies:
            logger.warning(
                f"{anomalies}/{len(parsed)} translation items were malformed "
                f"— source text used as fallback for missing ones"
            )

        # Build result — always preserve timecodes; fall back to source text if missing
        result: list[TranslatedSubtitleSegment] = []
        missing = 0
        for seg in segments:
            if seg.id not in translation_map:
                missing += 1
            result.append(
                TranslatedSubtitleSegment(
                    id=seg.id,
                    start=seg.start,
                    end=seg.end,
                    source_text=seg.text,
                    translated_text=translation_map.get(seg.id, seg.text),
                    target_language=target_language,
                )
            )

        if missing:
            logger.warning(
                f"{missing}/{len(segments)} segments had no translation for lang={target_language}"
            )

        return result

    def _fallback_to_source(
        self, segments: list[SubtitleSegment], target_language: str
    ) -> list[TranslatedSubtitleSegment]:
        """Return segments with source text as fallback translation."""
        return [
            TranslatedSubtitleSegment(
                id=seg.id,
                start=seg.start,
                end=seg.end,
                source_text=seg.text,
                translated_text=seg.text,
                target_language=target_language,
            )
            for seg in segments
        ]

    async def _request_with_retry(self, payload: dict, mode: str = "fast") -> httpx.Response:
        """POST to Groq with retry on transient errors and 429 rate limits."""
        max_retries = _MODE_MAX_RETRIES[mode]
        backoff = _MODE_RETRY_BACKOFF[mode]

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    response = await client.post(
                        GROQ_CHAT_URL,
                        headers={
                            "Authorization": f"Bearer {settings.groq_api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
            except (httpx.TransportError, httpx.TimeoutException) as e:
                if attempt < max_retries:
                    wait = backoff[attempt]
                    logger.warning(
                        f"Translation network error: {type(e).__name__}: {e} "
                        f"(attempt {attempt + 1}/{max_retries + 1}) — retrying in {wait}s"
                    )
                    await asyncio.sleep(wait)
                    continue
                raise RuntimeError(
                    f"Translation failed after {max_retries + 1} attempts: "
                    f"{type(e).__name__}: {e or 'connection lost'}"
                )

            # Retryable HTTP status codes (server errors + rate limit)
            if response.status_code in _RETRYABLE_STATUS or response.status_code == 429:
                if attempt < max_retries:
                    if response.status_code == 429:
                        # Use server-directed retry-after when available — it knows
                        # exactly when the rate-limit window resets. Fall back to
                        # our fixed backoff only if the header is absent/unparseable.
                        wait = _parse_retry_after(response) or backoff[attempt]
                    else:
                        wait = backoff[attempt]
                    logger.warning(
                        f"Translation API returned {response.status_code} "
                        f"(attempt {attempt + 1}/{max_retries + 1}) — retrying in {wait:.0f}s"
                    )
                    await asyncio.sleep(wait)
                    continue

            if response.status_code == 429:
                # Retries exhausted — carry the last retry-after so the caller can
                # schedule a proper recovery sleep before the next batch.
                retry_after = _parse_retry_after(response)
                raise _RateLimitExhaustedError(
                    "API rate limit reached during translation (exhausted retries).",
                    retry_after,
                )
            if response.status_code != 200:
                raise RuntimeError(
                    f"Groq translation API error {response.status_code}: {response.text[:300]}"
                )

            return response

        raise RuntimeError("Translation request failed unexpectedly")


class _TruncatedResponseError(Exception):
    """Internal: raised when the LLM output is truncated by max_tokens."""
    pass


class _RateLimitExhaustedError(RuntimeError):
    """Internal: raised by _request_with_retry when 429 retries are fully exhausted.

    Carries the server's retry-after value (if present) so callers can sleep
    exactly as long as the API requires instead of guessing.
    """
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class _RateLimitExhaustedFallback(Exception):
    """Internal: carries fallback segments back to translate_segments when 429 is unrecoverable.

    Separates 'rate limit wall hit' from generic errors so the batch loop can
    insert a server-directed (or mode-default) recovery sleep before the next batch.
    """
    def __init__(self, fallback_segments: list, retry_after: float | None = None) -> None:
        self.fallback_segments = fallback_segments
        self.retry_after = retry_after  # from Groq's retry-after header, if present
