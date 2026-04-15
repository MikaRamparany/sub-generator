import { useCallback, useEffect, useState } from "react";
import { DownloadsPanel } from "./components/DownloadsPanel";
import { JobConfigPanel } from "./components/JobConfigPanel";
import { ProgressBar } from "./components/ProgressBar";
import { SubtitleInfo } from "./components/SubtitleInfo";
import { SubtitlePreview } from "./components/SubtitlePreview";
import { VideoImport } from "./components/VideoImport";
import { VideoInfo } from "./components/VideoInfo";
import { useJobPolling } from "./hooks/useJobPolling";
import { createJob, deleteJob } from "./services/api";
import type { JobConfig, ProbeResult, SubtitleFileInfo } from "./types";

type AppStep = "import" | "configure" | "processing" | "done" | "failed";

export default function App() {
  const [step, setStep] = useState<AppStep>("import");
  const [probe, setProbe] = useState<ProbeResult | null>(null);
  const [subtitleInfo, setSubtitleInfo] = useState<SubtitleFileInfo | null>(null);
  const [videoPath, setVideoPath] = useState("");
  const [subtitlePath, setSubtitlePath] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const status = useJobPolling(jobId);

  // Transition step based on job status — never in render body
  useEffect(() => {
    if (!status) return;
    if (status.state === "completed" && step === "processing") {
      setStep("done");
    } else if (status.state === "failed" && step === "processing") {
      setStep("failed");
    }
  }, [status?.state, step]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleProbeComplete = useCallback((result: ProbeResult, path: string) => {
    setProbe(result);
    setSubtitleInfo(null);
    setVideoPath(path);
    setSubtitlePath("");
    setStep("configure");
    setError(null);
  }, []);

  const handleSubtitleImport = useCallback((info: SubtitleFileInfo, path: string) => {
    setSubtitleInfo(info);
    setProbe(null);
    setVideoPath("");
    setSubtitlePath(path);
    setStep("configure");
    setError(null);
  }, []);

  const handleStart = useCallback(async (config: JobConfig) => {
    setError(null);
    try {
      const id = await createJob(config);
      setJobId(id);
      setStep("processing");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start job");
    }
  }, []);

  const handleReset = useCallback(async () => {
    if (jobId) {
      try { await deleteJob(jobId); } catch { /* ignore cleanup errors */ }
    }
    setStep("import");
    setProbe(null);
    setSubtitleInfo(null);
    setVideoPath("");
    setSubtitlePath("");
    setJobId(null);
    setError(null);
  }, [jobId]);

  const showResults = step === "done" || step === "failed";
  const isSubtitleMode = Boolean(subtitleInfo);

  const renderFileInfo = () => {
    if (probe) return <VideoInfo probe={probe} />;
    if (subtitleInfo) return <SubtitleInfo info={subtitleInfo} />;
    return null;
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>Subtitle Generator</h1>
        {step !== "import" && (
          <button className="btn-secondary" onClick={handleReset}>
            New File
          </button>
        )}
      </header>

      <main className="app-main">
        {step === "import" && (
          <VideoImport
            onProbeComplete={handleProbeComplete}
            onSubtitleImport={handleSubtitleImport}
          />
        )}

        {step === "configure" && (
          <>
            {renderFileInfo()}
            <JobConfigPanel
              probe={probe}
              videoPath={videoPath}
              subtitlePath={subtitlePath || undefined}
              onStart={handleStart}
              disabled={false}
            />
          </>
        )}

        {step === "processing" && (
          <>
            {renderFileInfo()}
            {status && <ProgressBar status={status} />}
          </>
        )}

        {showResults && (
          <>
            {renderFileInfo()}
            {status && <ProgressBar status={status} />}
            {step === "failed" && (
              <p className="hint" style={{ marginTop: 8 }}>
                Partial exports may still be available below.
              </p>
            )}
            {jobId && <SubtitlePreview jobId={jobId} />}
            {jobId && <DownloadsPanel jobId={jobId} />}
          </>
        )}

        {error && <p className="error-message">{error}</p>}
      </main>
    </div>
  );
}
