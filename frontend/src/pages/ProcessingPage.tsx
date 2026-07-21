import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, getJobStatus } from "@/api/client";
import { StepIndicator } from "@/components/StepIndicator";
import { ErrorState } from "@/components/ui/ErrorState";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Spinner } from "@/components/ui/Spinner";
import type { JobStatusResponse } from "@/types";

const POLL_INTERVAL_MS = 2500;

const STATE_LABELS: Record<string, string> = {
  uploaded: "Upload received",
  parsing: "Parsing file",
  mapping: "Awaiting column mapping",
  validating: "Validating data",
  normalizing: "Awaiting confirmation",
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

export function ProcessingPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const [status, setStatus] = useState<JobStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  if (!jobId) return null;

  const failed = status?.state === "failed";

  return (
    <div className="tool-enter mx-auto flex max-w-xl flex-1 flex-col items-center justify-center">
      <StepIndicator current={4} jobId={jobId} />
      <div className="w-full text-center">
        {!failed && (
          <>
            <div className="mb-4 flex justify-center">
              <Spinner className="h-8 w-8" />
            </div>
            <p className="tool-eyebrow mb-1.5">In progress</p>
            <h2 className="font-display text-xl font-semibold tracking-tight text-stone-900 dark:text-stone-50">
              {status ? STATE_LABELS[status.state] ?? status.state : "Starting analysis service…"}
            </h2>
            <p className="mt-1.5 text-sm text-stone-500">
              {status?.state === "queued"
                ? status.progress_message &&
                  !status.progress_message.startsWith("Another job is currently running")
                  ? status.progress_message
                  : FALLBACK_QUEUED_MESSAGE
                : (status?.progress_message ?? "This can take a moment on a cold service start.")}
            </p>
            {status && (
              <div className="mx-auto mt-6 max-w-sm space-y-1">
                <ProgressBar pct={progressPct(status.state)} />
              </div>
            )}
            {status?.queue_position != null && status.queue_position > 0 && (
              <p className="mt-3 text-xs text-stone-400">
                In queue (workers busy) · Position {status.queue_position}
                {status.estimated_wait_seconds != null && ` · Est. wait ${Math.round(status.estimated_wait_seconds)}s`}
              </p>
            )}
          </>
        )}

        {failed && (
          <ErrorState
            title="Analysis failed"
            message={status?.error_summary ?? "The job could not be completed."}
            hint="You can fix column mapping on the existing upload, or start over with a new file."
          />
        )}

        {error && !failed && <p className="mt-4 text-xs text-rose-500">{error}</p>}

        {failed && jobId && (
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
        )}
      </div>
    </div>
  );
}
