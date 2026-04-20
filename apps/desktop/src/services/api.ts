import type {
  DownloadListResponse,
  JobConfig,
  JobStatus,
  PreviewResponse,
  ProbeResult,
  SubtitleFileInfo,
} from "../types";

// In dev mode, Vite proxies /api → http://127.0.0.1:8000.
// In the bundled app there is no proxy, so we need the absolute URL.
const BASE_URL =
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window
    ? "http://127.0.0.1:8000/api"
    : "/api";

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || `Request failed: ${response.status}`);
  }

  return response.json();
}

export async function probeVideo(videoPath: string): Promise<ProbeResult> {
  return request<ProbeResult>("/videos/probe", {
    method: "POST",
    body: JSON.stringify({ video_path: videoPath }),
  });
}

export async function probeSubtitle(filePath: string): Promise<SubtitleFileInfo> {
  return request<SubtitleFileInfo>("/subtitles/probe", {
    method: "POST",
    body: JSON.stringify({ video_path: filePath }),
  });
}

export async function createJob(config: JobConfig): Promise<string> {
  const result = await request<{ job_id: string }>("/jobs", {
    method: "POST",
    body: JSON.stringify(config),
  });
  return result.job_id;
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  return request<JobStatus>(`/jobs/${jobId}`);
}

export async function getJobPreview(jobId: string): Promise<PreviewResponse> {
  return request<PreviewResponse>(`/jobs/${jobId}/preview`);
}

export async function getJobDownloads(jobId: string): Promise<DownloadListResponse> {
  return request<DownloadListResponse>(`/jobs/${jobId}/downloads`);
}

export function getDownloadUrl(jobId: string, fileName: string): string {
  return `${BASE_URL}/jobs/${jobId}/downloads/${encodeURIComponent(fileName)}`;
}

export async function deleteJob(jobId: string): Promise<void> {
  await request(`/jobs/${jobId}`, { method: "DELETE" });
}
