from __future__ import annotations

import asyncio
import json

import httpx

from app.core.config import settings
from app.core.logging import logger
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

BATCH_SIZE = 10  # Keep small — LLM output gets truncated with larger batches
MAX_TOKENS = 2048  # Enough for 10 translated segments in verbose languages

_RETRYABLE_STATUS = {502, 503, 504}
_MAX_RETRIES = 4
_RETRY_BACKOFF = [3, 6, 15, 30]  # seconds — generous for rate limits
_INTER_BATCH_DELAY = 1.5  # seconds between batches to avoid rate limits


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
    ) -> list[TranslatedSubtitleSegment]:
        """Translate segments using Groq LLM API, batch by batch."""
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")

        lang_name = LANGUAGE_NAMES.get(target_language, target_language)
        logger.info(f"Translating {len(segments)} segments to {lang_name}")

        all_translated: list[TranslatedSubtitleSegment] = []

        for batch_idx, batch_start in enumerate(range(0, len(segments), BATCH_SIZE)):
            batch = segments[batch_start : batch_start + BATCH_SIZE]

            # Rate-limit: pause between batches (not before the first one)
            if batch_idx > 0:
                await asyncio.sleep(_INTER_BATCH_DELAY)

            translated_batch = await self._translate_batch_safe(
                batch, target_language, lang_name, source_language
            )
            all_translated.extend(translated_batch)

        logger.info(f"Translation complete: {len(all_translated)} segments to {lang_name}")
        return all_translated

    async def _translate_batch_safe(
        self,
        segments: list[SubtitleSegment],
        target_language: str,
        lang_name: str,
        source_language: str | None,
    ) -> list[TranslatedSubtitleSegment]:
        """Translate a batch, splitting in half on truncation, falling back to source on error."""
        try:
            return await self._translate_batch(
                segments, target_language, lang_name, source_language
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
            await asyncio.sleep(_INTER_BATCH_DELAY)
            first = await self._translate_batch_safe(
                segments[:mid], target_language, lang_name, source_language
            )
            await asyncio.sleep(_INTER_BATCH_DELAY)
            second = await self._translate_batch_safe(
                segments[mid:], target_language, lang_name, source_language
            )
            return first + second
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
    ) -> list[TranslatedSubtitleSegment]:
        model = settings.groq_translation_model
        segments_data = [{"id": s.id, "text": s.text} for s in segments]

        source_hint = ""
        if source_language and source_language != "auto":
            src_name = LANGUAGE_NAMES.get(source_language, source_language)
            source_hint = f" The source language is {src_name}."

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
            f"- For exclamations and interjections, use natural {lang_name} equivalents\n\n"
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
            "max_tokens": MAX_TOKENS,
        }

        response = await self._request_with_retry(payload)
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

    async def _request_with_retry(self, payload: dict) -> httpx.Response:
        """POST to Groq with retry on transient errors and 429 rate limits."""
        for attempt in range(_MAX_RETRIES + 1):
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
                if attempt < _MAX_RETRIES:
                    wait = _RETRY_BACKOFF[attempt]
                    logger.warning(
                        f"Translation network error: {type(e).__name__}: {e} "
                        f"(attempt {attempt + 1}/{_MAX_RETRIES + 1}) — retrying in {wait}s"
                    )
                    await asyncio.sleep(wait)
                    continue
                raise RuntimeError(
                    f"Translation failed after {_MAX_RETRIES + 1} attempts: "
                    f"{type(e).__name__}: {e or 'connection lost'}"
                )

            # Retryable HTTP status codes (server errors + rate limit)
            if response.status_code in _RETRYABLE_STATUS or response.status_code == 429:
                if attempt < _MAX_RETRIES:
                    wait = _RETRY_BACKOFF[attempt]
                    logger.warning(
                        f"Translation API returned {response.status_code} "
                        f"(attempt {attempt + 1}/{_MAX_RETRIES + 1}) — retrying in {wait}s"
                    )
                    await asyncio.sleep(wait)
                    continue

            if response.status_code == 429:
                raise RuntimeError("API rate limit reached during translation (exhausted retries).")
            if response.status_code != 200:
                raise RuntimeError(
                    f"Groq translation API error {response.status_code}: {response.text[:300]}"
                )

            return response

        raise RuntimeError("Translation request failed unexpectedly")


class _TruncatedResponseError(Exception):
    """Internal: raised when the LLM output is truncated by max_tokens."""
    pass
