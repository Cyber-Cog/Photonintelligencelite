import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ApiError,
  completeAnalysisTemplateUrl,
  completeAnalysisZipUrl,
  downloadAuthenticated,
  replaceUploadFiles,
  startDemo,
  uploadFiles,
  waitForUploadReady,
} from "@/api/client";
import { DownloadTemplateMenu } from "@/components/DownloadTemplateMenu";
import { StepIndicator } from "@/components/StepIndicator";
import { ParseActivityConsole } from "@/components/upload/ParseActivityConsole";
import { UploadFilesTable } from "@/components/upload/UploadFilesTable";
import { UploadReviewBar } from "@/components/upload/UploadReviewBar";
import { UploadIntelligencePanel } from "@/components/upload/UploadIntelligencePanel";
import {
  useParseActivityLog,
  type UploadActivityPhase,
} from "@/components/upload/useParseActivityLog";
import { InfoBanner } from "@/components/ui/InfoBanner";
import { PageHeader } from "@/components/ui/PageHeader";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Spinner } from "@/components/ui/Spinner";
import { useJob } from "@/context/JobContext";
import { useWorkflowTransition } from "@/context/WorkflowTransitionContext";
import { maybeCompress } from "@/lib/clientGzip";
import { rememberUploadPath } from "@/lib/uploadPath";
import type { UploadResponse } from "@/types";

const ACCEPTED = [".csv", ".csv.gz", ".xlsx", ".xlsm", ".xls"];

type UploadPath = "template" | "own";

function isAcceptedFile(name: string): boolean {
  const lower = name.toLowerCase();
  return ACCEPTED.some((ext) => lower.endsWith(ext));
}

