import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { VideoImport } from "../components/VideoImport";

// Mock the tauri module — no native APIs in test environment
vi.mock("../lib/tauri", () => ({
  isTauri: () => false,
  openVideoFileDialog: vi.fn(),
  getAbsolutePathFromFile: vi.fn(() => null),
}));

// Mock the API
vi.mock("../services/api", () => ({
  probeVideo: vi.fn(),
}));

describe("VideoImport", () => {
  it("renders the drop zone", () => {
    render(<VideoImport onProbeComplete={vi.fn()} />);
    expect(screen.getByText(/Drop a video here/i)).toBeInTheDocument();
  });

  it("lists supported formats", () => {
    render(<VideoImport onProbeComplete={vi.fn()} />);
    expect(screen.getByText(/MP4.*MOV.*MKV.*AVI.*WEBM/i)).toBeInTheDocument();
  });

  it("shows browser mode warning when not in Tauri", () => {
    render(<VideoImport onProbeComplete={vi.fn()} />);
    expect(screen.getByText(/Browser mode/i)).toBeInTheDocument();
    expect(screen.getByText(/npm run tauri dev/i)).toBeInTheDocument();
  });
});
