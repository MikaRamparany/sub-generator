import { useState } from "react";
import { getAbsolutePathFromFile, isTauri, openVideoFileDialog } from "../lib/tauri";
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
      setError(
        `Unsupported format: .${ext}. Supported: ${ALL_EXTENSIONS.join(", ")}`
      );
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
      const msg = e instanceof Error ? e.message : String(e);
      setError(`File dialog error: ${msg}`);
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
    } else if (!isTauri()) {
      setError(
        "File paths are not accessible in browser mode. " +
          "Run the app with: npm run tauri dev"
      );
    } else {
      setError(
        "Could not get the file path. Try using the Browse button instead."
      );
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
          <p>Analyzing file...</p>
        ) : (
          <>
            <p className="drop-icon">🎬</p>
            <p>Drop a video or subtitle file here, or click to browse</p>
            <p className="hint">Video: MP4, MOV, MKV, AVI, WEBM</p>
            <p className="hint">Subtitles: SRT, VTT (translation only)</p>
            {!isTauri() && (
              <p className="hint" style={{ color: "#f59e0b", marginTop: 8 }}>
                ⚠ Browser mode — run with{" "}
                <code>npm run tauri dev</code> for full functionality
              </p>
            )}
          </>
        )}
      </div>
      {error && <p className="error-message">{error}</p>}
    </div>
  );
}
