import type { UploadResponse } from "@/types";

type Props = {
  review: UploadResponse;
  onClear: () => void;
  onContinue: () => void;
  continuing?: boolean;
};

export function UploadReviewBar({ review, onClear, onContinue, continuing }: Props) {
  const fileCount = review.file_inventory?.length ?? 0;
  const rows = review.total_rows ?? 0;
  const missing = (review.signal_checklist ?? []).filter((c) => !c.present && !c.setup_only);
  const setupOnly = (review.signal_checklist ?? []).filter((c) => !c.present && c.setup_only);

  const summaryParts = [
    `${fileCount} file${fileCount === 1 ? "" : "s"}`,
    `${rows.toLocaleString()} rows`,
  ];
  if (review.looks_like_complete_pack) {
    summaryParts.push("Complete Analysis Pack detected");
  }

  const status =
    missing.length > 0
      ? `${missing.length} signal${missing.length === 1 ? "" : "s"} missing — map in Setup`
      : setupOnly.length > 0
        ? `${setupOnly.length} item${setupOnly.length === 1 ? "" : "s"} to confirm in Setup`
        : "Ready for Setup";

  return (
    <div className="sticky bottom-0 z-20 -mx-4 border-t border-[color:var(--pic-border)] bg-[color:var(--pic-surface-chrome)] px-4 py-3 backdrop-blur-md sm:-mx-6 sm:px-6">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 text-sm">
          <p className="truncate text-[color:var(--pic-text-secondary)]">{summaryParts.join(" · ")}</p>
          <p
            className={`text-xs ${
              missing.length > 0 ? "text-amber-700 dark:text-amber-400" : "text-[color:var(--pic-text-muted)]"
            }`}
          >
            {status}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button type="button" className="btn-ghost text-sm" onClick={onClear} disabled={continuing}>
            Clear all
          </button>
          <button type="button" className="btn-primary text-sm" onClick={onContinue} disabled={continuing}>
            {continuing ? "Opening Setup…" : "Continue to Setup →"}
          </button>
        </div>
      </div>
    </div>
  );
}
