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


def _insolation_from_series(ts: pd.Series, irr: pd.Series) -> Optional[float]:
    if ts.empty or irr.empty:
        return None
    frame = pd.DataFrame({"timestamp_utc": ts, "irr_val": irr}).dropna(subset=["irr_val"])
    if frame.empty:
        return None
    frame = frame.sort_values("timestamp_utc").drop_duplicates("timestamp_utc", keep="first")
    dt_h = _dt_hours(frame["timestamp_utc"])
    insolation_wh_m2 = float((frame["irr_val"].to_numpy() * dt_h.to_numpy()).sum())
    return insolation_wh_m2 / 1000.0


def _insolation_kwh_m2(context: AnalysisContext) -> Optional[float]:
    """POA-preferring insolation used for PR (GTI when POA present, else GHI)."""
    plant_irr = extract_irradiance_frame(context)
    if plant_irr.empty:
        return None
    return _insolation_from_series(plant_irr["timestamp_utc"], plant_irr["irr_val"])


def _column_insolation_kwh_m2(context: AnalysisContext, column: str) -> Optional[float]:
    """Insolation from a single irradiance column (ghi_w_m2 or poa_w_m2)."""
    irr = context.canonical.frame(columns=["timestamp_utc", "device_type", column])
    if irr.empty or column not in irr.columns:
        return None
    preferred = irr[irr["device_type"].isin(["plant", "wms"])]
    pool = preferred if not preferred.empty else irr
    series = pd.to_numeric(pool[column], errors="coerce")
    return _insolation_from_series(pool["timestamp_utc"], series)


def _period_hours(ts: pd.Series, interval_h: float) -> Optional[float]:
    """Analysis-window hours for CUF/PLF (span of timestamps + one sample interval)."""
    clean = ts.dropna()
    if clean.empty:
        return None
    span_h = (clean.max() - clean.min()).total_seconds() / 3600.0
    hours = span_h + max(interval_h, 1.0 / 60.0)
    return hours if hours > 0 else None


def _capacity_factor_pct(total_ac_kwh: float, capacity_kw: float, period_hours: float) -> Optional[float]:
    if capacity_kw <= 0 or period_hours <= 0:
        return None
    return round((total_ac_kwh / (capacity_kw * period_hours)) * 100.0, 2)


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


def _inverter_dc_kwp_map(context: AnalysisContext, inverter_ids: list[str]) -> dict[str, float]:
    """DC kWp per inverter: architecture SCB nameplates, else equal plant split."""
    by_inv: dict[str, float] = {}
    for entry in (context.plant.architecture or {}).values():
        inv = entry.get("inverter_id")
        dc = entry.get("dc_capacity_kwp")
        if not inv or dc is None:
            continue
        try:
            dc_f = float(dc)
        except (TypeError, ValueError):
            continue
        if dc_f > 0:
            by_inv[str(inv)] = by_inv.get(str(inv), 0.0) + dc_f

    if by_inv:
        return by_inv

    plant_dc = context.plant.dc_capacity_kwp
    if plant_dc <= 0 or not inverter_ids:
        return {}
    share = plant_dc / len(inverter_ids)
    return {inv: share for inv in inverter_ids}


def _inverter_pr_rows(context: AnalysisContext) -> list[dict[str, float | str]]:
    """Per-inverter PR for Results Summary comparison (not a fault module).

    PR%_i = AC_kWh_i / (DC_kWp_i × insolation_kWh/m²) × 100 — same formula as plant PR.
    """
    insolation = _insolation_kwh_m2(context)
    if insolation is None or insolation <= 0:
        return []

    ac = context.canonical.frame(columns=["timestamp_utc", "device_type", "inverter_id", "ac_power_kw"])
    ac = ac[ac["device_type"] == "inverter"].dropna(subset=["inverter_id"])
    if ac.empty:
        return []

    interval_h = context.sample_interval_minutes / 60.0
    ac = ac.copy()
    ac["ac_power_kw"] = pd.to_numeric(ac["ac_power_kw"], errors="coerce").fillna(0.0)
    energy = (
        ac.groupby("inverter_id", sort=True)["ac_power_kw"]
        .sum()
        .mul(interval_h)
        .rename("ac_energy_kwh")
        .reset_index()
    )
    inv_ids = [str(x) for x in energy["inverter_id"].tolist()]
    dc_map = _inverter_dc_kwp_map(context, inv_ids)
    if not dc_map:
        return []

    rows: list[dict[str, float | str]] = []
    for _, r in energy.iterrows():
        inv = str(r["inverter_id"])
        dc_kwp = float(dc_map.get(inv, 0.0))
        if dc_kwp <= 0:
            continue
        ac_kwh = float(r["ac_energy_kwh"])
        pr = (ac_kwh / (dc_kwp * insolation)) * 100.0
        rows.append(
            {
                "inverter_id": inv,
                "pr_pct": round(pr, 2),
                "ac_energy_kwh": round(ac_kwh, 2),
                "dc_kwp": round(dc_kwp, 3),
            }
        )
    rows.sort(key=lambda x: (-float(x["pr_pct"]), str(x["inverter_id"])))
    return rows


def compute_plant_kpis(context: AnalysisContext, results: list[ResultObject]) -> dict:
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

    # GTI = POA insolation when present; GHI = horizontal-only series.
    gti_kwh_m2 = _column_insolation_kwh_m2(context, "poa_w_m2")
    ghi_kwh_m2 = _column_insolation_kwh_m2(context, "ghi_w_m2")
    # If only one irradiance channel exists, GTI falls back to the PR insolation series.
    if gti_kwh_m2 is None:
        gti_kwh_m2 = _insolation_kwh_m2(context)

    interval_h = context.sample_interval_minutes / 60.0
    period_h = _period_hours(ac["timestamp_utc"], interval_h) if not ac.empty else None
    cuf_pct: Optional[float] = None
    plf_pct: Optional[float] = None
    if total_ac_kwh is not None and period_h is not None:
        # CUF: AC nameplate; PLF: DC nameplate — distinct when AC≠DC.
        cuf_pct = _capacity_factor_pct(total_ac_kwh, context.plant.ac_capacity_kw, period_h)
        plf_pct = _capacity_factor_pct(total_ac_kwh, context.plant.dc_capacity_kwp, period_h)

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
        "cuf_pct": cuf_pct,
        "plf_pct": plf_pct,
        "ghi_kwh_m2": round(ghi_kwh_m2, 3) if ghi_kwh_m2 is not None else None,
        "gti_kwh_m2": round(gti_kwh_m2, 3) if gti_kwh_m2 is not None else None,
        "inverter_pr": _inverter_pr_rows(context),
    }
