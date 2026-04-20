import { useEffect, useState } from "react";
import { getJobPreview } from "../services/api";
import type { PreviewResponse } from "../types";

interface Props {
  jobId: string;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function SubtitlePreview({ jobId }: Props) {
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [selectedLang, setSelectedLang] = useState<string>("source");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJobPreview(jobId).then(setPreview).catch((e) => setError(e.message));
  }, [jobId]);

  if (error) return <p className="error-message">{error}</p>;
  if (!preview) return null;

  const languages = Object.keys(preview.translations);
  const segments =
    selectedLang === "source"
      ? preview.source_segments
      : (preview.translations[selectedLang] ?? []).map((s) => ({
          id: s.id,
          start: s.start,
          end: s.end,
          text: s.translated_text,
        }));

  return (
    <div className="subtitle-preview">
      <div className="preview-header">
        <span className="preview-header-title">Preview</span>
        <div className="preview-lang-tabs">
          <button
            className={`preview-lang-btn ${selectedLang === "source" ? "active" : ""}`}
            onClick={() => setSelectedLang("source")}
          >
            Source
          </button>
          {languages.map((lang) => (
            <button
              key={lang}
              className={`preview-lang-btn ${selectedLang === lang ? "active" : ""}`}
              onClick={() => setSelectedLang(lang)}
            >
              {lang.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
      <div className="segments-list">
        {segments.length === 0 ? (
          <p className="hint" style={{ padding: "16px 18px" }}>No segments available</p>
        ) : (
          segments.map((seg) => (
            <div key={seg.id} className="segment-row">
              <span className="segment-id">#{seg.id}</span>
              <span className="segment-time">
                {formatTime(seg.start)} → {formatTime(seg.end)}
              </span>
              <span className="segment-text">{seg.text}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
