import { useEffect, useState } from "react";
import { getDownloadUrl, getJobDownloads } from "../services/api";
import type { ExportFile } from "../types";

interface Props {
  jobId: string;
}

export function DownloadsPanel({ jobId }: Props) {
  const [files, setFiles] = useState<ExportFile[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJobDownloads(jobId)
      .then((res) => setFiles(res.files))
      .catch((e) => setError(e.message));
  }, [jobId]);

  if (error) return <p className="error-message">{error}</p>;
  if (files.length === 0) return <p className="hint">No exports available yet</p>;

  return (
    <div className="downloads-panel">
      <h3>Downloads</h3>
      <div className="downloads-list">
        {files.map((file) => (
          <a
            key={file.file_name}
            className="download-item"
            href={getDownloadUrl(jobId, file.file_name)}
            download={file.file_name}
          >
            <span className="file-name">{file.file_name}</span>
            <span className="file-badge">{file.format.toUpperCase()}</span>
          </a>
        ))}
      </div>
    </div>
  );
}
