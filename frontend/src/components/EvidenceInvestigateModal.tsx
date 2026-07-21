import { useEffect } from "react";
import { createPortal } from "react-dom";
import { EvidenceChartsPanel } from "@/components/EvidenceChartsPanel";
import { PlotlyChart } from "@/components/PlotlyChart";
import { Badge } from "@/components/ui/Badge";
import { chartsForFaultRow, type FaultRow } from "@/lib/faultsTable";

const SEVERITY_TONE: Record<string, "danger" | "warning" | "info" | "neutral"> = {
  critical: "danger",
  high: "danger",
  medium: "warning",
  low: "info",
  info: "info",
};

function fmtKwh(v: number | null): string {
  if (v == null) return "—";
  return `${v.toLocaleString(undefined, { maximumFractionDigits: 2 })} kWh`;
}

export function EvidenceInvestigateModal({
  row,
  onClose,
}: {
  row: FaultRow;
  onClose: () => void;
}) {
  const { charts, note } = chartsForFaultRow(row);
  const { result, equipment, faultType, severity, lossKwh, timeWindow } = row;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const dialog = (
    <div
      className="fixed inset-0 z-[100] flex items-end justify-center bg-stone-950/50 p-0 sm:items-center sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="investigate-title"
      onClick={onClose}
    >
      <div
        className="flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-t-2xl border border-stone-200 bg-white shadow-xl dark:border-stone-700 dark:bg-stone-900 sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-stone-100 bg-gradient-to-r from-brand-50/80 to-transparent px-5 py-4 dark:border-stone-800 dark:bg-stone-900 dark:bg-none">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-brand-700 dark:text-brand-300">
              Investigate evidence
            </p>
            <h3 id="investigate-title" className="mt-0.5 font-display text-lg font-bold text-stone-900 dark:text-stone-50">
              {faultType}
            </h3>
            <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">
              {equipment}
              {severity ? (
                <>
                  {" · "}
                  <Badge tone={SEVERITY_TONE[severity] ?? "neutral"}>{severity}</Badge>
                </>
              ) : null}
              {" · "}
              <span className="font-semibold text-rose-600 dark:text-rose-400">{fmtKwh(lossKwh)}</span>
            </p>
            <p className="mt-1 text-xs text-stone-500">Fault window: {timeWindow}</p>
          </div>
          <button type="button" className="btn-ghost shrink-0 text-sm" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="space-y-4 overflow-y-auto p-5">
          {note && (
            <p className="rounded-lg border border-amber-200 bg-amber-50/80 px-3 py-2 text-xs text-amber-950 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-100">
              {note}
            </p>
          )}

          {charts.length > 0 ? (
            <div className="space-y-4">
              {charts.some((c) => c.chart_type === "diagnostic") ? (
                <EvidenceChartsPanel
                  charts={charts.filter((c) => c.chart_type === "diagnostic")}
                  label="Fault evidence (Investigate)"
                />
              ) : null}
              {charts
                .filter((c) => c.chart_type !== "diagnostic")
                .map((chart) => (
                  <PlotlyChart key={chart.chart_id} chart={chart} fullWidth />
                ))}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-stone-200 px-4 py-8 text-center dark:border-stone-700">
              <p className="text-sm text-stone-500">{note ?? "No charts available."}</p>
            </div>
          )}

          <div className="rounded-lg border border-stone-100 bg-stone-50/60 p-3 text-xs text-stone-600 dark:border-stone-800 dark:bg-stone-800/40 dark:text-stone-300">
            <p className="mb-2 text-[10px] font-bold uppercase tracking-wide text-stone-400">Traceability</p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <div>
                <p className="font-semibold text-stone-400">Samples</p>
                <p>
                  {result.evidence.affected_sample_count.toLocaleString()} /{" "}
                  {result.evidence.total_sample_count.toLocaleString()}
                </p>
              </div>
              <div>
                <p className="font-semibold text-stone-400">Signals</p>
                <p>{result.evidence.source_fields.join(", ") || "—"}</p>
              </div>
              <div className="col-span-2">
                <p className="font-semibold text-stone-400">Notes</p>
                <p>{result.evidence.notes || result.summary}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  // Portal to body so fixed positioning is viewport-relative (ancestors use transform / overflow).
  return createPortal(dialog, document.body);
}
