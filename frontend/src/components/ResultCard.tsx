import { memo, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { EvidenceInvestigateModal } from "@/components/EvidenceInvestigateModal";
import { Badge } from "@/components/ui/Badge";
import { buildFaultRows, type FaultRow } from "@/lib/faultsTable";
import { fixHref, setupFixForAlgorithm } from "@/lib/missingReasons";
import type { ResultObject } from "@/types";

export { EvidenceChartsPanel } from "@/components/EvidenceChartsPanel";

const SEVERITY_TONE: Record<string, "danger" | "warning" | "info" | "neutral"> = {
  critical: "danger",
  high: "danger",
  medium: "warning",
  low: "info",
  info: "info",
};

function timeWindowLabel(result: ResultObject): string {
  const { time_range_start: start, time_range_end: end } = result.evidence;
  if (start && end) return `${start.slice(0, 16)} → ${end.slice(0, 16)}`;
  if (start) return start.slice(0, 16);
  return "—";
}

/** Synthetic row when a module has charts but no findings table. */
function investigateRowForResult(result: ResultObject, existing: FaultRow[]): FaultRow {
  if (existing.length > 0) return existing[0];
  return {
    id: `${result.algorithm_id}-investigate`,
    faultType: result.title,
    algorithmId: result.algorithm_id,
    equipment: result.affected_equipment[0] ?? "—",
    severity: result.severity,
    lossKwh: result.loss_energy_kwh,
    timeWindow: timeWindowLabel(result),
    status: "Confirmed",
    result,
    tableIndex: -1,
    rowIndex: -1,
  };
}

function EvidenceMeta({ result }: { result: ResultObject }) {
  const { evidence } = result;
  return (
    <div className="grid grid-cols-2 gap-2 text-xs text-stone-500 sm:grid-cols-4">
      <div>
        <p className="font-semibold text-stone-400">Equipment</p>
        <p className="text-stone-700 dark:text-stone-300">
          {evidence.equipment_ids.length
            ? `${evidence.equipment_ids.slice(0, 5).join(", ")}${evidence.equipment_ids.length > 5 ? "…" : ""}`
            : "—"}
        </p>
      </div>
      <div>
        <p className="font-semibold text-stone-400">Fault window</p>
        <p className="text-stone-700 dark:text-stone-300">
          {evidence.time_range_start
            ? `${evidence.time_range_start.slice(0, 16)} → ${evidence.time_range_end?.slice(0, 16)}`
            : "—"}
        </p>
      </div>
      <div>
        <p className="font-semibold text-stone-400">Fault samples</p>
        <p className="text-stone-700 dark:text-stone-300">
          {evidence.affected_sample_count.toLocaleString()} / {evidence.total_sample_count.toLocaleString()}
        </p>
      </div>
      <div>
        <p className="font-semibold text-stone-400">Signals used</p>
        <p className="text-stone-700 dark:text-stone-300">{evidence.source_fields.join(", ") || "—"}</p>
      </div>
      {evidence.notes && (
        <div className="col-span-full rounded-md bg-amber-50/80 p-2 text-stone-600 dark:bg-amber-950/20 dark:text-stone-300">
          {evidence.notes}
        </div>
      )}
    </div>
  );
}

function ResultCardInner({
  result,
  defaultCollapsed = true,
  /** Always-open full card for the Diagnostics single-module pane. */
  standalone = false,
}: {
  result: ResultObject;
  defaultCollapsed?: boolean;
  standalone?: boolean;
}) {
  const { jobId } = useParams<{ jobId: string }>();
  const [expanded, setExpanded] = useState(standalone || !defaultCollapsed);
  const [investigateRow, setInvestigateRow] = useState<FaultRow | null>(null);

  const faultRows = useMemo(() => buildFaultRows([result]), [result]);
  const faultRowsByKey = useMemo(() => {
    const map = new Map<string, FaultRow>();
    for (const row of faultRows) {
      map.set(`${row.tableIndex}:${row.rowIndex}`, row);
    }
    return map;
  }, [faultRows]);

  if (result.status === "unavailable") {
    const fix = setupFixForAlgorithm(result.algorithm_id);
    const href = jobId ? fixHref(jobId, fix) : "/upload";
    return (
      <Link
        to={href}
        className={`block rounded-xl border border-amber-200/80 bg-amber-50/40 transition hover:border-amber-300 hover:bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/20 dark:hover:bg-amber-950/35 ${
          standalone ? "p-5" : "p-3"
        }`}
        data-tour={standalone ? "diagnostics-module" : undefined}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className={`font-medium text-stone-800 dark:text-stone-100 ${standalone ? "font-display text-base" : "text-sm"}`}>
              {result.title}
            </p>
            <p className="mt-1 text-xs leading-relaxed text-stone-600 dark:text-stone-400">{result.summary}</p>
            <p className="mt-1.5 text-[11px] font-semibold text-amber-800 dark:text-amber-200">
              Fix in Setup — then re-run to unlock this check
            </p>
          </div>
          <Badge tone="warning">Needs input</Badge>
        </div>
      </Link>
    );
  }

  if (result.status === "error") {
    return (
      <div
        className={`flex items-center justify-between rounded-xl border border-rose-200 dark:border-rose-900/60 ${
          standalone ? "p-5" : "p-3"
        }`}
        data-tour={standalone ? "diagnostics-module" : undefined}
      >
        <div>
          <p className={`font-medium text-rose-700 dark:text-rose-300 ${standalone ? "font-display text-base" : "text-sm"}`}>
            {result.title}
          </p>
          <p className="text-xs text-rose-500">{result.summary}</p>
        </div>
        <Badge tone="danger">Module error</Badge>
      </div>
    );
  }

  const evidenceCharts = result.evidence_charts ?? [];
  const summaryCharts = result.charts.filter((c) => c.chart_type !== "timeline");
  const chartCount = evidenceCharts.length + summaryCharts.length;
  const hasTables = result.tables.length > 0;
  const hasMetrics = Object.keys(result.metrics).length > 0;
  const canInvestigate = chartCount > 0 || faultRows.length > 0;

  const showBody = standalone || expanded;

  const openInvestigate = (row?: FaultRow | null) => {
    setInvestigateRow(row ?? investigateRowForResult(result, faultRows));
  };

  const headerInner = (
    <>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3
            className={`font-display font-semibold text-stone-900 dark:text-stone-50 ${
              standalone ? "text-base sm:text-lg" : "text-sm"
            }`}
          >
            {result.title}
          </h3>
          {result.severity && <Badge tone={SEVERITY_TONE[result.severity] ?? "neutral"}>{result.severity}</Badge>}
          {standalone && <Badge tone="info">Ready</Badge>}
        </div>
        <p
          className={`mt-0.5 text-stone-500 dark:text-stone-400 ${
            standalone ? "text-sm leading-relaxed" : "line-clamp-2 text-xs"
          }`}
        >
          {result.summary}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2 sm:gap-3">
        {result.loss_energy_kwh != null && (
          <p
            className={`text-right font-bold tabular-nums text-rose-600 dark:text-rose-400 ${
              standalone ? "text-base" : "text-sm"
            }`}
          >
            {result.loss_energy_kwh.toLocaleString(undefined, { maximumFractionDigits: 1 })}{" "}
            <span className="text-xs font-normal">kWh</span>
          </p>
        )}
        {standalone && canInvestigate && (
          <button
            type="button"
            className="btn-secondary text-xs"
            onClick={() => openInvestigate()}
            data-tour="diagnostics-investigate"
          >
            Investigate
          </button>
        )}
        {!standalone && (
          <span className="text-stone-400" aria-hidden>
            {expanded ? "▾" : "▸"}
          </span>
        )}
      </div>
    </>
  );

  return (
    <div
      className={`overflow-hidden border border-stone-200/90 bg-white/95 dark:border-stone-700 dark:bg-stone-900 ${
        standalone
          ? "rounded-2xl shadow-sm shadow-stone-900/[0.03] dark:shadow-none"
          : "rounded-xl shadow-sm shadow-stone-900/[0.02] dark:border-stone-800 dark:bg-stone-900/50 dark:shadow-none"
      }`}
      data-tour={standalone ? "diagnostics-module" : undefined}
    >
      {standalone ? (
        <div className="flex w-full items-start justify-between gap-3 px-4 py-4 text-left sm:px-5">
          {headerInner}
        </div>
      ) : (
        <button
          type="button"
          className="flex w-full items-start justify-between gap-3 px-3.5 py-3 text-left transition hover:bg-brand-50/30 dark:hover:bg-stone-800/40"
          onClick={() => setExpanded((e) => !e)}
          aria-expanded={expanded}
        >
          {headerInner}
        </button>
      )}

      {showBody && (
        <div
          className={`border-t border-stone-100 dark:border-stone-800 ${
            standalone ? "space-y-4 px-4 py-4 sm:px-5 sm:py-5" : "space-y-3 px-3.5 py-3"
          }`}
        >
          {hasMetrics && (
            <div className="flex flex-wrap gap-3">
              {Object.entries(result.metrics).map(([key, val]) => (
                <div
                  key={key}
                  className="rounded-lg border border-stone-100 bg-stone-50/70 px-2.5 py-1.5 dark:border-stone-800 dark:bg-stone-800/40"
                >
                  <p className="text-[10px] uppercase tracking-wide text-stone-400">{key.replace(/_/g, " ")}</p>
                  <p className="text-sm font-semibold tabular-nums text-stone-800 dark:text-stone-100">
                    {typeof val === "number" ? val.toLocaleString(undefined, { maximumFractionDigits: 2 }) : val}
                  </p>
                </div>
              ))}
            </div>
          )}

          {/* Charts stay in Investigate modal — never dump evidence_charts on the card. */}
          {chartCount > 0 && !hasTables && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-dashed border-brand-200/80 bg-brand-50/40 px-3 py-2.5 dark:border-brand-800/50 dark:bg-brand-950/20">
              <p className="text-xs text-stone-600 dark:text-stone-300">
                {chartCount} evidence chart{chartCount === 1 ? "" : "s"} available
                {standalone ? " — use Investigate above." : "."}
              </p>
              {/* Standalone already has Investigate in the header — avoid a second CTA. */}
              {!standalone && (
                <button type="button" className="btn-secondary text-xs" onClick={() => openInvestigate()}>
                  Investigate
                </button>
              )}
            </div>
          )}

          {chartCount > 0 && hasTables && (
            <p className="text-[11px] text-stone-500 dark:text-stone-400">
              Evidence charts open from Investigate on a finding row — not listed inline to keep this view scalable.
            </p>
          )}

          {hasTables &&
            result.tables.map((table, i) => (
              <div key={i} className="overflow-x-auto rounded-lg border border-stone-100 dark:border-stone-800">
                <p className="bg-stone-50 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-stone-500 dark:bg-stone-800/50">
                  {table.title}
                </p>
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-stone-200 text-xs uppercase text-stone-400 dark:border-stone-700">
                      {table.columns.map((c) => (
                        <th key={c} className="px-3 py-1.5 font-medium">
                          {c}
                        </th>
                      ))}
                      <th className="px-3 py-1.5 text-right font-medium">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {table.rows.map((row, r) => {
                      const faultRow = faultRowsByKey.get(`${i}:${r}`) ?? null;
                      return (
                        <tr
                          key={r}
                          className={`border-b border-stone-50 last:border-0 dark:border-stone-900 ${
                            faultRow ? "cursor-pointer hover:bg-amber-50/50 dark:hover:bg-amber-950/20" : ""
                          } ${
                            investigateRow && faultRow && investigateRow.id === faultRow.id
                              ? "bg-brand-50/60 dark:bg-brand-950/25"
                              : ""
                          }`}
                          onClick={() => faultRow && openInvestigate(faultRow)}
                        >
                          {row.map((cell, c) => (
                            <td key={c} className="px-3 py-1.5 text-stone-700 dark:text-stone-300">
                              {String(cell)}
                            </td>
                          ))}
                          <td className="px-3 py-1.5 text-right">
                            {faultRow && (
                              <button
                                type="button"
                                className="btn-secondary text-xs"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openInvestigate(faultRow);
                                }}
                              >
                                Investigate
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ))}

          {investigateRow && (
            <EvidenceInvestigateModal row={investigateRow} onClose={() => setInvestigateRow(null)} />
          )}

          {result.recommendations.length > 0 && (
            <div className="rounded-md border border-amber-200/70 bg-amber-50/50 p-2.5 text-sm text-amber-950 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-100">
              <p className="mb-1 text-[10px] font-bold uppercase tracking-wide">What to do next</p>
              <ul className="list-inside list-disc space-y-0.5 text-xs">
                {result.recommendations.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}

          <details className="text-xs text-stone-500">
            <summary className="cursor-pointer font-semibold text-stone-400">Traceability & thresholds</summary>
            <div className="mt-2 border-t border-stone-100 pt-2 dark:border-stone-800">
              <EvidenceMeta result={result} />
              {Object.keys(result.thresholds_used).length > 0 && (
                <p className="mt-2 text-xs text-stone-500">
                  <span className="font-semibold text-stone-400">Thresholds: </span>
                  {Object.entries(result.thresholds_used)
                    .map(([k, v]) => `${k.replace(/_/g, " ")}=${v}`)
                    .join(" · ")}
                </p>
              )}
              <p className="mt-2 text-xs text-stone-400">
                <Link to={`/docs#${result.algorithm_id}`} className="text-amber-700 hover:underline dark:text-amber-300">
                  Algorithm documentation
                </Link>
                {" · "}v{result.algorithm_version} · {result.execution_time_ms.toFixed(0)} ms
              </p>
            </div>
          </details>
        </div>
      )}
    </div>
  );
}

export const ResultCard = memo(ResultCardInner);
