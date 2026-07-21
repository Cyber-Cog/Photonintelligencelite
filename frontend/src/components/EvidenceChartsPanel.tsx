import { PlotlyChart } from "@/components/PlotlyChart";
import type { ChartSpec } from "@/types";

/** Shared evidence chart block — reused by ResultCard and Investigate modal. */
export function EvidenceChartsPanel({
  charts,
  label = "Fault evidence (Investigate)",
}: {
  charts: ChartSpec[];
  label?: string;
}) {
  if (charts.length === 0) return null;
  return (
    <section>
      <p className="label mb-2 text-brand-700 dark:text-brand-300">{label}</p>
      <div className="grid grid-cols-1 gap-4">
        {charts.map((chart) => (
          <PlotlyChart key={chart.chart_id} chart={chart} tall fullWidth />
        ))}
      </div>
    </section>
  );
}
