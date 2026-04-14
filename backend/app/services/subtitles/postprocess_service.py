from __future__ import annotations

import re

from app.core.logging import logger
from app.models.schemas import SubtitleSegment

MIN_SEGMENT_DURATION = 0.3  # seconds
MAX_GAP_FOR_MERGE = 0.15  # seconds


def clean_segments(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Apply all post-processing rules to subtitle segments."""
    result = segments
    result = remove_empty_segments(result)
    result = trim_text(result)
    result = fix_negative_timecodes(result)
    result = fix_invalid_durations(result)
    result = sort_chronologically(result)
    result = fix_overlaps(result)
    result = merge_short_segments(result)
    result = clean_punctuation(result)
    result = reindex(result)
    logger.info(f"Post-processing: {len(segments)} -> {len(result)} segments")
    return result


def remove_empty_segments(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    return [s for s in segments if s.text and s.text.strip()]


def trim_text(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    return [
        SubtitleSegment(id=s.id, start=s.start, end=s.end, text=s.text.strip())
        for s in segments
    ]


def fix_negative_timecodes(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    return [
        SubtitleSegment(
            id=s.id,
            start=max(0.0, s.start),
            end=max(0.0, s.end),
            text=s.text,
        )
        for s in segments
    ]


def fix_invalid_durations(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Remove segments where end <= start."""
    return [s for s in segments if s.end > s.start]


def sort_chronologically(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    return sorted(segments, key=lambda s: s.start)


def fix_overlaps(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Fix overlapping segments by trimming the end of the earlier segment."""
    if len(segments) < 2:
        return segments
    fixed = [segments[0]]
    for seg in segments[1:]:
        prev = fixed[-1]
        if prev.end > seg.start:
            fixed[-1] = SubtitleSegment(
                id=prev.id,
                start=prev.start,
                end=seg.start,
                text=prev.text,
            )
        fixed.append(seg)
    return [s for s in fixed if s.end > s.start]


def merge_short_segments(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Merge very short segments with the next segment if gap is small."""
    if len(segments) < 2:
        return segments

    merged: list[SubtitleSegment] = []
    i = 0
    while i < len(segments):
        seg = segments[i]
        duration = seg.end - seg.start
        if (
            duration < MIN_SEGMENT_DURATION
            and i + 1 < len(segments)
            and segments[i + 1].start - seg.end < MAX_GAP_FOR_MERGE
        ):
            next_seg = segments[i + 1]
            merged.append(
                SubtitleSegment(
                    id=seg.id,
                    start=seg.start,
                    end=next_seg.end,
                    text=f"{seg.text} {next_seg.text}",
                )
            )
            i += 2
        else:
            merged.append(seg)
            i += 1
    return merged


def clean_punctuation(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """Clean obvious punctuation issues."""
    result = []
    for s in segments:
        text = s.text
        # Remove multiple spaces
        text = re.sub(r" {2,}", " ", text)
        # Remove leading/trailing punctuation oddities
        text = re.sub(r"^[,;:\s]+", "", text)
        # Fix multiple periods
        text = re.sub(r"\.{4,}", "...", text)
        text = text.strip()
        if text:
            result.append(SubtitleSegment(id=s.id, start=s.start, end=s.end, text=text))
    return result


def reindex(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    return [
        SubtitleSegment(id=i, start=s.start, end=s.end, text=s.text)
        for i, s in enumerate(segments, start=1)
    ]
