/**
 * Map algorithm results → plain-language owner action cards.
 * Only surfaces real findings, blocked modules, and KPI gaps — never invents faults.
 *
 * Keep OWNER_COPY problem/next wording in sync with analytics/reports/owner_brief.py
 * (used by the PDF executive brief).
 */
import { buildFaultRows } from "@/lib/faultsTable";
import { diagnoseKpiGaps, fixHref, setupFixForAlgorithm, type FixTarget } from "@/lib/missingReasons";
import type { KpiResponse, ResultObject } from "@/types";

export type OwnerCta =
  | { kind: "investigate"; algorithmId: string; label: string }
  | { kind: "module"; algorithmId: string; label: string }
  | { kind: "setup"; href: string; label: string }
  | { kind: "section"; sectionId: "faults" | "bridge" | "diagnostics"; label: string };

export interface OwnerActionCard {
  id: string;
  priority: number;
  tone: "danger" | "warning" | "info";
  problem: string;
  impact: string;
  nextStep: string;
  cta: OwnerCta;
  algorithmId?: string;
  /** Raw severity for compact list (fault cards). */
  severity?: string | null;
  /** Estimated loss for ranking / summary chip. */
  lossKwh?: number | null;
}

export interface OwnerActionCenterModel {
  headline: string;
  subline: string;
  healthy: boolean;
  cards: OwnerActionCard[];
  /** Attention issues (danger/warning) — for summary chip. */
  issueCount: number;
  /** Sum of card lossKwh where available. */
  totalLossKwh: number | null;
}

/** How many full PROBLEM cards to show before compact rows. */
export const OWNER_ACTION_EXPANDED_LIMIT = 5;

const SEVERITY_RANK: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

/** Owner-facing problem / next-step copy keyed by algorithm (uses real result context). */
const OWNER_COPY: Record<
  string,
  {
    problem: (ctx: { equipment: string; count: number; title: string }) => string;
    next: string;
  }
> = {
  disconnected_strings: {
    problem: ({ equipment, count }) =>
      count > 1
        ? `${count} string groups look disconnected or offline (e.g. ${equipment}).`
        : `A string group looks disconnected or offline${equipment !== "—" ? ` (${equipment})` : ""}.`,
    next: "Check the listed SCB/strings on site, then Investigate evidence to confirm the fault window.",
  },
  module_damage: {
    problem: ({ equipment, count }) =>
      count > 1
        ? `${count} SCBs show voltage drop consistent with bypass diodes or module damage (e.g. ${equipment}).`
        : `Voltage drop suggests bypass diode or module damage${equipment !== "—" ? ` on ${equipment}` : ""}.`,
    next: "Inspect the affected modules for damage or diode activation; Investigate evidence for the voltage reference.",
  },
  string_outlier: {
    problem: ({ equipment, count }) =>
      count > 1
        ? `${count} strings/SCBs are running well below their peers (e.g. ${equipment}).`
        : `A string/SCB is running well below its peers${equipment !== "—" ? ` (${equipment})` : ""}.`,
    next: "Compare DC current on the peer group, then Investigate evidence or walk down the underperforming unit.",
  },
  clipping_power: {
    problem: ({ equipment, count }) =>
      count > 1
        ? `${count} inverters are clipping at AC rating while irradiance could support more (e.g. ${equipment}).`
        : `Inverter clipping at AC rating${equipment !== "—" ? ` (${equipment})` : ""} — irradiance could support more output.`,
    next: "Confirm whether curtailment is intentional; compare DC/AC oversizing and inverter ratings in Setup.",
  },
  clipping_current: {
    problem: ({ equipment, count }) =>
      count > 1
        ? `${count} SCB/MPPT paths show DC-side over-current clipping (e.g. ${equipment}).`
        : `DC-side current clipping detected${equipment !== "—" ? ` on ${equipment}` : ""}.`,
    next: "Map DC current evidence, validate architecture (strings per SCB), then Investigate the clip windows.",
  },
  inverter_efficiency: {
    problem: ({ equipment, count }) =>
      count > 1
        ? `${count} inverters show sustained conversion loss (e.g. ${equipment}).`
        : `Inverter conversion efficiency is below normal${equipment !== "—" ? ` (${equipment})` : ""}.`,
    next: "Review DC vs AC on the worst units; Investigate evidence and schedule inverter service if sustained.",
  },
  box_plot: {
    problem: () => "Inverter efficiency spread looks unusual across the fleet.",
    next: "Open the efficiency box plot in diagnostics and compare outliers to peers.",
  },
};

const BLOCKED_PRIORITY = new Set([
  "disconnected_strings",
  "module_damage",
  "clipping_power",
  "clipping_current",
  "inverter_efficiency",
  "string_outlier",
]);

