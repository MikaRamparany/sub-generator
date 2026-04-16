export interface AudioTrack {
  index: number;
  codec: string | null;
  channels: number | null;
  language: string | null;
}

export interface ProbeResult {
  file_name: string;
  file_size_mb: number;
  duration_seconds: number;
  video_format: string;
  audio_tracks: AudioTrack[];
}

export interface SubtitleSegment {
  id: number;
  start: number;
  end: number;
  text: string;
}

export interface TranslatedSubtitleSegment {
  id: number;
  start: number;
  end: number;
  source_text: string;
  translated_text: string;
  target_language: string;
}

export interface SubtitleFileInfo {
  file_name: string;
  file_size_mb: number;
  segment_count: number;
  format: string;
}

export interface JobConfig {
  input_video_path: string;
  input_subtitle_path?: string;
  audio_track_index: number;
  source_language: string;
  target_languages: string[];
  output_formats: string[];
  quality_mode: "fast" | "high_quality";
  translation_mode: "fast" | "balanced" | "safe";
  // "standard": fast pipeline, cost-controlled
  // "premium": transcript analysis + context injection + prioritised QA
  pipeline_mode: "standard" | "premium";
}

export interface JobStatus {
  job_id: string;
  state: string;
  progress: number;
  message: string;
  error_code: string | null;
}

export interface ExportFile {
  file_name: string;
  language: string;
  format: string;
  // file_path is intentionally absent — the backend keeps it internal
}

export interface PreviewResponse {
  source_segments: SubtitleSegment[];
  translations: Record<string, TranslatedSubtitleSegment[]>;
}

export interface DownloadListResponse {
  files: ExportFile[];
}

export const SUPPORTED_FORMATS = ["mp4", "mov", "mkv", "avi", "webm"];

export const SUPPORTED_SUBTITLE_FORMATS = ["srt", "vtt"];

export const AVAILABLE_LANGUAGES = [
  { code: "fr", name: "Français" },
  { code: "en", name: "English" },
  { code: "es", name: "Español" },
  { code: "de", name: "Deutsch" },
];

export const JOB_STATE_LABELS: Record<string, string> = {
  idle: "Ready",
  probing: "Analyzing video...",
  extracting_audio: "Extracting audio...",
  chunking_audio: "Splitting audio...",
  transcribing: "Transcribing...",
  parsing_subtitles: "Parsing subtitles...",
  post_processing: "Cleaning up...",
  analysing_transcript: "Analysing transcript...",
  translating: "Translating...",
  completed: "Complete!",
  failed: "Failed",
};
