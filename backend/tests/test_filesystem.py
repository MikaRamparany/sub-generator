from app.utils.filesystem import get_export_filename, get_video_base_name


class TestVideoBaseName:
    def test_simple(self):
        assert get_video_base_name("/path/to/video.mp4") == "video"

    def test_complex_name(self):
        assert get_video_base_name("/path/my video (2024).mkv") == "my video (2024)"


class TestExportFilename:
    def test_original_srt(self):
        assert get_export_filename("/path/video.mp4", "original", "srt") == "video.original.srt"

    def test_french_vtt(self):
        assert get_export_filename("/path/video.mp4", "fr", "vtt") == "video.fr.vtt"

    def test_english_srt(self):
        assert get_export_filename("/videos/my_movie.mov", "en", "srt") == "my_movie.en.srt"
