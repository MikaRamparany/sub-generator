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
  const [outputFormats, setOutputFormats] = useState<string[]>(["srt", "vtt"]);
  const [qualityMode, setQualityMode] = useState<"fast" | "high_quality">("fast");
  const [translationMode, setTranslationMode] = useState<"fast" | "balanced" | "safe">("fast");

  const toggleLang = (code: string) => {
    setTargetLanguages((prev) =>
      prev.includes(code) ? prev.filter((l) => l !== code) : [...prev, code]
    );
  };

  const toggleFormat = (fmt: string) => {
    setOutputFormats((prev) =>
      prev.includes(fmt) ? prev.filter((f) => f !== fmt) : [...prev, fmt]
    );
  };

  const handleStart = () => {
    if (isSubtitleMode && targetLanguages.length === 0) return;
    if (!isSubtitleMode && outputFormats.length === 0) return;

    onStart({
      input_video_path: isSubtitleMode ? "" : videoPath,
      input_subtitle_path: subtitlePath || "",
      audio_track_index: audioTrack,
      source_language: sourceLanguage,
      target_languages: targetLanguages,
      output_formats: outputFormats,
      quality_mode: qualityMode,
      translation_mode: translationMode,
    });
  };

  return (
    <div className="job-config">
      <h3>Configuration</h3>

      {!isSubtitleMode && probe && probe.audio_tracks.length > 1 && (
        <div className="config-section">
          <label>Audio Track</label>
          <select
            value={audioTrack}
            onChange={(e) => setAudioTrack(Number(e.target.value))}
            disabled={disabled}
          >
            {probe.audio_tracks.map((track: AudioTrack) => (
              <option key={track.index} value={track.index}>
                Track {track.index}
                {track.language ? ` (${track.language})` : ""}
                {track.codec ? ` — ${track.codec}` : ""}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="config-section">
        <label>Source Language</label>
        <select
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

      <div className="config-section">
        <label>Translate to{isSubtitleMode && " (required)"}</label>
        <div className="checkbox-group">
          {AVAILABLE_LANGUAGES.map((l) => (
            <label key={l.code} className="checkbox-label">
              <input
                type="checkbox"
                checked={targetLanguages.includes(l.code)}
                onChange={() => toggleLang(l.code)}
                disabled={disabled}
              />
              {l.name}
            </label>
          ))}
        </div>
      </div>

      <div className="config-section">
        <label>Export Formats</label>
        <div className="checkbox-group">
          {["srt", "vtt"].map((fmt) => (
            <label key={fmt} className="checkbox-label">
              <input
                type="checkbox"
                checked={outputFormats.includes(fmt)}
                onChange={() => toggleFormat(fmt)}
                disabled={disabled}
              />
              .{fmt}
            </label>
          ))}
        </div>
      </div>

      {!isSubtitleMode && (
        <div className="config-section">
          <label>Quality Mode</label>
          <div className="radio-group">
            <label className="radio-label">
              <input
                type="radio"
                name="quality"
                checked={qualityMode === "fast"}
                onChange={() => setQualityMode("fast")}
                disabled={disabled}
              />
              Fast
            </label>
            <label className="radio-label">
              <input
                type="radio"
                name="quality"
                checked={qualityMode === "high_quality"}
                onChange={() => setQualityMode("high_quality")}
                disabled={disabled}
              />
              High Quality
            </label>
          </div>
        </div>
      )}

      {targetLanguages.length > 0 && (
        <div className="config-section">
          <label>Translation Mode</label>
          <div className="radio-group">
            <label className="radio-label">
              <input
                type="radio"
                name="translation_mode"
                checked={translationMode === "fast"}
                onChange={() => setTranslationMode("fast")}
                disabled={disabled}
              />
              Fast
            </label>
            <label className="radio-label">
              <input
                type="radio"
                name="translation_mode"
                checked={translationMode === "balanced"}
                onChange={() => setTranslationMode("balanced")}
                disabled={disabled}
              />
              Balanced <span className="hint">(recommandé pour les longs films)</span>
            </label>
            <label className="radio-label">
              <input
                type="radio"
                name="translation_mode"
                checked={translationMode === "safe"}
                onChange={() => setTranslationMode("safe")}
                disabled={disabled}
              />
              Safe <span className="hint">(très patient, mais lent)</span>
            </label>
          </div>
        </div>
      )}

      <button
        className="btn-primary"
        onClick={handleStart}
        disabled={
          disabled ||
          (isSubtitleMode ? targetLanguages.length === 0 : outputFormats.length === 0)
        }
      >
        {isSubtitleMode ? "Translate Subtitles" : "Generate Subtitles"}
      </button>
    </div>
  );
}
