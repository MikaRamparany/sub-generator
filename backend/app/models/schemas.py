from __future__ import annotations

from pydantic import BaseModel, Field


class AudioTrack(BaseModel):
    index: int
    codec: str | None = None
    channels: int | None = None
    language: str | None = None


class ProbeResult(BaseModel):
    file_name: str
    file_size_mb: float
    duration_seconds: float
    video_format: str
    audio_tracks: list[AudioTrack]


class SubtitleSegment(BaseModel):
    id: int
    start: float
    end: float
    text: str


class TranslatedSubtitleSegment(BaseModel):
    id: int
    start: float
    end: float
    source_text: str
    translated_text: str
    target_language: str


class SubtitleFileInfo(BaseModel):
    file_name: str
    file_size_mb: float
    segment_count: int
    format: str  # "srt" or "vtt"


class JobConfig(BaseModel):
    input_video_path: str = ""
    input_subtitle_path: str = ""  # if set, skip STT and use this file
    audio_track_index: int = 0
    source_language: str = "auto"
    target_languages: list[str] = Field(default_factory=list)
    output_formats: list[str] = Field(default_factory=lambda: ["srt", "vtt"])
    quality_mode: str = "fast"


class JobStatus(BaseModel):
    job_id: str
    state: str = "idle"
    progress: float = 0.0
    message: str = ""
    error_code: str | None = None
    # Languages that failed translation (for partial success reporting)
    failed_languages: list[str] = Field(default_factory=list)
    # Segments removed during post-processing (hallucinations, annotations)
    removed_segment_count: int = 0
    # Segments where translation fell back to source text (rate limit / batch failure)
    fallback_segment_count: int = 0


# Internal model — file_path is kept server-side only
class ExportFile(BaseModel):
    file_name: str
    language: str
    format: str
    file_path: str  # internal only, never sent to frontend


# Public model exposed via API — no local path leak
class ExportFilePublic(BaseModel):
    file_name: str
    language: str
    format: str


class PreviewResponse(BaseModel):
    source_segments: list[SubtitleSegment] = Field(default_factory=list)
    translations: dict[str, list[TranslatedSubtitleSegment]] = Field(default_factory=dict)


class DownloadListResponse(BaseModel):
    files: list[ExportFilePublic] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    error_code: str | None = None


class ProbeRequest(BaseModel):
    video_path: str
