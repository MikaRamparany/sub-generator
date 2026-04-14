from app.models.schemas import SubtitleSegment
from app.services.subtitles.postprocess_service import (
    clean_segments,
    fix_invalid_durations,
    fix_overlaps,
    remove_empty_segments,
    sort_chronologically,
)


def seg(id: int, start: float, end: float, text: str = "text") -> SubtitleSegment:
    return SubtitleSegment(id=id, start=start, end=end, text=text)


class TestRemoveEmpty:
    def test_removes_empty_text(self):
        segs = [seg(1, 0, 1, "hello"), seg(2, 1, 2, ""), seg(3, 2, 3, "   ")]
        result = remove_empty_segments(segs)
        assert len(result) == 1

    def test_keeps_valid(self):
        segs = [seg(1, 0, 1, "hello"), seg(2, 1, 2, "world")]
        assert len(remove_empty_segments(segs)) == 2


class TestFixInvalidDurations:
    def test_removes_end_before_start(self):
        segs = [seg(1, 5.0, 3.0), seg(2, 1.0, 2.0)]
        result = fix_invalid_durations(segs)
        assert len(result) == 1
        assert result[0].id == 2

    def test_removes_zero_duration(self):
        segs = [seg(1, 1.0, 1.0)]
        assert len(fix_invalid_durations(segs)) == 0


class TestSortChronologically:
    def test_sorts_by_start(self):
        segs = [seg(1, 5.0, 6.0), seg(2, 1.0, 2.0), seg(3, 3.0, 4.0)]
        result = sort_chronologically(segs)
        assert [s.start for s in result] == [1.0, 3.0, 5.0]


class TestFixOverlaps:
    def test_trims_overlapping(self):
        segs = [seg(1, 0.0, 3.0), seg(2, 2.0, 5.0)]
        result = fix_overlaps(segs)
        assert result[0].end == 2.0
        assert result[1].start == 2.0

    def test_no_overlap_unchanged(self):
        segs = [seg(1, 0.0, 2.0), seg(2, 2.5, 4.0)]
        result = fix_overlaps(segs)
        assert result[0].end == 2.0


class TestCleanSegments:
    def test_full_pipeline(self):
        segs = [
            seg(1, 5.0, 6.0, "Second"),
            seg(2, 0.0, 3.0, "  First  "),
            seg(3, 2.5, 4.0, "Overlap"),
            seg(4, 10.0, 11.0, ""),
            seg(5, -1.0, 0.5, "Negative start"),
        ]
        result = clean_segments(segs)
        assert len(result) >= 3
        # Chronological order
        for i in range(len(result) - 1):
            assert result[i].start <= result[i + 1].start
        # No empty
        assert all(s.text.strip() for s in result)
        # Reindexed
        assert result[0].id == 1
