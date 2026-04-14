import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VideoInfo } from "../components/VideoInfo";
import type { ProbeResult } from "../types";

const probe: ProbeResult = {
  file_name: "test_video.mp4",
  file_size_mb: 125.4,
  duration_seconds: 3665,
  video_format: "mp4",
  audio_tracks: [
    { index: 0, codec: "aac", channels: 2, language: "en" },
  ],
};

describe("VideoInfo", () => {
  it("displays file name", () => {
    render(<VideoInfo probe={probe} />);
    expect(screen.getByText("test_video.mp4")).toBeInTheDocument();
  });

  it("displays file size", () => {
    render(<VideoInfo probe={probe} />);
    expect(screen.getByText("125.4 MB")).toBeInTheDocument();
  });

  it("formats duration with hours", () => {
    render(<VideoInfo probe={probe} />);
    // 3665s = 1h 1m 5s
    expect(screen.getByText("1h 1m 5s")).toBeInTheDocument();
  });

  it("displays track count", () => {
    render(<VideoInfo probe={probe} />);
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("displays format in uppercase", () => {
    render(<VideoInfo probe={probe} />);
    expect(screen.getByText("MP4")).toBeInTheDocument();
  });
});
