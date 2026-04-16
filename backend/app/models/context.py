"""Internal model for transcript-level context inferred from the source text.

This is not a public API schema — it lives only in memory during a job and is
passed between the transcript analysis, translation, and QA phases.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GlossaryEntry:
    src: str           # source term (as it appears in the transcript)
    preferred: str     # preferred translation in target language
    note: str = ""     # optional note for the translator


@dataclass
class TranscriptContext:
    """Structured context inferred from the full source transcript.

    Built by transcript_context_service.analyze_transcript() once per job.
    Injected into translation providers and QA to improve consistency.

    All fields are best-effort — the service marks low-confidence analyses
    with confidence < 0.7 and callers may choose to use the context more
    conservatively in that case.
    """
    proper_nouns: list[str] = field(default_factory=list)
    # Character names, place names, brand names — should stay untranslated

    glossary: list[GlossaryEntry] = field(default_factory=list)
    # Recurring terms with preferred translations and optional hints

    ambiguous_words: list[str] = field(default_factory=list)
    # Source words that could be mistranslated without context (e.g. "Fire", "Clear")

    style: str = ""
    # Short style/register hint derived from the transcript
    # e.g. "military action thriller, terse dialogue"

    confidence: float = 1.0
    # 0.0–1.0. Low (<0.6) means the LLM analysis was uncertain or the
    # transcript was too short to draw reliable conclusions.

    def to_glossary_hint(self, target_language: str) -> str:
        """Build a compact string for injection into translation prompts."""
        lines: list[str] = []
        if self.proper_nouns:
            lines.append(f"Keep unchanged: {', '.join(self.proper_nouns[:20])}")
        if self.glossary:
            entries = "; ".join(
                f"{e.src} → {e.preferred}" + (f" ({e.note})" if e.note else "")
                for e in self.glossary[:15]
            )
            lines.append(f"Preferred translations: {entries}")
        if self.ambiguous_words:
            lines.append(f"Context-sensitive: {', '.join(self.ambiguous_words[:10])}")
        if self.style:
            lines.append(f"Style: {self.style}")
        return "\n".join(lines)

    def is_useful(self) -> bool:
        """True if the context has enough information to be worth injecting."""
        return bool(self.proper_nouns or self.glossary or self.ambiguous_words)
