"""Plant-level KPI assembly.

Ported (formulas only) from PIC's dashboard.py / dashboard_helpers.py:
  - PR%            = total_ac_kwh / (plant_dc_kwp x insolation_kwh_m2) x 100      [dashboard._plant_pr_pct]
  - Specific yield = total_ac_kwh / plant_dc_kwp                                  [dashboard.py inverter table]
  - Insolation     = sum(irradiance samples in W/m2) x dt_h / 1000                [dashboard_helpers.gti_insolation_kwh_m2_from_sums]
  - Revenue loss   = total_loss_mwh x 1000 x tariff, else "not available"        [soiling_queries.py pattern, generalized]

Plant Availability is a documented MVP simplification (see docs/algorithm_parity.md):
PIC's original formula weights inverter-shutdown / grid-breakdown fault-hours by impacted DC
capacity, which requires engines out of MVP scope (§7.8 algorithm list). PIC Lite instead
measures downtime as daylight hours (POA/GHI above a floor) during which total plant AC
output is negligible, which is deterministic and traceable to the same canonical data.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from analytics.core.context import AnalysisContext
from analytics.core.result import ResultObject, ResultStatus
from analytics.common.irradiance import extract_irradiance_frame

DAYLIGHT_IRRADIANCE_FLOOR_W_M2 = 50.0
DOWNTIME_AC_FRACTION_OF_CAPACITY = 0.005


def _dt_hours(ts: pd.Series) -> pd.Series:
    diffs = ts.sort_values().diff().dt.total_seconds() / 3600.0
    diffs = diffs[(diffs > 0) & (diffs <= 6.0)]
    median = float(diffs.median()) if not diffs.empty else 1.0 / 60.0
    return ts.diff().dt.total_seconds().div(3600.0).fillna(median).clip(lower=1.0 / 3600.0, upper=2.0)


def _insolation_kwh_m2(context: AnalysisContext) -> Optional[float]:
    plant_irr = extract_irradiance_frame(context)
    if plant_irr.empty:
        return None

    plant_irr = plant_irr.sort_values("timestamp_utc")
    dt_h = _dt_hours(plant_irr["timestamp_utc"])
    insolation_wh_m2 = float((plant_irr["irr_val"].to_numpy() * dt_h.to_numpy()).sum())
    return insolation_wh_m2 / 1000.0


def _specific_yield_and_pr(context: AnalysisContext, total_ac_kwh: float) -> tuple[Optional[float], Optional[float]]:
    dc_kwp = context.plant.dc_capacity_kwp
    specific_yield = (total_ac_kwh / dc_kwp) if dc_kwp > 0 else None

    insolation = _insolation_kwh_m2(context)
    pr_pct = None
    if insolation and insolation > 0 and dc_kwp > 0:
        pr_pct = round((total_ac_kwh / (dc_kwp * insolation)) * 100.0, 2)
    return specific_yield, pr_pct


def _plant_availability_pct(context: AnalysisContext) -> Optional[float]:
    df = context.canonical.frame(columns=["timestamp_utc", "device_type", "ac_power_kw", "poa_w_m2", "ghi_w_m2"])
    irr = extract_irradiance_frame(context)
    if irr.empty:
        return None

    daylight_ts = set(irr.loc[irr["irr_val"] > DAYLIGHT_IRRADIANCE_FLOOR_W_M2, "timestamp_utc"])
    if not daylight_ts:
        return None

    ac = df[df["device_type"] == "inverter"]
    if ac.empty:
        return None
    plant_ac_by_ts = ac.groupby("timestamp_utc")["ac_power_kw"].sum()
    plant_ac_by_ts = plant_ac_by_ts[plant_ac_by_ts.index.isin(daylight_ts)]
    if plant_ac_by_ts.empty:
        return None

    capacity_floor = context.plant.ac_capacity_kw * DOWNTIME_AC_FRACTION_OF_CAPACITY
    operating_samples = len(plant_ac_by_ts)
    downtime_samples = int((plant_ac_by_ts <= capacity_floor).sum())
    availability = (1.0 - downtime_samples / operating_samples) * 100.0
    return round(max(0.0, min(100.0, availability)), 2)


def compute_plant_kpis(context: AnalysisContext, results: list[ResultObject]) -> dict[str, float | None]:
    ac = context.canonical.frame(columns=["timestamp_utc", "device_type", "ac_power_kw"])
    ac = ac[ac["device_type"] == "inverter"]

    total_ac_kwh: Optional[float] = None
    if not ac.empty:
        ac = ac.sort_values("timestamp_utc")
        interval_h = context.sample_interval_minutes / 60.0
        total_ac_kwh = float(pd.to_numeric(ac["ac_power_kw"], errors="coerce").fillna(0).sum() * interval_h)

    specific_yield, pr_pct = (None, None)
    if total_ac_kwh is not None:
        specific_yield, pr_pct = _specific_yield_and_pr(context, total_ac_kwh)

    availability_pct = _plant_availability_pct(context)

    total_loss_kwh = sum(r.loss_energy_kwh or 0.0 for r in results if r.status == ResultStatus.OK)
    fault_count = sum(1 for r in results if r.status == ResultStatus.OK and (r.loss_energy_kwh or 0) > 0)

    revenue_loss: Optional[float] = None
    if context.plant.tariff_inr_per_kwh is not None:
        revenue_loss = round(total_loss_kwh * context.plant.tariff_inr_per_kwh, 2)

    return {
        "plant_availability_pct": availability_pct,
        "performance_ratio_pct": pr_pct,
        "specific_yield_kwh_per_kwp": round(specific_yield, 3) if specific_yield is not None else None,
        "estimated_energy_loss_kwh": round(total_loss_kwh, 2),
        "revenue_loss_inr": revenue_loss,
        "revenue_loss_available": context.plant.tariff_inr_per_kwh is not None,
        "fault_count": fault_count,
        "total_ac_energy_kwh": round(total_ac_kwh, 2) if total_ac_kwh is not None else None,
    }
