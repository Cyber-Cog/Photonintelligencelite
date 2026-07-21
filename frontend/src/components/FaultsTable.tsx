import { useMemo, useState } from "react";
import { EvidenceInvestigateModal } from "@/components/EvidenceInvestigateModal";
import { Badge } from "@/components/ui/Badge";
import { SectionPanel } from "@/components/ui/SectionPanel";
import { buildFaultRows, type FaultRow } from "@/lib/faultsTable";
import type { ResultObject } from "@/types";

const SEVERITY_TONE: Record<string, "danger" | "warning" | "info" | "neutral"> = {
  critical: "danger",
  high: "danger",
  medium: "warning",
  low: "info",
  info: "info",
};

function fmtKwh(v: number | null): string {
  if (v == null) return "—";
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function FaultsTable({ results }: { results: ResultObject[] }) {
  const rows = useMemo(() => buildFaultRows(results), [results]);
  const [selected, setSelected] = useState<FaultRow | null>(null);

  if (rows.length === 0) {
    return (
      <SectionPanel
        title="Fault findings"
        description="No confirmed fault findings in this run. Modules with status OK and empty tables are omitted."
        scrollMargin={false}
      >
        <p className="text-xs text-stone-500">No rows to display.</p>
      </SectionPanel>
    );
  }

  return (
    <SectionPanel
      title="Fault findings"
      description={`${rows.length} finding(s). Select a row or Investigate for evidence charts.`}
      scrollMargin={false}
      bodyClassName="p-0"
    >
      <div className="overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>Fault type</th>
              <th>Equipment</th>
              <th>Severity</th>
              <th className="text-right">Loss (kWh)</th>
              <th>Time window</th>
              <th>Status</th>
              <th className="text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.id}
                className={`cursor-pointer hover:bg-amber-50/50 dark:hover:bg-amber-950/20 ${
                  selected?.id === row.id ? "bg-brand-50/60 dark:bg-brand-950/25" : ""
                }`}
                onClick={() => setSelected(row)}
              >
                <td className="font-medium text-stone-800 dark:text-stone-100">{row.faultType}</td>
                <td>{row.equipment}</td>
                <td>
                  {row.severity ? (
                    <Badge tone={SEVERITY_TONE[row.severity] ?? "neutral"}>{row.severity}</Badge>
                  ) : (
                    <span className="text-stone-400">—</span>
                  )}
                </td>
                <td className="text-right font-semibold tabular-nums text-rose-600 dark:text-rose-400">
                  {fmtKwh(row.lossKwh)}
                </td>
                <td className="text-xs text-stone-500">{row.timeWindow}</td>
                <td>
                  <Badge tone="success">{row.status}</Badge>
                </td>
                <td className="text-right">
                  <button
                    type="button"
                    className="btn-secondary text-xs"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelected(row);
                    }}
                  >
                    Investigate
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && <EvidenceInvestigateModal row={selected} onClose={() => setSelected(null)} />}
    </SectionPanel>
  );
}
