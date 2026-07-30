import { useMemo, useState } from "react";
import { PlotlyChart } from "@/components/PlotlyChart";
import { Badge } from "@/components/ui/Badge";
import type { ChartSpec, ResultObject } from "@/types";

function inverterNamesFromResult(result: ResultObject): string[] {
  const fromEvidence = result.evidence.equipment_ids?.filter(Boolean) ?? [];
  if (fromEvidence.length) return [...new Set(fromEvidence.map(String))];
  const table = result.tables[0];
  if (!table) return [];
  const invCol = table.columns.findIndex((c) => c.toLowerCase() === "inverter");
  if (invCol < 0) return [];
  return [
    ...new Set(
      table.rows
        .map((row) => (invCol < row.length && row[invCol] != null ? String(row[invCol]) : ""))
        .filter(Boolean),
    ),
  ];
}

/** Filter a categorical box chart to the selected inverter names (all shown by default). */
function filterBoxChart(chart: ChartSpec, visible: Set<string>): ChartSpec {
  if (visible.size === 0) {
    return {
      ...chart,
      figure: {
        ...chart.figure,
        data: [],
        layout: { ...chart.figure.layout, title: `${chart.title} (no inverters selected)` },
      },
    };
  }

  const data = (chart.figure.data ?? []).map((raw) => {
    const t = raw as {
      type?: string;
      x?: unknown[];
      y?: unknown[];
      q1?: number[];
      median?: number[];
      q3?: number[];
      lowerfence?: number[];
      upperfence?: number[];
      [key: string]: unknown;
    };
    if (!t.x?.length) return raw;

    // Sample-based box: parallel x/y arrays
    if (Array.isArray(t.y) && t.y.length === t.x.length) {
      const x: unknown[] = [];
      const y: unknown[] = [];
      for (let i = 0; i < t.x.length; i++) {
        const name = String(t.x[i]);
        if (!visible.has(name)) continue;
        x.push(t.x[i]);
        y.push(t.y[i]);
      }
      return { ...t, x, y };
    }

    // Precomputed quartiles: one value per category in x
    const keepIdx: number[] = [];
    t.x.forEach((v, i) => {
      if (visible.has(String(v))) keepIdx.push(i);
    });
    const pick = <T,>(arr: T[] | undefined): T[] | undefined =>
      arr ? keepIdx.map((i) => arr[i]) : arr;
    return {
      ...t,
      x: keepIdx.map((i) => t.x![i]),
      q1: pick(t.q1),
      median: pick(t.median),
      q3: pick(t.q3),
      lowerfence: pick(t.lowerfence),
      upperfence: pick(t.upperfence),
    };
  });

  const names = [...visible];
  const layout = {
    ...chart.figure.layout,
    xaxis: {
      ...((chart.figure.layout?.xaxis as object) || {}),
      categoryorder: "array",
      categoryarray: names,
    },
  };

  return { ...chart, figure: { ...chart.figure, data, layout } };
}

/**
 * Dedicated Box Plot analysis experience: all inverters on one chart, with
 * per-inverter visibility toggles. Not framed as a fault.
 */
