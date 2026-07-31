import { EvidenceChartsPanel } from "@/components/EvidenceChartsPanel";
import { PlotlyChart } from "@/components/PlotlyChart";
import { AppModal } from "@/components/ui/AppModal";
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

  return (
    <AppModal
      titleId="investigate-title"
      eyebrow="Investigate evidence"
      title={faultType}
      description={
        <>
          {equipment}
          {severity ? (
            <>
              {" · "}
              <Badge tone={SEVERITY_TONE[severity] ?? "neutral"}>{severity}</Badge>
            </>
          ) : null}
          {" · "}
          <span className="font-semibold text-rose-600 dark:text-rose-400">{fmtKwh(lossKwh)}</span>
          <span className="mt-1 block text-xs text-stone-500">Fault window: {timeWindow}</span>
        </>
      }
      onClose={onClose}
    >
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
    </AppModal>
  );
}
