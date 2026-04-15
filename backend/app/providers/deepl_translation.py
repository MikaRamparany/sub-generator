from __future__ import annotations

import asyncio

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.models.schemas import SubtitleSegment, TranslatedSubtitleSegment
from app.providers.base import SubtitleTranslationProvider

# Free-tier keys end with :fx → different hostname
_API_URL_FREE = "https://api-free.deepl.com/v2/translate"
_API_URL_PAID = "https://api.deepl.com/v2/translate"

# DeepL target language codes (some require region variant)
_TARGET_LANG = {
    "fr": "FR",
    "en": "EN-US",
    "es": "ES",
    "de": "DE",
    "pt": "PT-PT",
}

# DeepL source language codes (2-letter, no variant)
_SOURCE_LANG = {
    "fr": "FR",
    "en": "EN",
    "es": "ES",
    "de": "DE",
    "pt": "PT",
}

# DeepL accepts up to 50 texts per request
_BATCH_SIZE = 50
# Small courtesy delay between batches (DeepL rate limits are very generous,
# but avoid hammering in a tight loop)
_INTER_BATCH_DELAY = 0.3  # seconds

_MAX_RETRIES = 3
_RETRY_BACKOFF = [2, 5, 10]


class DeepLTranslationProvider(SubtitleTranslationProvider):
    async def translate_segments(
        self,
        segments: list[SubtitleSegment],
        target_language: str,
        source_language: str | None = None,
        translation_mode: str = "fast",  # ignored — DeepL has no meaningful modes
    ) -> list[TranslatedSubtitleSegment]:
        if not settings.deepl_api_key:
            raise RuntimeError("DEEPL_API_KEY is not configured")

        target_lang = _TARGET_LANG.get(target_language, target_language.upper())
        source_lang = (
            _SOURCE_LANG.get(source_language, source_language.upper())
            if source_language and source_language != "auto"
            else None
        )

        logger.info(
            f"Translating {len(segments)} segments to {target_lang} via DeepL "
            f"({len(segments) // _BATCH_SIZE + 1} batch(es))"
        )

        all_translated: list[TranslatedSubtitleSegment] = []

        for batch_idx, batch_start in enumerate(range(0, len(segments), _BATCH_SIZE)):
            batch = segments[batch_start : batch_start + _BATCH_SIZE]

            if batch_idx > 0:
                await asyncio.sleep(_INTER_BATCH_DELAY)

            texts = await self._translate_texts(
                [s.text for s in batch], target_lang, source_lang
            )

            for seg, translated_text in zip(batch, texts):
                all_translated.append(
                    TranslatedSubtitleSegment(
                        id=seg.id,
                        start=seg.start,
                        end=seg.end,
                        source_text=seg.text,
                        translated_text=translated_text,
                        target_language=target_language,
                    )
                )

        logger.info(f"DeepL translation complete: {len(all_translated)} segments")
        return all_translated

    async def _translate_texts(
        self,
        texts: list[str],
        target_lang: str,
        source_lang: str | None,
    ) -> list[str]:
        """Send a batch of texts to DeepL and return translated strings."""
        api_key = settings.deepl_api_key
        url = _API_URL_FREE if api_key.endswith(":fx") else _API_URL_PAID

        payload: dict = {
            "text": texts,
            "target_lang": target_lang,
            "preserve_formatting": True,
        }
        if source_lang:
            payload["source_lang"] = source_lang

        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        url,
                        headers={
                            "Authorization": f"DeepL-Auth-Key {api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
            except (httpx.TransportError, httpx.TimeoutException) as e:
                if attempt < _MAX_RETRIES:
                    wait = _RETRY_BACKOFF[attempt]
                    logger.warning(
                        f"DeepL network error: {type(e).__name__} "
                        f"(attempt {attempt + 1}/{_MAX_RETRIES + 1}) — retrying in {wait}s"
                    )
                    await asyncio.sleep(wait)
                    continue
                raise RuntimeError(f"DeepL request failed: {type(e).__name__}: {e or 'connection lost'}")

            if response.status_code == 429:
                if attempt < _MAX_RETRIES:
                    wait = _RETRY_BACKOFF[attempt]
                    logger.warning(f"DeepL 429 — retrying in {wait}s")
                    await asyncio.sleep(wait)
                    continue
                raise RuntimeError("DeepL rate limit exhausted")

            if response.status_code == 456:
                raise RuntimeError("DeepL quota exceeded — monthly character limit reached")

            if response.status_code != 200:
                raise RuntimeError(
                    f"DeepL API error {response.status_code}: {response.text[:200]}"
                )

            data = response.json()
            return [item["text"] for item in data["translations"]]

        raise RuntimeError("DeepL request failed unexpectedly")
