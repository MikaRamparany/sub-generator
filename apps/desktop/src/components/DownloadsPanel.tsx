import { useEffect, useState } from "react";
import { getJobDownloads } from "../services/api";
import { isTauri } from "../lib/tauri";
import type { ExportFile } from "../types";

interface Props {
  jobId: string;
}

const BACKEND_BASE = "http://127.0.0.1:8000/api";

async function saveBlob(blob: Blob, defaultName: string): Promise<void> {
  if (isTauri()) {
    const { save } = await import("@tauri-apps/plugin-dialog");
    const { writeFile } = await import("@tauri-apps/plugin-fs");

    const path = await save({ defaultPath: defaultName });
    if (!path) return; // user cancelled

    const buffer = new Uint8Array(await blob.arrayBuffer());
    await writeFile(path, buffer);
  } else {
    // Browser fallback
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = defaultName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }
}

async function downloadFile(jobId: string, fileName: string): Promise<void> {
  const url = `${BACKEND_BASE}/jobs/${jobId}/downloads/${encodeURIComponent(fileName)}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Download failed: ${response.status}`);
  }
  const blob = await response.blob();
  await saveBlob(blob, fileName);
}

async function downloadZip(jobId: string): Promise<void> {
  const url = `${BACKEND_BASE}/jobs/${jobId}/downloads/zip`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Download failed: ${response.status}`);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="([^"]+)"/);
  const fileName = match ? match[1] : "subtitles.zip";
  await saveBlob(blob, fileName);
}

export function DownloadsPanel({ jobId }: Props) {
  const [files, setFiles] = useState<ExportFile[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [downloadingZip, setDownloadingZip] = useState(false);

  useEffect(() => {
    getJobDownloads(jobId)
      .then((res) => setFiles(res.files))
      .catch((e) => setError(e.message));
  }, [jobId]);

  const handleDownloadZip = async () => {
    setDownloadingZip(true);
    try {
      await downloadZip(jobId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setDownloadingZip(false);
    }
  };

  const handleDownload = async (file: ExportFile) => {
    setDownloading(file.file_name);
    try {
      await downloadFile(jobId, file.file_name);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setDownloading(null);
    }
  };

  if (error) return <p className="error-message">{error}</p>;
  if (files.length === 0) return <p className="hint">No exports available yet</p>;

  return (
    <div className="downloads-panel">
      <h3>Downloads</h3>
      <div className="downloads-list">
        {files.map((file) => (
          <button
            key={file.file_name}
            className="download-item"
            onClick={() => handleDownload(file)}
            disabled={downloading === file.file_name}
          >
            <span className="file-name">{file.file_name}</span>
            <span className="file-badge">
              {downloading === file.file_name ? "..." : file.format.toUpperCase()}
            </span>
          </button>
        ))}
      </div>
      <button
        className="download-zip-btn"
        onClick={handleDownloadZip}
        disabled={downloadingZip}
      >
        {downloadingZip ? "Preparing zip..." : "Download all (.zip)"}
      </button>
    </div>
  );
}
