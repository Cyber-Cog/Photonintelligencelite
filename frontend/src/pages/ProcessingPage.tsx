import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, getJobStatus } from "@/api/client";
import { AnalysisConsole } from "@/components/processing/AnalysisConsole";
import { ChartPrepPanel } from "@/components/processing/ChartPrepPanel";
import { useAnalysisLog } from "@/components/processing/useAnalysisLog";
import { StepIndicator } from "@/components/StepIndicator";
import { ErrorState } from "@/components/ui/ErrorState";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Spinner } from "@/components/ui/Spinner";
import type { JobStatusResponse } from "@/types";

const POLL_INTERVAL_MS = 2000;

const STATE_LABELS: Record<string, string> = {
  uploaded: "Upload received",
  parsing: "Parsing file",
  mapping: "Awaiting column mapping",
  validating: "Validating data",
  normalizing: "Finalizing validation",
  queued: "Queued for analysis",
  running: "Running fault & loss algorithms",
  generating_charts: "Generating charts",
  generating_report: "Building reports",
  completed: "Completed",
  failed: "Failed",
  cleaned_up: "Cleaned up",
};

const FALLBACK_QUEUED_MESSAGE =
  "Your analysis is queued — other analyses are running in parallel; you'll start when a worker is free.";

const PROGRESS_ORDER = [
  "uploaded",
  "parsing",
  "mapping",
  "validating",
  "normalizing",
  "queued",
  "running",
  "generating_charts",
  "generating_report",
  "completed",
];

function progressPct(state: string): number {
  const idx = PROGRESS_ORDER.indexOf(state);
  if (idx < 0) return 0;
  return Math.round(((idx + 1) / PROGRESS_ORDER.length) * 100);
}

function formatElapsed(sec: number): string {
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

function stateLabelFor(status: JobStatusResponse | null): string {
  if (!status) return "Starting analysis service…";
  if (status.state === "validating" && (status.is_demo || /demo/i.test(status.progress_message ?? ""))) {
    return "Preparing demo data";
  }
  return STATE_LABELS[status.state] ?? status.state;
}

export function ProcessingPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const [status, setStatus] = useState<JobStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startedAtRef = useRef(Date.now());

  useEffect(() => {
    startedAtRef.current = Date.now();
    const id = window.setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - startedAtRef.current) / 1000));
    }, 1000);
    return () => window.clearInterval(id);
  }, [jobId]);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;

    const schedule = (ms: number) => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(poll, ms);
    };

    const poll = async () => {
      // Pause aggressive polling when the tab is hidden (saves CPU for Cursor/IDE too).
      if (typeof document !== "undefined" && document.hidden) {
        schedule(POLL_INTERVAL_MS * 4);
        return;
      }
      try {
        const res = await getJobStatus(jobId);
        if (cancelled) return;
        setStatus(res);
        setError(null);
        if (res.state === "completed") {
          navigate(`/jobs/${jobId}/dashboard`);
          return;
        }
        if (res.is_active) {
          schedule(POLL_INTERVAL_MS);
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Lost connection while checking job status.");
        schedule(POLL_INTERVAL_MS);
      }
    };

    const onVisibility = () => {
      if (!document.hidden) poll();
    };
    document.addEventListener("visibilitychange", onVisibility);
    poll();
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibility);
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [jobId, navigate]);

  const failed = status?.state === "failed";
  const live = Boolean(status?.is_active) && !failed;
  const stateLabel = stateLabelFor(status);
  const detail =
    status?.state === "queued"
      ? status.progress_message &&
        !status.progress_message.startsWith("Another job is currently running")
        ? status.progress_message
        : FALLBACK_QUEUED_MESSAGE
      : status?.progress_message ??
        (elapsedSec >= 15
          ? "Free-tier analysis is CPU-bound — this often takes a few minutes when warm."
          : "This can take a moment on a cold service start.");

  const logLines = useAnalysisLog(
    status?.state,
    status?.progress_message,
    status?.queue_position,
    elapsedSec,
    {
      isDemo: status?.is_demo,
      filename: status?.original_filename,
    },
  );

  if (!jobId) return null;

  return (
    <div className="proc-screen tool-enter relative flex min-h-0 w-full flex-1 flex-col overflow-hidden">
      <div className="proc-screen-grid pointer-events-none absolute inset-0" aria-hidden />

      <div className="relative z-[1] flex min-h-0 flex-1 flex-col gap-2 pb-0.5 pt-0.5">
        <div className="shrink-0">
          <StepIndicator current={4} jobId={jobId} />
        </div>

        {failed ? (
          <div className="mx-auto w-full max-w-xl overflow-y-auto">
            <ErrorState
              title="Analysis failed"
              message={status?.error_summary ?? "The job could not be completed."}
              hint="You can fix column mapping on the existing upload, or start over with a new file."
            />
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <button type="button" className="btn-primary" onClick={() => navigate(`/jobs/${jobId}/setup`)}>
                Fix column mapping
              </button>
              <button type="button" className="btn-secondary" onClick={() => navigate(`/jobs/${jobId}/validate`)}>
                Back to validation
              </button>
              <button type="button" className="btn-ghost" onClick={() => navigate(`/upload?replace=${jobId}`)}>
                Replace files / Back to upload
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* Compact status — one row on sm+ so console/chart keep the height */}
            <header className="proc-status-strip flex shrink-0 items-center gap-3 rounded-lg border border-stone-200/90 bg-white/90 px-2.5 py-2 shadow-sm shadow-stone-900/[0.03] dark:border-stone-700 dark:bg-stone-900/90 dark:shadow-none sm:px-3">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-brand-50 dark:bg-brand-950/40">
                <Spinner className="h-3.5 w-3.5" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0">
                  <h2 className="font-display text-sm font-semibold leading-tight tracking-tight text-stone-900 dark:text-stone-50 sm:text-base">
                    {stateLabel}
                  </h2>
                  <span className="text-[10px] font-medium uppercase tracking-wide text-stone-400">
                    {formatElapsed(elapsedSec)}
                  </span>
                </div>
                <p className="mt-0.5 truncate text-xs leading-snug text-stone-500 dark:text-stone-400" title={detail}>
                  {detail}
                  {status?.queue_position != null && status.queue_position > 0
                    ? ` · Queue #${status.queue_position}`
                    : ""}
                </p>
              </div>
              {status && (
                <div className="w-[7.5rem] shrink-0 sm:w-40">
                  <div className="mb-1 flex justify-between text-[10px] font-semibold uppercase tracking-wide text-stone-400">
                    <span>Pipeline</span>
                    <span className="tabular-nums text-brand-700 dark:text-brand-400">
                      {progressPct(status.state)}%
                    </span>
                  </div>
                  <div className="proc-progress-pulse">
                    <ProgressBar pct={progressPct(status.state)} />
                  </div>
                </div>
              )}
            </header>

            {error && <p className="shrink-0 text-xs text-rose-500">{error}</p>}

            {/* Fill leftover viewport only — panels scroll internally; no giant min-heights */}
            <div className="flex min-h-0 flex-1 flex-col gap-2 lg:flex-row">
              <AnalysisConsole lines={logLines} live={live} />
              <ChartPrepPanel state={status?.state} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
