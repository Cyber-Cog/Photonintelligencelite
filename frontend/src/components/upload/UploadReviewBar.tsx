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
  const arch = review.architecture_summary;
  const impact = review.module_impact_preview;
  const blocked = impact?.blocked_count ?? 0;
  const mayRun = impact?.may_run_count ?? 0;

  const summaryParts = [
    `${fileCount} file${fileCount === 1 ? "" : "s"}`,
    `${rows.toLocaleString()} rows`,
  ];
  if (review.looks_like_complete_pack) {
    summaryParts.push("Complete Analysis Pack");
  }
  if (arch?.detected) {
    summaryParts.push(`${arch.inverter_count} inv · ${arch.scb_count} SCB`);
  }

  const status =
    blocked > 0
      ? `${blocked} analysis module${blocked === 1 ? "" : "s"} may not run — review impact panel, then continue to Setup`
      : mayRun > 0
        ? `${mayRun} module${mayRun === 1 ? "" : "s"} may run after Validate confirms levels — continue to Setup`
        : arch?.detected
          ? "Signals and architecture detected — continue to Setup"
          : "Continue to Setup to confirm mapping and architecture";

  return (
    <div className="workflow-action-bar">
      <div className="workflow-action-bar-inner">
        <div className="workflow-action-bar-row">
          <div className="min-w-0 text-sm">
            <p className="text-[color:var(--pic-text-secondary)]">{summaryParts.join(" · ")}</p>
            <p
              className={`text-xs ${
                blocked > 0 || mayRun > 0
                  ? "text-amber-700 dark:text-amber-400"
                  : "text-[color:var(--pic-text-muted)]"
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
    </div>
  );
}
