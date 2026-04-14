import { useCallback, useEffect, useRef, useState } from "react";
import { getJobStatus } from "../services/api";
import type { JobStatus } from "../types";

const POLL_INTERVAL_MS = 1500;

export function useJobPolling(jobId: string | null) {
  const [status, setStatus] = useState<JobStatus | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!jobId) {
      setStatus(null);
      return;
    }

    const poll = async () => {
      try {
        const s = await getJobStatus(jobId);
        setStatus(s);
        if (s.state === "completed" || s.state === "failed") {
          stopPolling();
        }
      } catch {
        stopPolling();
      }
    };

    poll();
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);

    return stopPolling;
  }, [jobId, stopPolling]);

  return status;
}
