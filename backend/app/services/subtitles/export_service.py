from __future__ import annotations

from pathlib import Path

from app.models.schemas import SubtitleSegment, TranslatedSubtitleSegment
from app.utils.timestamps import seconds_to_srt_timestamp, seconds_to_vtt_timestamp


def segments_to_srt(segments: list[SubtitleSegment]) -> str:
    """Generate SRT content from subtitle segments."""
    lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        start_ts = seconds_to_srt_timestamp(seg.start)
        end_ts = seconds_to_srt_timestamp(seg.end)
        lines.append(str(i))
        lines.append(f"{start_ts} --> {end_ts}")
        lines.append(seg.text)
        lines.append("")
    return "\n".join(lines)


def segments_to_vtt(segments: list[SubtitleSegment]) -> str:
    """Generate VTT content from subtitle segments."""
    lines: list[str] = ["WEBVTT", ""]
    for i, seg in enumerate(segments, start=1):
        start_ts = seconds_to_vtt_timestamp(seg.start)
        end_ts = seconds_to_vtt_timestamp(seg.end)
        lines.append(str(i))
        lines.append(f"{start_ts} --> {end_ts}")
        lines.append(seg.text)
        lines.append("")
    return "\n".join(lines)


def translated_segments_to_subtitle_segments(
    segments: list[TranslatedSubtitleSegment],
) -> list[SubtitleSegment]:
    """Convert translated segments to regular segments using translated text."""
    return [
        SubtitleSegment(id=seg.id, start=seg.start, end=seg.end, text=seg.translated_text)
        for seg in segments
    ]


def write_subtitle_file(content: str, output_path: str) -> str:
    """Write subtitle content to file."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return output_path
