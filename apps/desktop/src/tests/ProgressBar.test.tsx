import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProgressBar } from "../components/ProgressBar";
import type { JobStatus } from "../types";

function makeStatus(overrides: Partial<JobStatus> = {}): JobStatus {
  return {
    job_id: "test-job",
    state: "transcribing",
    progress: 0.5,
    message: "Transcribing...",
    error_code: null,
    ...overrides,
  };
}

describe("ProgressBar", () => {
  it("shows progress percentage", () => {
    render(<ProgressBar status={makeStatus({ progress: 0.42 })} />);
    expect(screen.getByText("42%")).toBeInTheDocument();
  });

  it("shows the human-readable state label", () => {
    render(<ProgressBar status={makeStatus({ state: "transcribing", message: "" })} />);
    // The label maps "transcribing" → "Transcribing..." via JOB_STATE_LABELS
    expect(screen.getByText("Transcribing...")).toBeInTheDocument();
  });

  it("shows the message text", () => {
    render(<ProgressBar status={makeStatus({ message: "Processing chunk 1/3..." })} />);
    expect(screen.getByText("Processing chunk 1/3...")).toBeInTheDocument();
  });

  it("shows completed state", () => {
    render(<ProgressBar status={makeStatus({ state: "completed", progress: 1.0, message: "" })} />);
    expect(screen.getByText("Complete!")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  it("shows failed state with error class", () => {
    const { container } = render(
      <ProgressBar status={makeStatus({ state: "failed", message: "Something went wrong" })} />
    );
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(container.querySelector(".error")).toBeTruthy();
  });

  it("shows zero percent at start", () => {
    render(<ProgressBar status={makeStatus({ state: "idle", progress: 0 })} />);
    expect(screen.getByText("0%")).toBeInTheDocument();
  });
});
