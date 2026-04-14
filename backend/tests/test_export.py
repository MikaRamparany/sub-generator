from app.models.schemas import SubtitleSegment, TranslatedSubtitleSegment
from app.services.subtitles.export_service import (
    segments_to_srt,
    segments_to_vtt,
    translated_segments_to_subtitle_segments,
)


def make_segments() -> list[SubtitleSegment]:
    return [
        SubtitleSegment(id=1, start=0.0, end=2.5, text="Hello world."),
        SubtitleSegment(id=2, start=2.6, end=5.1, text="How are you?"),
        SubtitleSegment(id=3, start=5.5, end=8.0, text="I am fine."),
    ]


class TestSRTGeneration:
    def test_basic_structure(self):
        srt = segments_to_srt(make_segments())
        lines = srt.strip().split("\n")
        assert lines[0] == "1"
        assert "-->" in lines[1]
        assert lines[2] == "Hello world."

    def test_segment_count(self):
        srt = segments_to_srt(make_segments())
        # Each segment is 3 lines + 1 blank = 4 lines, last has trailing blank
        blocks = [b for b in srt.strip().split("\n\n") if b.strip()]
        assert len(blocks) == 3

    def test_timestamp_format(self):
        srt = segments_to_srt(make_segments())
        assert "00:00:00,000 --> 00:00:02,500" in srt

    def test_empty_input(self):
        assert segments_to_srt([]) == ""


class TestVTTGeneration:
    def test_starts_with_webvtt(self):
        vtt = segments_to_vtt(make_segments())
        assert vtt.startswith("WEBVTT")

    def test_uses_dot_timestamps(self):
        vtt = segments_to_vtt(make_segments())
        assert "00:00:00.000 --> 00:00:02.500" in vtt

    def test_segment_text(self):
        vtt = segments_to_vtt(make_segments())
        assert "How are you?" in vtt

    def test_empty_input(self):
        vtt = segments_to_vtt([])
        assert vtt.strip() == "WEBVTT"


class TestTranslatedConversion:
    def test_uses_translated_text(self):
        translated = [
            TranslatedSubtitleSegment(
                id=1, start=0.0, end=2.5,
                source_text="Hello", translated_text="Bonjour",
                target_language="fr",
            ),
        ]
        result = translated_segments_to_subtitle_segments(translated)
        assert len(result) == 1
        assert result[0].text == "Bonjour"
        assert result[0].start == 0.0
        assert result[0].end == 2.5
