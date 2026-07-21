/** Flatten ResultObject findings into unified fault rows for the Results table. */
import type { ChartSpec, ResultObject } from "@/types";

export interface FaultRow {
  id: string;
  faultType: string;
  algorithmId: string;
  equipment: string;
  severity: string | null;
  lossKwh: number | null;
  timeWindow: string;
  status: string;
  result: ResultObject;
  /** Original table row index within its ResultTable (for matching). */
  tableIndex: number;
  rowIndex: number;
}

function colIndex(columns: string[], ...candidates: string[]): number | null {
  const lower = columns.map((c) => c.toLowerCase());
  for (const cand of candidates) {
    const i = lower.indexOf(cand.toLowerCase());
    if (i >= 0) return i;
  }
  return null;
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "" && !Number.isNaN(Number(value))) {
    return Number(value);
  }
  return null;
}

function timeWindow(result: ResultObject): string {
  const { time_range_start: start, time_range_end: end } = result.evidence;
  if (start && end) return `${start.slice(0, 16)} → ${end.slice(0, 16)}`;
  if (start) return start.slice(0, 16);
  return "—";
}

export function buildFaultRows(results: ResultObject[]): FaultRow[] {
  const rows: FaultRow[] = [];

  for (const result of results) {
    if (result.status !== "ok") continue;
    const window = timeWindow(result);

    if (!result.tables.length) {
      if ((result.loss_energy_kwh ?? 0) > 0 || result.affected_equipment.length > 0) {
        rows.push({
          id: `${result.algorithm_id}-summary`,
          faultType: result.title,
          algorithmId: result.algorithm_id,
          equipment: result.affected_equipment.slice(0, 3).join(", ") || "—",
          severity: result.severity,
          lossKwh: result.loss_energy_kwh,
          timeWindow: window,
          status: "Confirmed",
          result,
          tableIndex: -1,
          rowIndex: -1,
        });
      }
      continue;
    }

    result.tables.forEach((table, tableIndex) => {
      const eqI = colIndex(table.columns, "SCB", "SCB/MPPT", "Inverter", "Unit", "Equipment");
      const lossI = colIndex(table.columns, "Loss (kWh)", "Estimated loss (kWh)", "Loss");
      const kindI = colIndex(table.columns, "Fault kind");

      table.rows.forEach((raw, rowIndex) => {
        const equipment =
          eqI != null && eqI < raw.length && raw[eqI] != null && String(raw[eqI]).trim() !== ""
            ? String(raw[eqI])
            : "—";
        const lossFromRow = lossI != null && lossI < raw.length ? asNumber(raw[lossI]) : null;
        const kind =
          kindI != null && kindI < raw.length && raw[kindI] != null ? String(raw[kindI]) : null;

        rows.push({
          id: `${result.algorithm_id}-${tableIndex}-${rowIndex}`,
          faultType: kind ? `${result.title} (${kind})` : result.title,
          algorithmId: result.algorithm_id,
          equipment,
          severity: result.severity,
          lossKwh: lossFromRow ?? result.loss_energy_kwh,
          timeWindow: window,
          status: "Confirmed",
          result,
          tableIndex,
          rowIndex,
        });
      });
    });
  }

  return rows.sort((a, b) => (b.lossKwh ?? 0) - (a.lossKwh ?? 0));
}

/** Pick the best evidence / summary charts for a fault row investigate action.
 * Returns charts for the selected row (or top unit) — never dumps the full fleet set. */
export function chartsForFaultRow(row: FaultRow): { charts: ChartSpec[]; note: string | null } {
  const { result, equipment } = row;
  const evidence = result.evidence_charts ?? [];
  const summary = result.charts.filter((c) => c.chart_type !== "timeline");

  if (evidence.length > 0) {
    const matched = evidence.filter(
      (c) =>
        equipment !== "—" && (c.chart_id.includes(equipment) || c.title.includes(equipment)),
    );
    if (matched.length > 0) {
      return { charts: matched.slice(0, 2), note: null };
    }
    // Scale-safe fallback: top unit only (not all disconnected-string charts).
    return {
      charts: evidence.slice(0, 1),
      note:
        equipment !== "—"
          ? `No dedicated chart for ${equipment} — showing evidence for the top fault unit. Select another row and Investigate to swap.`
          : `Showing evidence for the top fault unit (${evidence.length} total available via findings table).`,
    };
  }

  if (summary.length > 0) {
    return {
      charts: summary.slice(0, 2),
      note: "No diagnostic timeseries for this row — showing summary charts from the algorithm result.",
    };
  }

  return {
    charts: [],
    note: "No evidence or summary charts were produced for this finding. Traceability details are shown below.",
  };
}
