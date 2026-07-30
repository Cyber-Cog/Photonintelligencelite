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
  validating: "Preparing demo data",
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
  const stateLabel = status ? STATE_LABELS[status.state] ?? status.state : "Starting analysis service…";
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
  );

  if (!jobId) return null;

  return (
    <div className="proc-screen tool-enter relative mx-auto flex w-full max-w-6xl flex-1 flex-col">
      <div className="proc-screen-grid pointer-events-none absolute inset-0" aria-hidden />

      <div className="relative z-[1] flex min-h-0 flex-1 flex-col gap-4 pb-2 pt-1">
        <StepIndicator current={4} jobId={jobId} />

        {failed ? (
          <div className="mx-auto w-full max-w-xl">
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
            {/* Status strip */}
            <header className="proc-status-strip flex flex-col gap-3 rounded-2xl border border-stone-200/90 bg-white/90 px-4 py-3 shadow-sm shadow-stone-900/[0.03] dark:border-stone-700 dark:bg-stone-900/90 dark:shadow-none sm:flex-row sm:items-center sm:justify-between">
              <div className="flex min-w-0 items-start gap-3">
                <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 dark:bg-brand-950/40">
                  <Spinner className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <p className="tool-eyebrow mb-0.5">In progress · {formatElapsed(elapsedSec)}</p>
                  <h2 className="font-display text-lg font-semibold tracking-tight text-stone-900 dark:text-stone-50 sm:text-xl">
                    {stateLabel}
                  </h2>
                  <p className="mt-0.5 text-sm text-stone-500 dark:text-stone-400">{detail}</p>
                  {status?.queue_position != null && status.queue_position > 0 && (
                    <p className="mt-1 text-xs text-stone-400">
                      In queue (workers busy) · Position {status.queue_position}
                      {status.estimated_wait_seconds != null &&
                        ` · Est. wait ${Math.round(status.estimated_wait_seconds)}s`}
                    </p>
                  )}
                </div>
              </div>
              {status && (
                <div className="w-full shrink-0 sm:w-48">
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

            {error && <p className="text-xs text-rose-500">{error}</p>}

            {/* Main workspace: console + chart prep */}
            <div className="flex min-h-[min(62vh,36rem)] flex-1 flex-col gap-3 lg:min-h-[28rem] lg:flex-row">
              <AnalysisConsole lines={logLines} live={live} />
              <ChartPrepPanel state={status?.state} />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
