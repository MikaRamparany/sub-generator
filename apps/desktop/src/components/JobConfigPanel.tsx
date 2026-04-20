import { useState } from "react";
import type { AudioTrack, JobConfig, ProbeResult } from "../types";
import { AVAILABLE_LANGUAGES } from "../types";

interface Props {
  probe: ProbeResult | null;
  videoPath: string;
  subtitlePath?: string;
  onStart: (config: JobConfig) => void;
  disabled: boolean;
}

export function JobConfigPanel({ probe, videoPath, subtitlePath, onStart, disabled }: Props) {
  const isSubtitleMode = Boolean(subtitlePath);
  const [audioTrack, setAudioTrack] = useState(probe?.audio_tracks[0]?.index ?? 0);
  const [sourceLanguage, setSourceLanguage] = useState("auto");
  const [targetLanguages, setTargetLanguages] = useState<string[]>([]);
  const [qualityMode, setQualityMode] = useState<"fast" | "high_quality">("fast");
  const [pipelineMode, setPipelineMode] = useState<"standard" | "premium">("standard");

  const toggleLang = (code: string) => {
    setTargetLanguages((prev) =>
      prev.includes(code) ? prev.filter((l) => l !== code) : [...prev, code]
    );
  };

  const canSubmit = isSubtitleMode ? targetLanguages.length > 0 : true;

  const handleStart = () => {
    if (!canSubmit) return;
    onStart({
      input_video_path: isSubtitleMode ? "" : videoPath,
      input_subtitle_path: subtitlePath || "",
      audio_track_index: audioTrack,
      source_language: sourceLanguage,
      target_languages: targetLanguages,
      output_formats: ["srt", "vtt"],
      quality_mode: qualityMode,
      translation_mode: "balanced",
      pipeline_mode: pipelineMode,
    });
  };

  return (
    <div className="job-config">

      {/* Audio track — only if multiple tracks */}
      {!isSubtitleMode && probe && probe.audio_tracks.length > 1 && (
        <div className="config-section">
          <div className="config-label">Audio Track</div>
          <select
            className="config-select"
            value={audioTrack}
            onChange={(e) => setAudioTrack(Number(e.target.value))}
            disabled={disabled}
          >
            {probe.audio_tracks.map((track: AudioTrack) => (
              <option key={track.index} value={track.index}>
                Track {track.index}
                {track.language ? ` · ${track.language}` : ""}
                {track.codec ? ` · ${track.codec}` : ""}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Source language */}
      <div className="config-section">
        <div className="config-label">Source Language</div>
        <select
          className="config-select"
          value={sourceLanguage}
          onChange={(e) => setSourceLanguage(e.target.value)}
          disabled={disabled}
        >
          <option value="auto">Auto-detect</option>
          {AVAILABLE_LANGUAGES.map((l) => (
            <option key={l.code} value={l.code}>{l.name}</option>
          ))}
        </select>
      </div>

      {/* Target languages */}
      <div className="config-section">
        <div className="config-label">
          {isSubtitleMode ? "Translate to — required" : "Translate to — optional"}
        </div>
        <div className="lang-chips">
          {AVAILABLE_LANGUAGES.map((l) => (
            <button
              key={l.code}
              className={`lang-chip ${targetLanguages.includes(l.code) ? "selected" : ""}`}
              onClick={() => toggleLang(l.code)}
              disabled={disabled}
            >
              {l.name}
            </button>
          ))}
        </div>
      </div>

      {/* Quality mode — video only */}
      {!isSubtitleMode && (
        <div className="config-section">
          <div className="config-label">Transcription Quality</div>
          <div className="segmented-control">
            <button
              className={`seg-btn ${qualityMode === "fast" ? "active" : ""}`}
              onClick={() => setQualityMode("fast")}
              disabled={disabled}
            >
              Fast
              <span className="seg-btn-sub">Whisper Turbo</span>
            </button>
            <button
              className={`seg-btn ${qualityMode === "high_quality" ? "active" : ""}`}
              onClick={() => setQualityMode("high_quality")}
              disabled={disabled}
            >
              High Quality
              <span className="seg-btn-sub">Whisper Large v3</span>
            </button>
          </div>
        </div>
      )}

      {/* Pipeline mode */}
      <div className="config-section">
        <div className="config-label">Pipeline</div>
        <div className="segmented-control">
          <button
            className={`seg-btn ${pipelineMode === "standard" ? "active" : ""}`}
            onClick={() => setPipelineMode("standard")}
            disabled={disabled}
          >
            Standard
            <span className="seg-btn-sub">Fast · cost-efficient</span>
          </button>
          <button
            className={`seg-btn ${pipelineMode === "premium" ? "active" : ""}`}
            onClick={() => setPipelineMode("premium")}
            disabled={disabled}
          >
            Premium
            <span className="seg-btn-sub">Context analysis · QA</span>
          </button>
        </div>
      </div>

      {/* Submit */}
      <div className="config-submit">
        <button
          className="btn-primary"
          onClick={handleStart}
          disabled={disabled || !canSubmit}
        >
          {isSubtitleMode ? "Translate Subtitles" : "Generate Subtitles"}
        </button>
      </div>
    </div>
  );
}
