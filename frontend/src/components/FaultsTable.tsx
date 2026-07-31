import { useMemo, useState } from "react";
import { EvidenceInvestigateModal } from "@/components/EvidenceInvestigateModal";
import { Badge } from "@/components/ui/Badge";
import { SectionPanel } from "@/components/ui/SectionPanel";
import {
  categoryForAlgorithm,
  type FaultCategoriesResponse,
} from "@/lib/faultCategories";
import { buildFaultRows, type FaultRow } from "@/lib/faultsTable";
import type { ResultObject } from "@/types";

const SEVERITY_TONE: Record<string, "danger" | "warning" | "info" | "neutral"> = {
  critical: "danger",
  high: "danger",
  medium: "warning",
  low: "info",
  info: "info",
};

type FaultTab = "actionable" | "non_actionable";

function fmtKwh(v: number | null): string {
  if (v == null) return "—";
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function FaultRowsTable({
  rows,
  selected,
  onSelect,
}: {
  rows: FaultRow[];
  selected: FaultRow | null;
  onSelect: (row: FaultRow) => void;
}) {
  if (rows.length === 0) {
    return <p className="px-4 py-6 text-xs text-stone-500">No findings in this category.</p>;
  }

  return (
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
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              className={`cursor-pointer hover:bg-amber-50/50 dark:hover:bg-amber-950/20 ${
                selected?.id === row.id ? "bg-brand-50/60 dark:bg-brand-950/25" : ""
              }`}
              onClick={() => onSelect(row)}
              title="Open evidence charts"
            >
              <td className="font-medium text-stone-800 dark:text-stone-100">{row.faultType}</td>
              <td>
                <span className="inline-flex max-w-[14rem] flex-wrap gap-1">
                  {row.equipment.split(", ").map((eq) => (
                    <span
                      key={eq}
                      className="rounded-pic-sm bg-stone-100 px-1.5 py-0.5 text-[10px] font-medium text-stone-700 dark:bg-stone-800 dark:text-stone-200"
                    >
                      {eq}
                    </span>
                  ))}
                </span>
              </td>
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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function FaultsTable({
  results,
  categories,
}: {
  results: ResultObject[];
  categories?: FaultCategoriesResponse | null;
}) {
  const rows = useMemo(() => buildFaultRows(results), [results]);
  const [selected, setSelected] = useState<FaultRow | null>(null);
  const [tab, setTab] = useState<FaultTab>("actionable");

  const actionable = useMemo(
    () => rows.filter((r) => categoryForAlgorithm(r.algorithmId, categories) === "actionable"),
    [rows, categories],
  );
  const nonActionable = useMemo(
    () => rows.filter((r) => categoryForAlgorithm(r.algorithmId, categories) === "non_actionable"),
    [rows, categories],
  );

  const visible = tab === "actionable" ? actionable : nonActionable;

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
      description={`${rows.length} confirmed finding${rows.length === 1 ? "" : "s"}. Click a row for evidence.`}
      scrollMargin={false}
      bodyClassName="p-0"
    >
      <div
        className="flex flex-wrap gap-1 border-b border-[color:var(--pic-border-subtle)] px-3 py-2"
        role="tablist"
        aria-label="Fault category"
      >
        {(
          [
            ["actionable", "Actionable", actionable.length],
            ["non_actionable", "Non-actionable", nonActionable.length],
          ] as const
        ).map(([id, label, count]) => {
          const active = tab === id;
          return (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={active}
              className={`rounded-pic px-2.5 py-1.5 text-xs font-semibold transition ${
                active
                  ? "bg-brand-50 text-stone-900 ring-1 ring-brand-200/80 dark:bg-brand-950/40 dark:text-amber-100 dark:ring-brand-800/50"
                  : "text-[color:var(--pic-text-muted)] hover:bg-stone-100/80 dark:hover:bg-stone-800/60"
              }`}
              onClick={() => setTab(id)}
            >
              {label}
              <span className="ml-1.5 tabular-nums text-[10px] opacity-80">({count})</span>
            </button>
          );
        })}
      </div>

      <FaultRowsTable rows={visible} selected={selected} onSelect={setSelected} />

      {selected && <EvidenceInvestigateModal row={selected} onClose={() => setSelected(null)} />}
    </SectionPanel>
  );
}