export function UploadPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const replaceJobId = searchParams.get("replace");
  const { setJob } = useJob();
  const { runWithTransition, active: transitioning } = useWorkflowTransition();
  const inputRef = useRef<HTMLInputElement>(null);

  const [path, setPath] = useState<UploadPath | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [review, setReview] = useState<UploadResponse | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [phaseHint, setPhaseHint] = useState<string | null>(null);
  const [activityPhase, setActivityPhase] = useState<UploadActivityPhase | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [dlError, setDlError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<"excel" | "zip" | null>(null);
  const [demoLoading, setDemoLoading] = useState(false);
  const uploadStartedAt = useRef<number | null>(null);

  useEffect(() => {
    if (!replaceJobId) return;
    setPath("own");
  }, [replaceJobId]);

  useEffect(() => {
    if (!uploading) {
      uploadStartedAt.current = null;
      setElapsedSec(0);
      return;
    }
    uploadStartedAt.current = Date.now();
    const id = window.setInterval(() => {
      if (uploadStartedAt.current == null) return;
      setElapsedSec(Math.floor((Date.now() - uploadStartedAt.current) / 1000));
    }, 1000);
    return () => window.clearInterval(id);
  }, [uploading]);

  const fileNames = useMemo(
    () => (review ? review.file_inventory?.map((f) => f.filename) ?? [] : selectedFiles.map((f) => f.name)),
    [review, selectedFiles],
  );
  const activityLines = useParseActivityLog(
    uploading,
    activityPhase,
    phaseHint,
    fileNames,
    progress,
    elapsedSec,
  );

  const choosePath = (next: UploadPath) => {
    setPath(next);
    setSelectedFiles([]);
    setReview(null);
    setError(null);
    setDlError(null);
    setProgress(0);
  };

  const clearReview = () => {
    setReview(null);
    setSelectedFiles([]);
    setError(null);
    setProgress(0);
  };

  const download = async (kind: "excel" | "zip") => {
    setDlError(null);
    setDownloading(kind);
    try {
      if (kind === "excel") {
        await downloadAuthenticated(completeAnalysisTemplateUrl(), "pic_lite_complete_analysis_pack.xlsx");
      } else {
        await downloadAuthenticated(completeAnalysisZipUrl(), "pic_lite_complete_analysis_pack.zip");
      }
    } catch (err) {
      setDlError(err instanceof ApiError ? err.message : "Download failed.");
    } finally {
      setDownloading(null);
    }
  };

  const addFiles = useCallback((incoming: FileList | File[]) => {
    const next: File[] = [];
    for (const f of Array.from(incoming)) {
      if (!isAcceptedFile(f.name)) {
        setError(`Skipped ${f.name}. Accepted formats: CSV, Excel.`);
        continue;
      }
      next.push(f);
    }
    if (next.length) {
      setError(null);
      setSelectedFiles((prev) => [...prev, ...next]);
    }
  }, []);

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
    if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
  };

  const runUpload = async () => {
    if (selectedFiles.length === 0 || uploading || !path) return;
    setUploading(true);
    setError(null);
    setProgress(0);
    setPhaseHint(null);
    setActivityPhase("uploading");
    try {
      const prepared = await Promise.all(selectedFiles.map((f) => maybeCompress(f)));
      let res = replaceJobId
        ? await replaceUploadFiles(replaceJobId, prepared, setProgress)
        : await uploadFiles(prepared, setProgress);
      if (res.state === "parsing" || res.state === "uploaded") {
        setProgress(100);
        setActivityPhase("parsing");
        setPhaseHint("Parsing Excel workbook… wide reports can take up to a minute.");
        res = await waitForUploadReady(res.job_id, {
          onProgress: (msg) => setPhaseHint(msg),
        });
      }
      rememberUploadPath(res.job_id, path);
      setJob(res.job_id, res);
      setReview(res);
      setSelectedFiles([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed. Check your connection and try again.");
    } finally {
      setUploading(false);
      setPhaseHint(null);
      setActivityPhase(null);
    }
  };

  const continueToSetup = async () => {
    if (!review?.job_id) return;
    const jobId = review.job_id;
    try {
      await runWithTransition("to-setup", () => {
        navigate(`/jobs/${jobId}/setup`);
      });
    } catch {
      /* navigation-only; overlay clears in finally */
    }
  };

  const loadDemo = async () => {
    setDemoLoading(true);
    setError(null);
    try {
      await runWithTransition("to-demo", async () => {
        const res = await startDemo();
        setJob(res.job_id, null);
        navigate(`/jobs/${res.job_id}/processing`);
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start demo.");
    } finally {
      setDemoLoading(false);
    }
  };

  const showWorkspace = Boolean(path || replaceJobId);
  const totalMb = selectedFiles.reduce((s, f) => s + f.size, 0) / (1024 * 1024);

  const dropzone = (
    <div
      role="button"
      tabIndex={0}
      onClick={() => !review && inputRef.current?.click()}
      onKeyDown={(e) => e.key === "Enter" && !review && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        if (!review) setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={(e) => {
        if (review) return;
        onDrop(e);
      }}
      className={`flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed px-4 py-10 text-center transition-all duration-200 ${
        review
          ? "cursor-default border-[color:var(--pic-border-subtle)] bg-[color:var(--pic-surface-muted)] opacity-80"
          : dragActive
            ? "cursor-pointer border-brand-500 bg-brand-50/50 dark:bg-brand-900/15"
            : "cursor-pointer border-[color:var(--pic-border)] bg-[color:var(--pic-surface-muted)] hover:border-brand-400 hover:bg-brand-50/30 dark:hover:border-brand-500"
      }`}
    >
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-100 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <path d="M12 16V4m0 0L8 8m4-4 4 4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <div>
        <p className="text-sm font-medium text-[color:var(--pic-text)]">
          {review ? "Files uploaded — review below or continue to Setup" : "Drop CSV or Excel files here"}
        </p>
        <p className="mt-1 text-xs text-[color:var(--pic-text-muted)]">
          {review ? "Use Clear all to upload a different set" : "or browse from your machine · multi-file supported"}
        </p>
      </div>
      {!review ? (
        <div className="flex flex-wrap justify-center gap-2">
          {[".csv", ".xlsx", ".xls"].map((ext) => (
            <span
              key={ext}
              className="rounded-md border border-[color:var(--pic-border-subtle)] bg-[color:var(--pic-surface-raised)] px-2 py-0.5 text-[10px] font-medium text-[color:var(--pic-text-muted)]"
            >
              {ext}
            </span>
          ))}
        </div>
      ) : null}
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".csv,.gz,.xlsx,.xlsm,.xls"
        className="hidden"
        onChange={(e) => e.target.files && addFiles(e.target.files)}
      />
    </div>
  );

  return (
    <div className={`tool-enter flow-shell w-full ${review ? "pb-[calc(5.5rem+env(safe-area-inset-bottom))]" : "flow-stack"}`}>
      <StepIndicator current={1} jobId={replaceJobId ?? review?.job_id} />

      <PageHeader
        eyebrow={replaceJobId ? "Replace files" : "Start analysis"}
        title={replaceJobId ? "Replace SCADA reports" : "Upload SCADA reports"}
        description={
          review
            ? "Check which signals were found in each file. Anything missing can be mapped in Setup."
            : "Upload one or more plant exports. We detect columns per file before you confirm mapping."
        }
        actions={
          showWorkspace ? (
            <div className="flex flex-wrap items-center gap-2">
              {!replaceJobId ? (
                <button type="button" className="btn-ghost text-xs" disabled={demoLoading} onClick={() => void loadDemo()}>
                  {demoLoading ? <Spinner className="h-3.5 w-3.5" /> : null}
                  Load demo dataset
                </button>
              ) : (
                <Link to={`/jobs/${replaceJobId}/setup`} className="btn-ghost text-xs">
                  Back to Setup
                </Link>
              )}
              {!review ? (
                <button type="button" className="btn-secondary text-xs" onClick={() => inputRef.current?.click()}>
                  Browse files
                </button>
              ) : null}
              {path === "template" && !review ? (
                <DownloadTemplateMenu
                  buttonClassName="btn-ghost text-xs"
                  disabled={downloading !== null}
                  downloading={downloading}
                  onSelect={(kind) => void download(kind)}
                  align="right"
                />
              ) : null}
              {!replaceJobId && path ? (
                <button type="button" className="btn-ghost text-xs" onClick={() => choosePath(path === "template" ? "own" : "template")}>
                  {path === "template" ? "Use own format" : "Use template"}
                </button>
              ) : null}
            </div>
          ) : undefined
        }
      />

      {replaceJobId ? (
        <InfoBanner tone="info" title="Replacing files on this job">
          Plant ratings and architecture are kept. New columns appear in Setup for mapping. If this job&apos;s
          old files were removed after retention, uploading here starts fresh SCADA on the same job.
        </InfoBanner>
      ) : null}

      {!showWorkspace && (
        <div className="grid gap-4 sm:grid-cols-2">
          <button
            type="button"
            onClick={() => choosePath("template")}
            className="group flex flex-col rounded-pic-xl border border-brand-200/80 bg-gradient-to-br from-brand-50/90 to-[color:var(--pic-surface-raised)] p-5 text-left shadow-pic transition hover:border-brand-400 dark:border-brand-700/45 dark:from-brand-950/30"
          >
            <span className="font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-brand-700 dark:text-brand-300">
              Recommended
            </span>
            <span className="mt-2 font-display text-base font-semibold tracking-tight">Complete Analysis Pack</span>
            <span className="mt-2 text-sm leading-relaxed text-[color:var(--pic-text-muted)]">
              Download the template, fill SCADA + architecture sheets, then upload for automatic detection.
            </span>
          </button>
          <button
            type="button"
            onClick={() => choosePath("own")}
            className="group flex flex-col rounded-pic-xl border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-muted)] p-5 text-left shadow-pic transition hover:border-[color:var(--pic-border-strong)]"
          >
            <span className="font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-[color:var(--pic-text-muted)]">
              Alternate
            </span>
            <span className="mt-2 font-display text-base font-semibold tracking-tight">Your SCADA / OEM export</span>
            <span className="mt-2 text-sm leading-relaxed text-[color:var(--pic-text-muted)]">
              CSV or Excel from any inverter, SMB, or multi-file plant export.
            </span>
          </button>
        </div>
      )}

      {showWorkspace && (
        <>
          {!review ? (
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(280px,340px)] xl:items-start">
              <div className="space-y-4">
                {path === "template" ? (
                  <div className="rounded-xl border border-brand-200/70 bg-brand-50/50 px-4 py-3 dark:border-brand-700/45 dark:bg-brand-950/20">
                    <p className="text-sm text-[color:var(--pic-text-secondary)]">
                      Prefer the Complete Analysis Pack for full fault coverage. Download, fill, then upload below.
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <DownloadTemplateMenu
                        buttonClassName="btn-secondary text-xs"
                        disabled={downloading !== null}
                        downloading={downloading}
                        onSelect={(kind) => void download(kind)}
                      />
                    </div>
                    {dlError ? <p className="mt-2 text-sm text-rose-600">{dlError}</p> : null}
                  </div>
                ) : null}

                {dropzone}

                {selectedFiles.length > 0 && (
                  <ul className="divide-y divide-[color:var(--pic-border-subtle)] overflow-hidden rounded-lg border border-[color:var(--pic-border)]">
                    {selectedFiles.map((f, i) => (
                      <li key={`${f.name}-${i}`} className="flex items-center justify-between gap-3 bg-[color:var(--pic-surface-raised)] px-3 py-2.5 text-sm">
                        <span className="truncate font-medium">{f.name}</span>
                        <button
                          type="button"
                          className="text-xs font-semibold text-rose-600 hover:underline"
                          onClick={() => setSelectedFiles((prev) => prev.filter((_, j) => j !== i))}
                        >
                          Remove
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                {selectedFiles.length > 0 && (
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <p className="text-xs text-[color:var(--pic-text-muted)]">
                      {selectedFiles.length} file(s) · {totalMb.toFixed(2)} MB
                    </p>
                    <button type="button" className="btn-primary text-sm" onClick={() => void runUpload()} disabled={uploading}>
                      {uploading ? <Spinner className="h-4 w-4" /> : null}
                      Upload &amp; review
                    </button>
                  </div>
                )}

                {uploading && (
                  <div className="space-y-1">
                    <ProgressBar pct={progress} />
                    <p className="text-xs text-[color:var(--pic-text-muted)]">
                      {phaseHint ?? `Uploading… ${progress}%`}
                      {elapsedSec > 0 ? <span className="ml-1.5 tabular-nums">· {elapsedSec}s</span> : null}
                    </p>
                    {activityPhase ? <ParseActivityConsole lines={activityLines} phase={activityPhase} live /> : null}
                  </div>
                )}

                {error ? <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p> : null}
              </div>

              <UploadIntelligencePanel hierarchy={[]} showPlaceholder />
            </div>
          ) : (
            <div className="space-y-6">
              {error ? <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p> : null}
              {review.file_inventory && review.file_inventory.length > 0 ? (
                <UploadFilesTable files={review.file_inventory} totalRows={review.total_rows ?? 0} />
              ) : null}
              <UploadIntelligencePanel
                hierarchy={review.hierarchy_overview ?? []}
                architecture={review.architecture_summary}
                moduleImpact={review.module_impact_preview}
                layout="review"
              />
            </div>
          )}
        </>
      )}

      {review ? (
        <UploadReviewBar
          review={review}
          onClear={clearReview}
          onContinue={() => void continueToSetup()}
          continuing={transitioning}
        />
      ) : null}
    </div>
  );
}
