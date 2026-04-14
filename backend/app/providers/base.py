from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.schemas import SubtitleSegment, TranslatedSubtitleSegment


class SpeechToTextProvider(ABC):
    @abstractmethod
    async def transcribe(
        self,
        audio_path: str,
        source_language: str | None = None,
        quality_mode: str = "fast",
    ) -> list[SubtitleSegment]:
        """Transcribe audio file and return timestamped segments."""
        ...


class SubtitleTranslationProvider(ABC):
    @abstractmethod
    async def translate_segments(
        self,
        segments: list[SubtitleSegment],
        target_language: str,
        source_language: str | None = None,
    ) -> list[TranslatedSubtitleSegment]:
        """Translate subtitle segments to target language, preserving timecodes."""
        ...
