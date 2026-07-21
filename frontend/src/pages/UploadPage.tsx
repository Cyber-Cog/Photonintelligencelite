import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ApiError,
  completeAnalysisTemplateUrl,
  completeAnalysisZipUrl,
  downloadAuthenticated,
  replaceUploadFiles,
  uploadFiles,
} from "@/api/client";
import { StepIndicator } from "@/components/StepIndicator";
import { InfoBanner } from "@/components/ui/InfoBanner";
import { PageHeader } from "@/components/ui/PageHeader";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { SectionPanel } from "@/components/ui/SectionPanel";
import { Spinner } from "@/components/ui/Spinner";
import { useJob } from "@/context/JobContext";
import { maybeCompress } from "@/lib/clientGzip";
import { rememberUploadPath } from "@/lib/uploadPath";

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
  const inputRef = useRef<HTMLInputElement>(null);

  const [path, setPath] = useState<UploadPath | null>(null);
  const [showDropzone, setShowDropzone] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [dlError, setDlError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<"excel" | "zip" | null>(null);

  useEffect(() => {
    if (!replaceJobId) return;
    setPath((prev) => prev ?? "own");
    setShowDropzone(true);
  }, [replaceJobId]);

  const choosePath = (next: UploadPath) => {
    setPath(next);
    setShowDropzone(Boolean(replaceJobId));
    setSelectedFiles([]);
    setError(null);
    setDlError(null);
    setProgress(0);
  };

  const switchPath = () => {
    setPath(null);
    setShowDropzone(Boolean(replaceJobId));
    setSelectedFiles([]);
    setError(null);
    setDlError(null);
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

  const handleUpload = async () => {
    if (selectedFiles.length === 0 || uploading || !path) return;
    setUploading(true);
    setError(null);
    setProgress(0);
    try {
      const prepared = await Promise.all(selectedFiles.map((f) => maybeCompress(f)));
      const res = replaceJobId
        ? await replaceUploadFiles(replaceJobId, prepared, setProgress)
        : await uploadFiles(prepared, setProgress);
      rememberUploadPath(res.job_id, path);
      setJob(res.job_id, res);
      navigate(`/jobs/${res.job_id}/setup`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed. Check your connection and try again.");
      setUploading(false);
    }
  };

  const totalMb = selectedFiles.reduce((s, f) => s + f.size, 0) / (1024 * 1024);

  const dropzone = (
    <SectionPanel
      title={
        replaceJobId
          ? "Replace SCADA files"
          : path === "template"
            ? "Upload filled template"
            : "Upload SCADA files"
      }
      description={
        replaceJobId
          ? "Plant details are kept. Columns that still match by name keep their prior mapping; new columns appear in Setup."
          : path === "template"
            ? "Prefer the Complete Analysis Pack for full coverage — if you upload a different format, Setup will detect it and let you map columns."
            : "Any CSV/XLSX export. Column mapping happens in Setup."
      }
      scrollMargin={false}
    >
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={onDrop}
        className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed px-4 py-12 text-center transition-all duration-200 ${
          dragActive
            ? "border-brand-500 bg-brand-50/50 dark:bg-brand-900/15"
            : "border-stone-300 bg-stone-50/40 hover:border-brand-400 hover:bg-brand-50/30 dark:border-stone-600 dark:bg-stone-950/30 dark:hover:border-brand-500"
        }`}
      >
        <p className="text-sm font-medium text-stone-700 dark:text-stone-200">
          Drag and drop files, or click to browse
        </p>
        <p className="text-xs text-stone-400">.csv · .xlsx · multiple files accepted</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".csv,.gz,.xlsx,.xlsm,.xls"
          className="hidden"
          onChange={(e) => e.target.files && addFiles(e.target.files)}
        />
      </div>

      {selectedFiles.length > 0 && (
        <ul className="mt-4 divide-y divide-stone-200 overflow-hidden rounded-lg border border-stone-200 dark:divide-stone-800 dark:border-stone-800">
          {selectedFiles.map((f, i) => (
            <li key={`${f.name}-${i}`} className="flex items-center justify-between gap-3 px-3 py-2.5 text-sm">
              <span className="truncate font-medium text-stone-700 dark:text-stone-200">{f.name}</span>
              <div className="flex shrink-0 items-center gap-2">
                <span className="text-xs text-stone-400">{(f.size / (1024 * 1024)).toFixed(2)} MB</span>
                <button
                  type="button"
                  className="text-xs font-semibold text-rose-600 hover:underline"
                  onClick={() => setSelectedFiles((prev) => prev.filter((_, j) => j !== i))}
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {selectedFiles.length > 0 && (
        <p className="mt-2 text-xs text-stone-400">
          {selectedFiles.length} file(s) · {totalMb.toFixed(2)} MB total
        </p>
      )}

      {error && <p className="mt-3 text-sm text-rose-600 dark:text-rose-400">{error}</p>}

      {uploading && (
        <div className="mt-3 space-y-1">
          <ProgressBar pct={progress} />
          <p className="text-xs text-stone-400">Uploading and merging… {progress}%</p>
        </div>
      )}
    </SectionPanel>
  );

  return (
    <div className="tool-enter mx-auto w-full max-w-2xl">
      <StepIndicator current={1} jobId={replaceJobId} />
      <PageHeader
        className="mb-4"
        eyebrow={replaceJobId ? "Replace files" : "Start analysis"}
        title={replaceJobId ? "Replace SCADA reports" : "Upload SCADA reports"}
        description={
          replaceJobId
            ? "Upload new files for this job. Setup mapping stays available afterward — prior column maps rematch when headers still match."
            : path
              ? "Files are merged into a single analysis dataset. After upload we detect whether this looks like the Complete Analysis Pack, then Setup mapping is always available."
              : "Choose how you will provide plant data. The template path is recommended — not required. Sign-in is required for templates and uploads."
        }
        actions={
          replaceJobId ? (
            <Link to={`/jobs/${replaceJobId}/setup`} className="btn-ghost text-xs">
              Back to Setup
            </Link>
          ) : path ? (
            <button type="button" className="btn-ghost text-xs" onClick={switchPath}>
              Change path
            </button>
          ) : undefined
        }
      />

      {replaceJobId ? (
        <InfoBanner className="mb-4" tone="info" title="Replacing files on this job">
          Plant ratings and architecture are kept. Column mapping is rematched for headers that still exist; new
          columns show up in Setup for you to map.
        </InfoBanner>
      ) : null}

      {!path && !replaceJobId && (
        <div className="grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            onClick={() => choosePath("template")}
            className="group flex flex-col rounded-2xl border border-brand-200/80 bg-gradient-to-br from-brand-50/80 to-white p-4 text-left shadow-sm shadow-stone-900/[0.02] transition hover:border-brand-400 hover:shadow-md dark:border-brand-700/45 dark:bg-stone-900 dark:bg-none dark:shadow-none dark:hover:border-brand-500"
          >
            <span className="font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-brand-700 dark:text-brand-300">
              Recommended
            </span>
            <span className="mt-2 font-display text-base font-semibold tracking-tight text-stone-900 dark:text-stone-50">
              Use the Complete Analysis template
            </span>
            <span className="mt-1.5 text-sm leading-relaxed text-stone-600 dark:text-stone-400">
              Best for full fault coverage. Download the pack, fill required columns, then upload. If you upload a
              different format anyway, we detect it and send you to normal mapping.
            </span>
            <span className="mt-4 text-xs font-semibold text-brand-700 group-hover:underline dark:text-brand-300">
              Continue with template →
            </span>
          </button>

          <button
            type="button"
            onClick={() => choosePath("own")}
            className="group flex flex-col rounded-2xl border border-stone-200/90 bg-stone-50/90 p-4 text-left shadow-sm shadow-stone-900/[0.02] transition hover:border-stone-400 hover:shadow-md dark:border-stone-600 dark:bg-stone-900 dark:shadow-none dark:hover:border-stone-500"
          >
            <span className="font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-stone-500 dark:text-stone-400">
              Alternate
            </span>
            <span className="mt-2 font-display text-base font-semibold tracking-tight text-stone-900 dark:text-stone-50">
              Upload your own SCADA format
            </span>
            <span className="mt-1.5 text-sm leading-relaxed text-stone-600 dark:text-stone-400">
              Any CSV or Excel export. Map columns to PIC Lite fields in Setup.
            </span>
            <span className="mt-4 text-xs font-semibold text-stone-700 group-hover:underline dark:text-stone-300">
              Continue with own files →
            </span>
          </button>
        </div>
      )}

      {path === "template" && (
        <div className="space-y-4">
          <div className="rounded-2xl border border-brand-200/70 bg-gradient-to-br from-brand-50/80 to-white px-4 py-3.5 shadow-sm shadow-stone-900/[0.02] dark:border-brand-700/45 dark:bg-stone-900 dark:bg-none dark:shadow-none">
            <p className="font-display text-sm font-semibold tracking-tight text-stone-900 dark:text-stone-50">
              Complete Analysis Pack
            </p>
            <p className="mt-1 text-sm leading-relaxed text-stone-700 dark:text-stone-300">
              Prefer this path for full fault coverage. Include timestamp, equipment IDs, AC power (kW), DC current
              (A) and voltage (V), and POA/GHI (W/m²). Architecture and inverter ratings are confirmed in Setup.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                className="btn-primary text-xs"
                disabled={downloading !== null}
                onClick={() => void download("excel")}
              >
                {downloading === "excel" ? <Spinner className="h-3.5 w-3.5" /> : null}
                Download Excel template
              </button>
              <button
                type="button"
                className="btn-secondary text-xs"
                disabled={downloading !== null}
                onClick={() => void download("zip")}
              >
                {downloading === "zip" ? <Spinner className="h-3.5 w-3.5" /> : null}
                Download CSV package
              </button>
            </div>
            {dlError ? <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{dlError}</p> : null}
          </div>

          {!showDropzone ? (
            <div className="flex justify-end">
              <button type="button" className="btn-secondary" onClick={() => setShowDropzone(true)}>
                I filled the template — upload files
              </button>
            </div>
          ) : (
            <>
              {dropzone}
              <div className="flex justify-end">
                <button
                  type="button"
                  className="btn-primary"
                  onClick={handleUpload}
                  disabled={selectedFiles.length === 0 || uploading}
                >
                  {uploading ? <Spinner className="h-4 w-4" /> : null}
                  Continue
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {path === "own" && (
        <div className="space-y-4">
          {!replaceJobId ? (
            <div className="rounded-2xl border border-stone-200/90 bg-stone-50/90 px-4 py-3.5 shadow-sm shadow-stone-900/[0.02] dark:border-stone-600 dark:bg-stone-900 dark:shadow-none">
              <p className="font-display text-sm font-semibold tracking-tight text-stone-900 dark:text-stone-50">
                Own SCADA / OEM export
              </p>
              <p className="mt-1 text-sm leading-relaxed text-stone-700 dark:text-stone-300">
                Upload any CSV or Excel plant export. You will map columns to required signals in Setup before
                analysis runs.
              </p>
              {!showDropzone ? (
                <div className="mt-3">
                  <button type="button" className="btn-primary text-xs" onClick={() => setShowDropzone(true)}>
                    Upload my files
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}

          {showDropzone ? (
            <>
              {dropzone}
              <div className="flex justify-end gap-2">
                {replaceJobId ? (
                  <button type="button" className="btn-ghost text-sm" onClick={() => choosePath("template")}>
                    Prefer template instead
                  </button>
                ) : null}
                <button
                  type="button"
                  className="btn-primary"
                  onClick={handleUpload}
                  disabled={selectedFiles.length === 0 || uploading}
                >
                  {uploading ? <Spinner className="h-4 w-4" /> : null}
                  {replaceJobId ? "Replace & continue" : "Continue"}
                </button>
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}