function fmtKwh(v: number | null | undefined): string | null {
  if (v == null || !Number.isFinite(v) || v <= 0) return null;
  return `${v.toLocaleString(undefined, { maximumFractionDigits: 1 })} kWh`;
}

function severityLabel(sev: string | null): string {
  if (!sev) return "Needs review";
  const s = sev.toLowerCase();
  if (s === "critical" || s === "high") return `${sev} severity`;
  if (s === "medium") return "Medium severity";
  return `${sev} severity`;
}

function impactFrom(lossKwh: number | null, severity: string | null, fallback?: string): string {
  const kwh = fmtKwh(lossKwh);
  if (kwh && severity) return `${kwh} estimated loss · ${severityLabel(severity)}`;
  if (kwh) return `${kwh} estimated loss`;
  if (severity) return severityLabel(severity);
  return fallback ?? "Needs attention";
}

function humanMissing(summary: string): string {
  const cleaned = summary.replace(/\s+/g, " ").trim();
  if (!cleaned) return "Required inputs are missing for this check.";
  // Soften analyst phrasing without inventing new facts
  return cleaned
    .replace(/^Unavailable:\s*/i, "")
    .replace(/\bSCADA\b/gi, "plant data")
    .replace(/\bPOA\b/g, "plane-of-array irradiance")
    .replace(/\bGHI\b/g, "global horizontal irradiance");
}

function ownerNextForBlocked(algorithmId: string, fix: FixTarget): string {
  if (fix.kind === "upload") return "Re-upload plant data with the missing signals, then re-run analysis.";
  if (fix.hash === "architecture") {
    return "Add plant architecture (strings per SCB / modules per string) in Setup, then re-run.";
  }
  if (fix.hash === "plant") {
    return "Complete the plant capacity fields in Setup, then re-run.";
  }
  const field = fix.field;
  if (field === "ac_power_kw") return "Map inverter AC power in Setup → Column mapping, then re-run.";
  if (field === "poa_w_m2" || field === "ghi_w_m2") return "Map irradiance (POA or GHI) in Setup, then re-run.";
  if (field === "dc_power_kw" || field === "dc_current_a") return "Map DC current/power in Setup, then re-run.";
  if (OWNER_COPY[algorithmId]) return `Fix the missing inputs in Setup so “${algorithmId.replace(/_/g, " ")}” can run.`;
  return "Open Setup, supply the missing inputs, then re-run analysis.";
}

/**
 * Build prioritized owner actions from KPIs + algorithm results.
 */
