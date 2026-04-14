import type { ProbeResult } from "../types";

interface Props {
  probe: ProbeResult;
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export function VideoInfo({ probe }: Props) {
  return (
    <div className="video-info">
      <h3>Video Information</h3>
      <div className="info-grid">
        <span className="label">File:</span>
        <span>{probe.file_name}</span>
        <span className="label">Size:</span>
        <span>{probe.file_size_mb.toFixed(1)} MB</span>
        <span className="label">Duration:</span>
        <span>{formatDuration(probe.duration_seconds)}</span>
        <span className="label">Format:</span>
        <span>{probe.video_format.toUpperCase()}</span>
        <span className="label">Audio tracks:</span>
        <span>{probe.audio_tracks.length}</span>
      </div>
    </div>
  );
}
