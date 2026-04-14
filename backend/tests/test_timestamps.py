from app.utils.timestamps import seconds_to_srt_timestamp, seconds_to_vtt_timestamp


class TestSRTTimestamp:
    def test_zero(self):
        assert seconds_to_srt_timestamp(0.0) == "00:00:00,000"

    def test_simple(self):
        assert seconds_to_srt_timestamp(1.5) == "00:00:01,500"

    def test_minutes(self):
        assert seconds_to_srt_timestamp(65.123) == "00:01:05,123"

    def test_hours(self):
        assert seconds_to_srt_timestamp(3661.999) == "01:01:01,999"

    def test_negative_clamped(self):
        assert seconds_to_srt_timestamp(-5.0) == "00:00:00,000"

    def test_large_value(self):
        assert seconds_to_srt_timestamp(86400.0) == "24:00:00,000"

    def test_millisecond_rounding(self):
        result = seconds_to_srt_timestamp(1.9999)
        assert result == "00:00:02,000" or result == "00:00:01,999"


class TestVTTTimestamp:
    def test_zero(self):
        assert seconds_to_vtt_timestamp(0.0) == "00:00:00.000"

    def test_simple(self):
        assert seconds_to_vtt_timestamp(1.5) == "00:00:01.500"

    def test_uses_dot_not_comma(self):
        result = seconds_to_vtt_timestamp(2.345)
        assert "." in result
        assert "," not in result

    def test_minutes(self):
        assert seconds_to_vtt_timestamp(125.750) == "00:02:05.750"

    def test_negative_clamped(self):
        assert seconds_to_vtt_timestamp(-1.0) == "00:00:00.000"
