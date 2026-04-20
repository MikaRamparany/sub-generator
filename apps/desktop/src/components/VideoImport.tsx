import { useState } from "react";
import { getAbsolutePathFromFile, openVideoFileDialog } from "../lib/tauri";
import { probeSubtitle, probeVideo } from "../services/api";
import type { ProbeResult, SubtitleFileInfo } from "../types";
import { SUPPORTED_FORMATS, SUPPORTED_SUBTITLE_FORMATS } from "../types";

const ALL_EXTENSIONS = [...SUPPORTED_FORMATS, ...SUPPORTED_SUBTITLE_FORMATS];

interface Props {
  onProbeComplete: (result: ProbeResult, videoPath: string) => void;
  onSubtitleImport: (info: SubtitleFileInfo, filePath: string) => void;
}

function getExtension(filePath: string): string {
  return filePath.split(".").pop()?.toLowerCase() ?? "";
}

export function VideoImport({ onProbeComplete, onSubtitleImport }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const handleAbsolutePath = async (filePath: string) => {
    setError(null);
    const ext = getExtension(filePath);
    if (!ALL_EXTENSIONS.includes(ext)) {
      setError(`Unsupported format: .${ext}`);
      return;
    }
    setLoading(true);
    try {
      if (SUPPORTED_SUBTITLE_FORMATS.includes(ext)) {
        const info = await probeSubtitle(filePath);
        onSubtitleImport(info, filePath);
      } else {
        const result = await probeVideo(filePath);
        onProbeComplete(result, filePath);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to analyze file");
    } finally {
      setLoading(false);
    }
  };

  const handleBrowseClick = async () => {
    setError(null);
    try {
      const path = await openVideoFileDialog();
      if (path) await handleAbsolutePath(path);
    } catch (e) {
      setError(e instanceof Error ? e.message : "File dialog error");
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    setError(null);
    const file = e.dataTransfer.files[0];
    if (!file) return;
    const path = getAbsolutePathFromFile(file);
    if (path) {
      await handleAbsolutePath(path);
    } else {
      setError("Could not get file path. Try the Browse button.");
    }
  };

  return (
    <div className="video-import">
      <div
        className={`drop-zone ${dragOver ? "drag-over" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={handleBrowseClick}
      >
        {loading ? (
          <div className="drop-zone-loading">
            <div className="spinner" />
            Analyzing file…
          </div>
        ) : (
          <>
            <div className="drop-icon-wrap">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
            </div>
            <p className="drop-title">Drop a file or click to browse</p>
            <p className="drop-sub">Video or subtitle file</p>
            <div className="drop-formats">
              {ALL_EXTENSIONS.map((ext) => (
                <span key={ext} className="format-tag">{ext}</span>
              ))}
            </div>
          </>
        )}
      </div>
      {error && <p className="error-message">{error}</p>}
    </div>
  );
}
