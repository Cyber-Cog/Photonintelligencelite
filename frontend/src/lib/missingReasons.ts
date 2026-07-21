import type { KpiResponse } from "@/types";
import { ALGORITHM_FIELD_HINTS } from "@/lib/canonicalHints";

/** Where the user should go to supply the missing input — points at an exact Setup control when possible. */
export type FixTarget =
  | {
      kind: "setup";
      hash: "mapping" | "plant" | "architecture";
      /** Plant form key, canonical field (ac_power_kw), or column:Name */
      field?: string;
    }
  | { kind: "upload" };

export interface MissingReason {
  id: string;
  message: string;
  fix: FixTarget;
}

export function fixHref(jobId: string, fix: FixTarget): string {
  if (fix.kind === "upload") return "/upload";
  if (fix.field) {
    return `/jobs/${jobId}/setup#${fix.hash}&field=${encodeURIComponent(fix.field)}`;
  }
  return `/jobs/${jobId}/setup#${fix.hash}`;
}

function hasPositive(v: number | null | undefined): boolean {
  return v != null && Number.isFinite(v) && v > 0;
}

/**
 * Infer why Expected/Actual cannot be built for the energy loss bridge.
 * Uses KPI intermediates: actual energy, specific yield (needs DC capacity), PR (needs irradiance).
 */
export function diagnoseBridgeGaps(kpis: KpiResponse): MissingReason[] {
  const gaps: MissingReason[] = [];
  const hasActual = hasPositive(kpis.total_ac_energy_kwh);
  const hasPr = hasPositive(kpis.performance_ratio_pct);
  const hasYield = hasPositive(kpis.specific_yield_kwh_per_kwp);

  if (hasActual && hasPr) return [];

  if (!hasActual) {
    gaps.push({
      id: "actual_energy",
      message: "Actual energy missing. Map inverter AC power and re-run analysis.",
      fix: { kind: "setup", hash: "mapping", field: "ac_power_kw" },
    });
  }

  if (!hasPr) {
    if (!hasActual) {
      gaps.push({
        id: "expected_energy",
        message:
          "Expected energy needs Performance Ratio. After AC power is mapped, ensure POA/GHI and plant DC capacity are set, then re-run.",
        fix: { kind: "setup", hash: "mapping", field: "ac_power_kw" },
      });
    } else if (!hasYield) {
      gaps.push({
        id: "dc_capacity",
        message: "Plant DC capacity missing. Set DC capacity (MWp) in plant config and re-run so Expected energy can be derived.",
        fix: { kind: "setup", hash: "plant", field: "dc_capacity_mwp" },
      });
    } else {
      gaps.push({
        id: "irradiance",
        message:
          "Expected energy needs Performance Ratio. Map POA or GHI irradiance and re-run so PR (and Expected) can be computed.",
        fix: { kind: "setup", hash: "mapping", field: "poa_w_m2" },
      });
    }
  }

  return gaps;
}

/** Per-KPI strip reasons when a card shows “Not available”. */
export function diagnoseKpiGaps(kpis: KpiResponse): {
  performance_ratio_pct: MissingReason | null;
  specific_yield_kwh_per_kwp: MissingReason | null;
  plant_availability_pct: MissingReason | null;
  revenue_loss_inr: MissingReason | null;
} {
  const hasActual = hasPositive(kpis.total_ac_energy_kwh);
  const hasPr = hasPositive(kpis.performance_ratio_pct);
  const hasYield = hasPositive(kpis.specific_yield_kwh_per_kwp);
  const hasAvail = kpis.plant_availability_pct != null;

  let performance_ratio_pct: MissingReason | null = null;
  if (!hasPr) {
    if (!hasActual) {
      performance_ratio_pct = {
        id: "kpi_pr_ac",
        message: "Map inverter AC power, then re-run",
        fix: { kind: "setup", hash: "mapping", field: "ac_power_kw" },
      };
    } else if (!hasYield) {
      performance_ratio_pct = {
        id: "kpi_pr_dc",
        message: "Set plant DC capacity (MWp), then re-run",
        fix: { kind: "setup", hash: "plant", field: "dc_capacity_mwp" },
      };
    } else {
      performance_ratio_pct = {
        id: "kpi_pr_irr",
        message: "Map POA or GHI irradiance, then re-run",
        fix: { kind: "setup", hash: "mapping", field: "poa_w_m2" },
      };
    }
  }

  let specific_yield_kwh_per_kwp: MissingReason | null = null;
  if (!hasYield) {
    if (!hasActual) {
      specific_yield_kwh_per_kwp = {
        id: "kpi_yield_ac",
        message: "Map inverter AC power, then re-run",
        fix: { kind: "setup", hash: "mapping", field: "ac_power_kw" },
      };
    } else {
      specific_yield_kwh_per_kwp = {
        id: "kpi_yield_dc",
        message: "Set plant DC capacity (MWp), then re-run",
        fix: { kind: "setup", hash: "plant", field: "dc_capacity_mwp" },
      };
    }
  }

  let plant_availability_pct: MissingReason | null = null;
  if (!hasAvail) {
    if (!hasActual) {
      plant_availability_pct = {
        id: "kpi_avail_ac",
        message: "Map inverter AC power, then re-run",
        fix: { kind: "setup", hash: "mapping", field: "ac_power_kw" },
      };
    } else {
      plant_availability_pct = {
        id: "kpi_avail_irr",
        message: "Map POA or GHI for daylight hours, then re-run",
        fix: { kind: "setup", hash: "mapping", field: "poa_w_m2" },
      };
    }
  }

  let revenue_loss_inr: MissingReason | null = null;
  if (!kpis.revenue_loss_available) {
    revenue_loss_inr = {
      id: "kpi_tariff",
      message: "Add tariff (₹/kWh) under plant optional details, then re-run",
      fix: { kind: "setup", hash: "plant", field: "tariff_inr_per_kwh" },
    };
  }

  return {
    performance_ratio_pct,
    specific_yield_kwh_per_kwp,
    plant_availability_pct,
    revenue_loss_inr,
  };
}

const ARCHITECTURE_ALGORITHMS = new Set([
  "module_damage",
  "disconnected_strings",
  "clipping_current",
]);

/** Setup deep-link for an unavailable algorithm card. */
export function setupFixForAlgorithm(algorithmId: string): FixTarget {
  if (ARCHITECTURE_ALGORITHMS.has(algorithmId)) {
    return { kind: "setup", hash: "architecture", field: "architecture" };
  }
  const hint = ALGORITHM_FIELD_HINTS[algorithmId];
  if (hint) {
    return { kind: "setup", hash: "mapping", field: hint };
  }
  return { kind: "setup", hash: "mapping" };
}
