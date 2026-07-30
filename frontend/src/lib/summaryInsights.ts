/** Derive Summary insight lists from algorithm results (worst inverters / string health). */
import { isAnalysisModule } from "@/lib/diagnosticsModules";
import type { ResultObject } from "@/types";

export type SummaryUnitRow = {
  id: string;
  label: string;
  metric: string;
  detail?: string;
  tone: "bad" | "warn" | "ok" | "neutral";
  algorithmId: string;
};

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

function fmtKwh(v: number): string {
  return `${v.toLocaleString(undefined, { maximumFractionDigits: 1 })} kWh`;
}

/** Rank inverters by loss from efficiency / clipping-power tables. */
export function worstInvertersFromResults(results: ResultObject[], limit = 5): SummaryUnitRow[] {
  const byInv = new Map<string, { loss: number; eff: number | null; algorithmId: string }>();

  for (const r of results) {
    if (r.status !== "ok" || isAnalysisModule(r.algorithm_id, r)) continue;
    if (r.algorithm_id !== "inverter_efficiency" && r.algorithm_id !== "clipping_power") continue;

    for (const table of r.tables) {
      const invI = colIndex(table.columns, "Inverter", "Unit", "Equipment");
      const lossI = colIndex(table.columns, "Loss (kWh)", "Estimated loss (kWh)", "Loss");
      const effI = colIndex(table.columns, "Efficiency (%)");
      if (invI == null) continue;

      for (const row of table.rows) {
        const id = row[invI] != null ? String(row[invI]).trim() : "";
        if (!id || id === "—") continue;
        const loss = lossI != null ? asNumber(row[lossI]) ?? 0 : 0;
        const eff = effI != null ? asNumber(row[effI]) : null;
        const prev = byInv.get(id);
        if (!prev || loss > prev.loss) {
          byInv.set(id, {
            loss: Math.max(loss, prev?.loss ?? 0),
            eff: eff ?? prev?.eff ?? null,
            algorithmId: r.algorithm_id,
          });
        } else if (eff != null && prev.eff == null) {
          prev.eff = eff;
        }
      }
    }
  }

  return [...byInv.entries()]
    .sort((a, b) => b[1].loss - a[1].loss)
    .slice(0, limit)
    .filter(([, v]) => v.loss > 0.05 || (v.eff != null && v.eff < 97))
    .map(([id, v]) => ({
      id: `inv-${id}`,
      label: id,
      metric: v.loss > 0 ? fmtKwh(v.loss) : v.eff != null ? `${v.eff.toFixed(1)}%` : "—",
      detail:
        v.eff != null && v.loss > 0
          ? `${v.eff.toFixed(1)}% efficiency`
          : v.eff != null
            ? "Efficiency"
            : "Loss share",
      tone: (v.loss > 50 || (v.eff != null && v.eff < 95) ? "bad" : v.loss > 5 ? "warn" : "neutral") as SummaryUnitRow["tone"],
      algorithmId: v.algorithmId,
    }));
}

/** String / SCB health from disconnected-strings and module-damage findings. */
export function stringHealthFromResults(results: ResultObject[], limit = 6): {
  rows: SummaryUnitRow[];
  healthyNote: string | null;
} {
  const rows: SummaryUnitRow[] = [];
  const seen = new Set<string>();

  const push = (item: SummaryUnitRow) => {
    if (seen.has(item.label)) return;
    seen.add(item.label);
    rows.push(item);
  };

  for (const r of results) {
    if (r.status !== "ok" || isAnalysisModule(r.algorithm_id, r)) continue;
    if (!["disconnected_strings", "module_damage"].includes(r.algorithm_id)) continue;

    for (const table of r.tables) {
      const eqI = colIndex(table.columns, "SCB", "SCB/MPPT", "String", "Equipment", "Inverter");
      const lossI = colIndex(table.columns, "Loss (kWh)", "Estimated loss (kWh)", "Loss");
      const kindI = colIndex(table.columns, "Fault kind", "Max missing strings");
      if (eqI == null) continue;

      for (const row of table.rows) {
        const label = row[eqI] != null ? String(row[eqI]).trim() : "";
        if (!label || label === "—") continue;
        const loss = lossI != null ? asNumber(row[lossI]) : null;
        const kind = kindI != null && row[kindI] != null ? String(row[kindI]) : null;
        const titleHint =
          r.algorithm_id === "disconnected_strings"
            ? "Disconnected"
            : kind || "Voltage fault";
        push({
          id: `${r.algorithm_id}-${label}`,
          label,
          metric: loss != null && loss > 0 ? fmtKwh(loss) : titleHint,
          detail: kind && loss != null && loss > 0 ? `${titleHint} · ${kind}` : titleHint,
          tone: r.algorithm_id === "disconnected_strings" || r.severity === "high" ? "bad" : "warn",
          algorithmId: r.algorithm_id,
        });
        if (rows.length >= limit) break;
      }
      if (rows.length >= limit) break;
    }
  }

  if (rows.length === 0) {
    const ds = results.find((r) => r.algorithm_id === "disconnected_strings");
    if (ds?.status === "ok") {
      return {
        rows: [],
        healthyNote: "No string/SCB fault findings in this run.",
      };
    }
    if (ds?.status === "unavailable") {
      return {
        rows: [],
        healthyNote: "String health needs DC current (+ irradiance / architecture for disconnected strings).",
      };
    }
    return { rows: [], healthyNote: "String/SCB checks did not produce findings for this upload." };
  }

  return { rows: rows.slice(0, limit), healthyNote: null };
}
