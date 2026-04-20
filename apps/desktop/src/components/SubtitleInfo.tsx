import type { SubtitleFileInfo } from "../types";

interface Props {
  info: SubtitleFileInfo;
}

export function SubtitleInfo({ info }: Props) {
  return (
    <div className="file-card">
      <div className="file-card-icon">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
          <polyline points="10 9 9 9 8 9" />
        </svg>
      </div>
      <div className="file-card-body">
        <div className="file-card-name">{info.file_name}</div>
        <div className="file-card-meta">
          <span>{info.format.toUpperCase()}</span>
          <span>{info.segment_count} segments</span>
          <span>{info.file_size_mb.toFixed(2)} MB</span>
        </div>
      </div>
    </div>
  );
}
