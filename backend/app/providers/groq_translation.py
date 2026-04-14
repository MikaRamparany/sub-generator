from __future__ import annotations

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

BATCH_SIZE = 20


def _extract_json_from_content(content: str) -> str:
    """Strip markdown code fences if present and return raw JSON string."""
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        # Drop first line (```json or ```) and last line (```)
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

        for batch_start in range(0, len(segments), BATCH_SIZE):
            batch = segments[batch_start : batch_start + BATCH_SIZE]
            translated_batch = await self._translate_batch(
                batch, target_language, lang_name, source_language
            )
            all_translated.extend(translated_batch)

        logger.info(f"Translation complete: {len(all_translated)} segments to {lang_name}")
        return all_translated

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
            f"Translate the following subtitle segments to {lang_name}.{source_hint}\n"
            f"Return ONLY a JSON array of objects with 'id' (integer) and 'text' (string) fields.\n"
            f"Preserve proper nouns. Keep translations concise for subtitle readability.\n"
            f"Do not add any explanation, just the JSON array.\n\n"
            f"Segments:\n{json.dumps(segments_data, ensure_ascii=False)}"
        )

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                GROQ_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a professional subtitle translator. "
                                "You output only valid JSON arrays."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                },
            )

        if response.status_code == 429:
            raise RuntimeError("API rate limit reached during translation.")
        if response.status_code != 200:
            raise RuntimeError(
                f"Groq translation API error {response.status_code}: {response.text[:300]}"
            )

        raw_content = response.json()["choices"][0]["message"]["content"]
        json_str = _extract_json_from_content(raw_content)

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Translation response is not valid JSON: {e} — "
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
                logger.warning(
                    f"No translation returned for segment id={seg.id} "
                    f"(lang={target_language}) — using source text as fallback"
                )
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
