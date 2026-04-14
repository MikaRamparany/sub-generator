import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DownloadsPanel } from "../components/DownloadsPanel";
import type { DownloadListResponse } from "../types";

vi.mock("../services/api", () => ({
  getJobDownloads: vi.fn(),
  getDownloadUrl: (jobId: string, fileName: string) =>
    `/api/jobs/${jobId}/downloads/${fileName}`,
}));

describe("DownloadsPanel", () => {
  it("shows placeholder when no files", async () => {
    const { getJobDownloads } = await import("../services/api");
    vi.mocked(getJobDownloads).mockResolvedValue({ files: [] } as DownloadListResponse);

    render(<DownloadsPanel jobId="test-job" />);
    await waitFor(() => {
      expect(screen.getByText(/No exports available/i)).toBeInTheDocument();
    });
  });

  it("renders download links for each export file", async () => {
    const { getJobDownloads } = await import("../services/api");
    vi.mocked(getJobDownloads).mockResolvedValue({
      files: [
        { file_name: "video.original.srt", language: "original", format: "srt" },
        { file_name: "video.fr.vtt", language: "fr", format: "vtt" },
      ],
    } as DownloadListResponse);

    render(<DownloadsPanel jobId="test-job" />);
    await waitFor(() => {
      expect(screen.getByText("video.original.srt")).toBeInTheDocument();
      expect(screen.getByText("video.fr.vtt")).toBeInTheDocument();
    });
  });

  it("shows format badge for each file", async () => {
    const { getJobDownloads } = await import("../services/api");
    vi.mocked(getJobDownloads).mockResolvedValue({
      files: [
        { file_name: "video.original.srt", language: "original", format: "srt" },
      ],
    } as DownloadListResponse);

    render(<DownloadsPanel jobId="test-job" />);
    await waitFor(() => {
      expect(screen.getByText("SRT")).toBeInTheDocument();
    });
  });

  it("shows error message on API failure", async () => {
    const { getJobDownloads } = await import("../services/api");
    vi.mocked(getJobDownloads).mockRejectedValue(new Error("Network error"));

    render(<DownloadsPanel jobId="test-job" />);
    await waitFor(() => {
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });
  });
});