export function BoxPlotAnalysisPanel({ result }: { result: ResultObject }) {
  const allNames = useMemo(() => inverterNamesFromResult(result), [result]);
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());

  const visible = useMemo(() => {
    const set = new Set(allNames.filter((n) => !hidden.has(n)));
    return set;
  }, [allNames, hidden]);

  const chart = result.charts.find((c) => c.chart_type === "box") ?? result.charts[0] ?? null;
  const filteredChart = useMemo(
    () => (chart ? filterBoxChart(chart, visible) : null),
    [chart, visible],
  );

  const statsTable = result.tables[0];
  const filteredRows = useMemo(() => {
    if (!statsTable) return [];
    const invCol = statsTable.columns.findIndex((c) => c.toLowerCase() === "inverter");
    if (invCol < 0) return statsTable.rows;
    return statsTable.rows.filter((row) => visible.has(String(row[invCol] ?? "")));
  }, [statsTable, visible]);

  const toggle = (name: string) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      // Keep at least one inverter visible when possible
      if (next.size >= allNames.length && allNames.length > 1) {
        next.delete(name);
      }
      return next;
    });
  };

  const showAll = () => setHidden(new Set());
  const outlierNote =
    (result.metrics?.outlier_count ?? 0) > 0
      ? result.evidence.notes
      : null;

  if (result.status === "unavailable" || result.status === "error") {
    return null;
  }

  return (
    <div
      className="overflow-hidden rounded-xl border border-stone-200/90 bg-white/95 shadow-sm shadow-stone-900/[0.03] dark:border-stone-700 dark:bg-stone-900 dark:shadow-none"
      data-tour="diagnostics-module"
      data-analysis="box_plot"
    >
      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-stone-100 px-3.5 py-3 dark:border-stone-800">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-display text-base font-semibold text-stone-900 dark:text-stone-50 sm:text-lg">
              {result.title}
            </h3>
            <Badge tone="info">Analysis</Badge>
            <Badge tone="success">Ready</Badge>
          </div>
          <p className="mt-1 text-sm leading-relaxed text-stone-500 dark:text-stone-400">{result.summary}</p>
          {outlierNote ? (
            <p className="mt-1.5 text-xs text-stone-600 dark:text-stone-300">{outlierNote}</p>
          ) : null}
        </div>
      </div>

      <div className="space-y-3 px-3.5 py-3">
        {allNames.length > 0 && (
          <div>
            <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
              <p className="text-[10px] font-bold uppercase tracking-wide text-stone-400">
                Inverters on chart
              </p>
              <button
                type="button"
                className="text-[11px] font-semibold text-amber-800 underline dark:text-amber-200"
                onClick={showAll}
                disabled={hidden.size === 0}
              >
                Show all
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {allNames.map((name) => {
                const on = !hidden.has(name);
                return (
                  <button
                    key={name}
                    type="button"
                    onClick={() => toggle(name)}
                    aria-pressed={on}
                    className={`rounded-md border px-2 py-1 text-[11px] font-semibold transition ${
                      on
                        ? "border-brand-300 bg-brand-50 text-stone-900 dark:border-brand-700 dark:bg-brand-950/40 dark:text-amber-50"
                        : "border-stone-200 bg-stone-50 text-stone-400 line-through dark:border-stone-700 dark:bg-stone-800/40 dark:text-stone-500"
                    }`}
                    title={on ? `Hide ${name}` : `Show ${name}`}
                  >
                    {name}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {filteredChart ? (
          <div className="overflow-x-auto rounded-lg border border-stone-100 dark:border-stone-800">
            <PlotlyChart chart={filteredChart} tall fullWidth />
          </div>
        ) : (
          <p className="text-xs text-stone-500">No box plot chart in this result.</p>
        )}

        {statsTable && filteredRows.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-stone-100 dark:border-stone-800">
            <p className="bg-stone-50 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-stone-500 dark:bg-stone-800/50">
              {statsTable.title}
            </p>
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-stone-200 text-xs uppercase text-stone-400 dark:border-stone-700">
                  {statsTable.columns.map((c) => (
                    <th key={c} className="px-3 py-1.5 font-medium">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row, r) => (
                  <tr key={r} className="border-b border-stone-50 last:border-0 dark:border-stone-900">
                    {row.map((cell, c) => (
                      <td key={c} className="px-3 py-1.5 text-stone-700 dark:text-stone-300">
                        {String(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {result.recommendations.length > 0 && (
          <div className="rounded-md border border-stone-200/80 bg-stone-50/60 p-2.5 text-sm dark:border-stone-700 dark:bg-stone-800/30">
            <p className="mb-1 text-[10px] font-bold uppercase tracking-wide text-stone-400">Notes</p>
            <ul className="list-inside list-disc space-y-0.5 text-xs text-stone-600 dark:text-stone-300">
              {result.recommendations.map((rec, i) => (
                <li key={i}>{rec}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
