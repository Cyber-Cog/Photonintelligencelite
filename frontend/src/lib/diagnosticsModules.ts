/** Fault vs analysis module classification — keep in sync with analytics/common/module_kinds.py */

import type { ResultObject } from "@/types";

export const ANALYSIS_ALGORITHM_IDS = new Set(["box_plot"]);

export const FAULT_ALGORITHM_IDS = new Set([
  "disconnected_strings",
  "clipping_power",
  "clipping_current",
  "inverter_efficiency",
  "module_damage",
  "string_outlier",
]);

/** Preferred Diagnostics order: faults first, then analysis tools. */
export const DIAG_FAULT_ORDER = [
  "disconnected_strings",
  "clipping_power",
  "clipping_current",
  "inverter_efficiency",
  "module_damage",
  "string_outlier",
] as const;

export const DIAG_ANALYSIS_ORDER = ["box_plot"] as const;

const FIELD_LABELS: Record<string, string> = {
  ac_power_kw: "AC power (kW)",
  dc_power_kw: "DC power (kW)",
  dc_current_a: "DC current (A) / SMB string current",
  dc_voltage_v: "DC voltage (V)",
  poa_w_m2: "POA irradiance (W/m²)",
  ghi_w_m2: "GHI irradiance (W/m²)",
  module_temp_c: "Module temperature (°C)",
  ambient_temp_c: "Ambient temperature (°C)",
  device_id: "Device / equipment ID",
  inverter_id: "Inverter ID",
  scb_id: "SCB / SMB ID",
  string_id: "String ID",
};

export function isAnalysisModule(algorithmId: string, result?: ResultObject): boolean {
  if (result?.module_kind === "analysis") return true;
  return ANALYSIS_ALGORITHM_IDS.has(algorithmId);
}

export function isFaultModule(algorithmId: string, result?: ResultObject): boolean {
  if (result?.module_kind === "analysis" || result?.module_kind === "kpi") return false;
  if (ANALYSIS_ALGORITHM_IDS.has(algorithmId)) return false;
  if (algorithmId === "kpis") return false;
  return FAULT_ALGORITHM_IDS.has(algorithmId) || result?.module_kind === "fault" || !result?.module_kind;
}

export function labelField(field: string): string {
  if (FIELD_LABELS[field]) return FIELD_LABELS[field];
  if (field.includes(" or ")) {
    return field
      .split(" or ")
      .map((f) => labelField(f.trim()))
      .join(" / ");
  }
  return field.replace(/_/g, " ");
}

/** Explicit “Needs: …” line for unavailable modules. */
export function needsDataLine(result: ResultObject): string | null {
  if (result.status !== "unavailable") return null;
  const fields = (result.missing_fields ?? []).map(labelField);
  const config = result.missing_config ?? [];
  const parts: string[] = [];
  if (fields.length) parts.push(fields.join(", "));
  if (config.length) parts.push(config.join(", "));
  if (parts.length) return `Needs: ${parts.join("; ")}`;
  // Fall back to summary when orchestrator already wrote Needs: …
  const s = (result.summary || "").trim();
  if (/^needs:/i.test(s)) return s.split(/\. Next step:/i)[0].trim();
  if (s) return s;
  return "Needs: required signals or plant config (see Setup).";
}

export function hasFaultFindings(result: ResultObject): boolean {
  if (result.status !== "ok") return false;
  if (isAnalysisModule(result.algorithm_id, result)) return false;
  return (
    (result.loss_energy_kwh ?? 0) > 0.5 ||
    (result.severity != null && ["critical", "high", "medium"].includes(result.severity)) ||
    result.tables.some((t) => t.rows.length > 0)
  );
}

export type ModuleNavBadge = {
  label: string;
  className: string;
  title?: string;
};

/** Honest status chips for Diagnostics folder. */
export function moduleNavBadge(r: ResultObject): ModuleNavBadge {
  if (r.status === "unavailable") {
    const needs = needsDataLine(r) ?? "Needs data";
    return {
      label: "Needs data",
      className: "bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200",
      title: needs,
    };
  }
  if (r.status === "error") {
    return {
      label: "Error",
      className: "bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300",
      title: r.summary || r.error || "Module error",
    };
  }
  if (isAnalysisModule(r.algorithm_id, r)) {
    return {
      label: "Ready",
      className: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
      title: r.summary || "Analysis ready",
    };
  }
  if (hasFaultFindings(r)) {
    return {
      label: "Findings",
      className: "bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-200",
      title: r.summary || "Fault findings",
    };
  }
  return {
    label: "Healthy",
    className: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
    title: "Ran with no findings to report",
  };
}

export function orderDiagModules(results: ResultObject[]): {
  faults: ResultObject[];
  analysis: ResultObject[];
} {
  const byId = new Map(results.map((r) => [r.algorithm_id, r]));
  const faults: ResultObject[] = [];
  const analysis: ResultObject[] = [];
  const placed = new Set<string>();

  for (const id of DIAG_FAULT_ORDER) {
    const r = byId.get(id);
    if (!r) continue;
    faults.push(r);
    placed.add(id);
  }
  for (const id of DIAG_ANALYSIS_ORDER) {
    const r = byId.get(id);
    if (!r) continue;
    analysis.push(r);
    placed.add(id);
  }
  for (const r of results) {
    if (placed.has(r.algorithm_id) || r.algorithm_id === "kpis") continue;
    if (isAnalysisModule(r.algorithm_id, r)) analysis.push(r);
    else faults.push(r);
  }
  return { faults, analysis };
}
