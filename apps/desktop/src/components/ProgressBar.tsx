import type { JobStatus } from "../types";
import { JOB_STATE_LABELS } from "../types";

interface Props {
  status: JobStatus;
}

export function ProgressBar({ status }: Props) {
  const label = JOB_STATE_LABELS[status.state] ?? status.state;
  const percent = Math.round(status.progress * 100);
  const isFailed = status.state === "failed";
  const isComplete = status.state === "completed";

  return (
    <div className="progress-section">
      <div className="progress-header">
        <span className={`status-label ${isFailed ? "error" : isComplete ? "success" : ""}`}>
          {label}
        </span>
        <span className="progress-percent">{percent}%</span>
      </div>
      <div className="progress-bar-track">
        <div
          className={`progress-bar-fill ${isFailed ? "error" : isComplete ? "success" : ""}`}
          style={{ width: `${percent}%` }}
        />
      </div>
      {status.message && (
        <p className={`progress-message ${isFailed ? "error" : ""}`}>{status.message}</p>
      )}
    </div>
  );
}
