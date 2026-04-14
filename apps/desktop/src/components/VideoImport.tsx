import { useState } from "react";
import { getAbsolutePathFromFile, isTauri, openVideoFileDialog } from "../lib/tauri";
import { probeVideo } from "../services/api";
import type { ProbeResult } from "../types";
import { SUPPORTED_FORMATS } from "../types";

interface Props {
  onProbeComplete: (result: ProbeResult, videoPath: string) => void;
}

function hasValidExtension(filePath: string): boolean {
  const ext = filePath.split(".").pop()?.toLowerCase() ?? "";
  return SUPPORTED_FORMATS.includes(ext);
}

export function VideoImport({ onProbeComplete }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const handleAbsolutePath = async (filePath: string) => {
    setError(null);
    if (!hasValidExtension(filePath)) {
      const ext = filePath.split(".").pop() ?? "unknown";
      setError(
        `Unsupported format: .${ext}. Supported: ${SUPPORTED_FORMATS.join(", ")}`
      );
      return;
    }
    setLoading(true);
    try {
      const result = await probeVideo(filePath);
      onProbeComplete(result, filePath);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to analyze video");
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
      setError(e instanceof Error ? e.message : "Could not open file dialog");
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
          <p>Analyzing video...</p>
        ) : (
          <>
            <p className="drop-icon">🎬</p>
            <p>Drop a video here or click to browse</p>
            <p className="hint">Supported: MP4, MOV, MKV, AVI, WEBM</p>
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