export function buildOwnerActions(
  jobId: string,
  kpis: KpiResponse,
  results: ResultObject[],
): OwnerActionCenterModel {
  const cards: OwnerActionCard[] = [];
  const faultRows = buildFaultRows(results);
  const byAlgo = new Map<string, ResultObject>();
  for (const r of results) byAlgo.set(r.algorithm_id, r);

  // 1) Confirmed fault findings — one card per algorithm with real rows/loss
  const faultByAlgo = new Map<string, typeof faultRows>();
  for (const row of faultRows) {
    const list = faultByAlgo.get(row.algorithmId) ?? [];
    list.push(row);
    faultByAlgo.set(row.algorithmId, list);
  }

  for (const [algorithmId, rows] of faultByAlgo) {
    const result = byAlgo.get(algorithmId);
    if (!result || result.status !== "ok") continue;

    const copy = OWNER_COPY[algorithmId];
    const equipmentSample = rows
      .map((r) => r.equipment)
      .filter((e) => e && e !== "—")
      .slice(0, 2)
      .join(", ");
    const equipment = equipmentSample || result.affected_equipment.slice(0, 2).join(", ") || "—";
    const loss =
      rows.reduce((s, r) => s + (r.lossKwh ?? 0), 0) || result.loss_energy_kwh || null;
    const sev = result.severity;
    const sevRank = SEVERITY_RANK[(sev ?? "medium").toLowerCase()] ?? 2;

    const problem = copy
      ? copy.problem({ equipment, count: rows.length, title: result.title })
      : result.summary || `${result.title}: ${rows.length} finding(s) need review.`;

    const nextFromRec =
      result.recommendations.find((r) => r.trim().length > 0) ??
      copy?.next ??
      "Open the finding, Investigate evidence, then schedule a site check if confirmed.";

    cards.push({
      id: `fault-${algorithmId}`,
      priority: 10 + sevRank,
      tone: sevRank <= 1 ? "danger" : sevRank <= 2 ? "warning" : "info",
      problem,
      impact: impactFrom(loss, sev, `${rows.length} finding${rows.length === 1 ? "" : "s"}`),
      nextStep: nextFromRec,
      cta: {
        kind: "investigate",
        algorithmId,
        label: faultRows.some((r) => r.algorithmId === algorithmId) ? "Investigate" : "Go to module",
      },
      algorithmId,
      severity: sev,
      lossKwh: loss,
    });
  }

  // Also surface ok modules with loss/affected equipment but no table rows (already in buildFaultRows)
  // — covered above.

  // 2) Blocked / unavailable modules that matter to an owner
  for (const result of results) {
    if (result.status !== "unavailable" && result.status !== "error") continue;
    if (!BLOCKED_PRIORITY.has(result.algorithm_id) && result.status !== "error") continue;

    const fix = setupFixForAlgorithm(result.algorithm_id);
    const href = fixHref(jobId, fix);
    const missingBits = humanMissing(result.summary || result.error || "");

    cards.push({
      id: `blocked-${result.algorithm_id}`,
      priority: result.status === "error" ? 25 : 40,
      tone: result.status === "error" ? "danger" : "warning",
      problem:
        result.status === "error"
          ? `${result.title} failed to run.`
          : `${result.title} could not run — missing inputs.`,
      impact: result.status === "error" ? "Module error" : "Check unavailable until fixed",
      nextStep:
        result.status === "error"
          ? result.summary || "Re-check Setup inputs and re-run analysis."
          : `${missingBits} ${ownerNextForBlocked(result.algorithm_id, fix)}`,
      cta: { kind: "setup", href, label: "Fix in Setup" },
      algorithmId: result.algorithm_id,
    });
  }

  // 3) Revenue / tariff gap
  const kpiGaps = diagnoseKpiGaps(kpis);
  if (kpiGaps.revenue_loss_inr && (kpis.estimated_energy_loss_kwh ?? 0) > 0) {
    cards.push({
      id: "kpi-tariff",
      priority: 35,
      tone: "warning",
      problem: "Energy loss is quantified, but revenue impact cannot be shown.",
      impact: fmtKwh(kpis.estimated_energy_loss_kwh) ?? "Loss known · ₹ unknown",
      nextStep: "Add tariff (₹/kWh) under plant optional details in Setup, then re-run.",
      cta: {
        kind: "setup",
        href: fixHref(jobId, kpiGaps.revenue_loss_inr.fix),
        label: "Fix in Setup",
      },
    });
  } else if (kpiGaps.revenue_loss_inr && !kpis.revenue_loss_available) {
    cards.push({
      id: "kpi-tariff-soft",
      priority: 55,
      tone: "info",
      problem: "Revenue loss is not available for this run.",
      impact: "Optional — adds ₹ impact to loss figures",
      nextStep: "Add tariff (₹/kWh) in Setup if you want revenue alongside energy loss.",
      cta: {
        kind: "setup",
        href: fixHref(jobId, kpiGaps.revenue_loss_inr.fix),
        label: "Add tariff",
      },
    });
  }

  // Sort by priority (severity/impact). UI shows top N expanded + compact rest — no hard page-height stack.
  cards.sort((a, b) => {
    const lossDiff = (b.lossKwh ?? 0) - (a.lossKwh ?? 0);
    if (a.priority !== b.priority) return a.priority - b.priority;
    if (lossDiff !== 0) return lossDiff;
    return a.id.localeCompare(b.id);
  });

  // Soft-info tariff alone shouldn't block "healthy" if no real issues
  const attentionCards = cards.filter(
    (c) => c.tone !== "info" || c.id.startsWith("fault-") || c.id.startsWith("blocked-"),
  );
  const issueCount = attentionCards.filter((c) => c.tone === "danger" || c.tone === "warning").length;
  const healthy = issueCount === 0;

  const lossSum = cards.reduce((s, c) => s + (c.lossKwh ?? 0), 0);
  const totalLossKwh = lossSum > 0 ? lossSum : null;

  let headline: string;
  let subline: string;
  if (healthy) {
    headline = "Plant looks healthy";
    subline =
      cards.length > 0
        ? "No urgent faults or blocked checks. Optional improvements are listed here."
        : "No confirmed faults or blocked checks in this run. Use Loss bridge and Diagnostics for detail.";
  } else if (issueCount === 1) {
    headline = "1 issue needs attention";
    subline = "Start with the action below — then use the loss bridge and diagnostics for detail.";
  } else {
    headline = `${issueCount} issues need attention`;
    subline = "Prioritized for an asset owner. Open Loss bridge or Diagnostics for analyst depth.";
  }

  return { headline, subline, healthy, cards, issueCount, totalLossKwh };
}
