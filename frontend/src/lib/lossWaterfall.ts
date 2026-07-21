import type { KpiResponse, ResultObject } from "@/types";
import { CHART_SEGMENT } from "@/lib/chartTheme";
import { diagnoseBridgeGaps, type MissingReason } from "@/lib/missingReasons";

export type WaterfallUnit = "mwh" | "pct";

export interface BridgeSegment {
  key: string;
  label: string;
  invisible: number;
  visible: number;
  kind: "total" | "loss" | "unknown";
  fill: string;
  rawMwh: number;
}

export interface BridgeModel {
  mode: "bridge" | "categories";
  expectedMwh: number;
  actualMwh: number;
  unknownMwh: number;
  diagnosedMwh: number;
  segments: BridgeSegment[];
  /** Informational note only (e.g. overlap). Actionable gaps live in `gaps`. */
  note: string | null;
  gaps: MissingReason[];
}

const DIAG_ORDER: Record<string, number> = {
  inverter_efficiency: 10,
  clipping_power: 20,
  clipping_current: 30,
  disconnected_strings: 40,
  module_damage: 50,
  string_outlier: 60,
};

const DIAG_LABELS: Record<string, string> = {
  inverter_efficiency: "Inverter efficiency",
  clipping_power: "Clipping (power)",
  clipping_current: "Clipping (current)",
  disconnected_strings: "Disconnected strings",
  module_damage: "Module damage / diode",
  string_outlier: "String outlier",
};

function kwhToMwh(kwh: number): number {
  return kwh / 1000;
}

function diagnosedLosses(results: ResultObject[]): { id: string; label: string; mwh: number }[] {
  return results
    .filter((r) => r.status === "ok" && (r.loss_energy_kwh ?? 0) > 1e-6)
    .map((r) => ({
      id: r.algorithm_id,
      label: DIAG_LABELS[r.algorithm_id] ?? r.title,
      mwh: kwhToMwh(r.loss_energy_kwh ?? 0),
    }))
    .sort((a, b) => {
      const oa = DIAG_ORDER[a.id] ?? 100;
      const ob = DIAG_ORDER[b.id] ?? 100;
      if (oa !== ob) return oa - ob;
      return b.mwh - a.mwh;
    });
}

/**
 * Build a loss-analysis-style energy bridge from Results KPIs + algorithm losses.
 * Mirrors solar_analytics_codex_bundle `waterfall_bridge` stacking:
 * Expected → diagnosed losses → Unknown → Actual.
 *
 * Expected = Actual ÷ (PR/100). Requires `total_ac_energy_kwh` and `performance_ratio_pct`.
 */
export function buildLossBridge(kpis: KpiResponse, results: ResultObject[]): BridgeModel | null {
  const cats = diagnosedLosses(results);
  const diagnosedMwh = cats.reduce((s, c) => s + c.mwh, 0);
  const actualKwh = kpis.total_ac_energy_kwh;
  const pr = kpis.performance_ratio_pct;
  const gaps = diagnoseBridgeGaps(kpis);

  const canBridge =
    actualKwh != null &&
    actualKwh > 0 &&
    pr != null &&
    pr > 0 &&
    Number.isFinite(pr);

  if (!canBridge && cats.length === 0) {
    return null;
  }

  if (!canBridge) {
    let cum = diagnosedMwh;
    const segments: BridgeSegment[] = cats.map((c) => {
      cum -= c.mwh;
      return {
        key: `diag_${c.id}`,
        label: c.label,
        invisible: Math.max(0, cum),
        visible: c.mwh,
        kind: "loss" as const,
        fill: CHART_SEGMENT.loss,
        rawMwh: c.mwh,
      };
    });
    return {
      mode: "categories",
      expectedMwh: 0,
      actualMwh: 0,
      unknownMwh: 0,
      diagnosedMwh,
      segments,
      note: null,
      gaps,
    };
  }

  const actualMwh = kwhToMwh(actualKwh!);
  const expectedMwh = actualMwh / (pr! / 100);
  const unknownMwh = Math.max(0, expectedMwh - actualMwh - diagnosedMwh);
  const overlap =
    expectedMwh - actualMwh - diagnosedMwh < -1e-6
      ? "Diagnosed losses may overlap across modules; unknown is clamped at zero."
      : null;

  const segments: BridgeSegment[] = [];
  segments.push({
    key: "expected",
    label: "Expected energy",
    invisible: 0,
    visible: expectedMwh,
    kind: "total",
    fill: CHART_SEGMENT.expected,
    rawMwh: expectedMwh,
  });

  let cum = expectedMwh;
  for (const c of cats) {
    cum -= c.mwh;
    segments.push({
      key: `diag_${c.id}`,
      label: c.label,
      invisible: Math.max(0, cum),
      visible: c.mwh,
      kind: "loss",
      fill: CHART_SEGMENT.loss,
      rawMwh: c.mwh,
    });
  }

  segments.push({
    key: "unknown",
    label: "Unknown loss",
    invisible: actualMwh,
    visible: unknownMwh,
    kind: "unknown",
    fill: CHART_SEGMENT.unknown,
    rawMwh: unknownMwh,
  });

  segments.push({
    key: "actual",
    label: "Actual energy (metered)",
    invisible: 0,
    visible: actualMwh,
    kind: "total",
    fill: CHART_SEGMENT.actual,
    rawMwh: actualMwh,
  });

  return {
    mode: "bridge",
    expectedMwh,
    actualMwh,
    unknownMwh,
    diagnosedMwh,
    segments,
    note: overlap,
    gaps: [],
  };
}

export function scaleSegments(segments: BridgeSegment[], unit: WaterfallUnit, expectedMwh: number): BridgeSegment[] {
  if (unit !== "pct" || expectedMwh <= 0) return segments;
  const s = 100 / expectedMwh;
  return segments.map((seg) => ({
    ...seg,
    invisible: seg.invisible * s,
    visible: seg.visible * s,
  }));
}

export const WATERFALL_LEGEND = [
  { key: "expected", name: "Expected", fill: CHART_SEGMENT.expected },
  { key: "diagnostics", name: "Fault diagnostics", fill: CHART_SEGMENT.loss },
  { key: "unknown", name: "Unknown", fill: CHART_SEGMENT.unknown },
  { key: "actual", name: "Actual", fill: CHART_SEGMENT.actual },
] as const;
