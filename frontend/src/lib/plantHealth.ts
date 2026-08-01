import type { KpiResponse, ResultObject } from "@/types";

export type PlantHealthTone = "good" | "warn" | "bad" | "neutral";

export type PlantHealthModel = {
  /** Primary score shown in the ring — PR when available, else module coverage. */
  score: number | null;
  scoreLabel: string;
  scoreUnit: string;
  tone: PlantHealthTone;
  headline: string;
  detail: string;
  readinessPct: number;
  okModules: number;
  blockedModules: number;
  faultCount: number;
  issueCount: number;
  availabilityPct: number | null;
  yieldKwhPerKwp: number | null;
  lossKwh: number | null;
};

function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n));
}

function toneFromPr(pr: number, faultCount: number, issueCount: number): PlantHealthTone {
  if (pr >= 80 && faultCount === 0 && issueCount === 0) return "good";
  if (pr >= 70 && issueCount <= 2) return "warn";
  if (pr < 60 || faultCount > 0 || issueCount > 3) return "bad";
  return "warn";
}

/**
 * Derive an overview health model from existing KPIs + module status.
 * Never invents SEO-style scores — prefers real PR, then module readiness.
 */
export function buildPlantHealth(opts: {
  kpis: KpiResponse;
  results: ResultObject[];
  issueCount: number;
}): PlantHealthModel {
  const { kpis, results, issueCount } = opts;
  const modules = results.filter((r) => r.algorithm_id !== "kpis");
  const okModules = modules.filter((r) => r.status === "ok").length;
  const blockedModules = modules.filter((r) => r.status === "unavailable").length;
  const total = okModules + blockedModules + modules.filter((r) => r.status === "error").length;
  const readinessPct = total > 0 ? Math.round((okModules / total) * 100) : 0;
  const faultCount = kpis.fault_count ?? 0;
  const pr = kpis.performance_ratio_pct;

  if (pr != null && Number.isFinite(pr)) {
    const score = clamp(Math.round(pr * 10) / 10, 0, 100);
    const tone = toneFromPr(score, faultCount, issueCount);
    const headline =
      tone === "good"
        ? "Plant performing within expected band"
        : tone === "bad"
          ? "Performance and faults need attention"
          : "Review actionable findings for this run";
    const detailParts = [
      `${okModules} module${okModules === 1 ? "" : "s"} ready`,
      blockedModules > 0 ? `${blockedModules} need data` : null,
      faultCount > 0 ? `${faultCount} fault${faultCount === 1 ? "" : "s"}` : "no active faults",
    ].filter(Boolean);
    return {
      score,
      scoreLabel: "Performance ratio",
      scoreUnit: "%",
      tone,
      headline,
      detail: detailParts.join(" · "),
      readinessPct,
      okModules,
      blockedModules,
      faultCount,
      issueCount,
      availabilityPct: kpis.plant_availability_pct,
      yieldKwhPerKwp: kpis.specific_yield_kwh_per_kwp,
      lossKwh: kpis.estimated_energy_loss_kwh,
    };
  }

  const tone: PlantHealthTone =
    readinessPct >= 70 && issueCount === 0
      ? "good"
      : readinessPct < 40 || issueCount > 2
        ? "bad"
        : "warn";

  return {
    score: readinessPct,
    scoreLabel: "Module coverage",
    scoreUnit: "%",
    tone: total === 0 ? "neutral" : tone,
    headline:
      total === 0
        ? "Waiting for analysis modules"
        : tone === "good"
          ? "Coverage looks solid — map remaining signals for deeper faults"
          : "Limited module coverage for this run",
    detail:
      total === 0
        ? "KPIs and diagnostics will appear when the run finishes."
        : `${okModules} ready · ${blockedModules} blocked · ${issueCount} issue${issueCount === 1 ? "" : "s"}`,
    readinessPct,
    okModules,
    blockedModules,
    faultCount,
    issueCount,
    availabilityPct: kpis.plant_availability_pct,
    yieldKwhPerKwp: kpis.specific_yield_kwh_per_kwp,
    lossKwh: kpis.estimated_energy_loss_kwh,
  };
}
