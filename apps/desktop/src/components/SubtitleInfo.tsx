import type { SubtitleFileInfo } from "../types";

interface Props {
  info: SubtitleFileInfo;
}

export function SubtitleInfo({ info }: Props) {
  return (
    <div className="video-info">
      <h3>Subtitle File</h3>
      <div className="info-grid">
        <span className="label">File:</span>
        <span>{info.file_name}</span>
        <span className="label">Size:</span>
        <span>{info.file_size_mb.toFixed(2)} MB</span>
        <span className="label">Format:</span>
        <span>{info.format.toUpperCase()}</span>
        <span className="label">Segments:</span>
        <span>{info.segment_count}</span>
      </div>
    </div>
  );
}
