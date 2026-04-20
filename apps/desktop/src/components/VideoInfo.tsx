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
    <div className="file-card">
      <div className="file-card-icon">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="23 7 16 12 23 17 23 7" />
          <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
        </svg>
      </div>
      <div className="file-card-body">
        <div className="file-card-name">{probe.file_name}</div>
        <div className="file-card-meta">
          <span>{probe.file_size_mb.toFixed(1)} MB</span>
          <span>{formatDuration(probe.duration_seconds)}</span>
          <span>{probe.video_format.toUpperCase()}</span>
          {probe.audio_tracks.length > 1 && (
            <span>{probe.audio_tracks.length} audio tracks</span>
          )}
        </div>
      </div>
    </div>
  );
}
