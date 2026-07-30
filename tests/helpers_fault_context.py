"""Minimal AnalysisContext builders for MUST-fire / MUST-NOT-fire fault cases."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from analytics.common.config_loader import resolve_thresholds
from analytics.core.context import (
    CANONICAL_COLUMNS,
    AnalysisContext,
    CanonicalDataAccess,
    JobMeta,
    PlantConfig,
    ResolvedMapping,
)


def _empty_rows(n: int) -> dict[str, list]:
    return {c: [pd.NA] * n for c in CANONICAL_COLUMNS}


def build_context(
    frame: pd.DataFrame,
    *,
    architecture: dict | None = None,
    equipment_ratings: dict | None = None,
    sample_interval_minutes: int = 5,
    timezone_name: str = "Asia/Kolkata",
) -> AnalysisContext:
    plant = PlantConfig(
        plant_name="Fault Matrix Plant",
        ac_capacity_mw=0.18,
        dc_capacity_mwp=0.198,
        module_rating_wp=545.0,
        inverter_capacity_kw=90.0,
        module_technology="Mono PERC",
        bifacial=False,
        timezone=timezone_name,
        strings_per_scb=4,
        tariff_inr_per_kwh=3.5,
        pr_benchmark_pct=80.0,
        plant_type="fixed_tilt",
        equipment_ratings=equipment_ratings or {"INV-01": 90.0, "INV-02": 90.0},
        architecture=architecture
        or {
            f"{inv}-SCB-{i:02d}": {
                "inverter_id": inv,
                "strings_per_scb": 4,
                "modules_per_string": 11,
            }
            for inv in ("INV-01", "INV-02")
            for i in range(1, 5)
        },
    )
    thresholds = resolve_thresholds(plant.plant_type, plant.bifacial)
    return AnalysisContext(
        canonical=CanonicalDataAccess.from_frame(frame),
        plant=plant,
        mapping=ResolvedMapping(column_to_canonical={}, confidence_by_column={}),
        timezone=timezone_name,
        sample_interval_minutes=sample_interval_minutes,
        thresholds=thresholds,
        job_meta=JobMeta(job_id="fault-matrix", created_at="2026-01-01T00:00:00Z", trace_id="fault-matrix"),
    )


def make_scb_current_plant(
    *,
    hours: float = 8.0,
    interval_min: int = 5,
    fault_scb: str = "INV-01-SCB-01",
    healthy_current_a: float = 36.0,
    fault_current_a: float = 27.0,
    fault_start_hour: float = 0.5,
    fault_duration_hours: float | None = None,
    irradiance: float = 800.0,
    voltage: float = 620.0,
    scbs_per_inv: int = 4,
) -> pd.DataFrame:
    """Build SCB + WMS rows for DS / string-outlier style tests.

    Currents include small noise so the frozen-day pre-filter does not remove healthy
    peer SCBs (perfectly flat sensors are treated as frozen and excluded from the
    virtual reference — same as reference PIC ``ds_detection``).
    """
    n = int(hours * 60 / interval_min)
    start = datetime(2026, 3, 15, 9, 0, 0, tzinfo=timezone.utc)
    ts = [start + timedelta(minutes=interval_min * i) for i in range(n)]
    if fault_duration_hours is None:
        fault_duration_hours = hours

    fault_start = start + timedelta(hours=fault_start_hour)
    fault_end = fault_start + timedelta(hours=fault_duration_hours)
    rng = np.random.default_rng(42)

    rows: list[dict] = []
    for t in ts:
        r = _empty_rows(1)
        r["timestamp_utc"] = [t]
        r["device_id"] = ["PLANT-WMS-01"]
        r["device_type"] = ["plant"]
        r["poa_w_m2"] = [irradiance]
        r["ghi_w_m2"] = [irradiance * 0.97]
        rows.append({k: v[0] for k, v in r.items()})

        for inv in ("INV-01",):
            for i in range(1, scbs_per_inv + 1):
                scb = f"{inv}-SCB-{i:02d}"
                noise = float(rng.normal(0.0, 0.15))
                cur = healthy_current_a + noise
                if scb == fault_scb and fault_start <= t <= fault_end:
                    cur = fault_current_a + noise * 0.3
                r = _empty_rows(1)
                r["timestamp_utc"] = [t]
                r["device_id"] = [scb]
                r["device_type"] = ["scb"]
                r["inverter_id"] = [inv]
                r["scb_id"] = [scb]
                r["dc_current_a"] = [cur]
                r["dc_voltage_v"] = [voltage + float(rng.normal(0.0, 0.5))]
                rows.append({k: v[0] for k, v in r.items()})

    return pd.DataFrame(rows)


def make_string_current_plant(
    *,
    hours: float = 4.0,
    interval_min: int = 5,
    outlier_string: str = "INV-01-SCB-01-STR-02",
    healthy_a: float = 10.0,
    outlier_a: float = 4.0,
) -> pd.DataFrame:
    n = int(hours * 60 / interval_min)
    start = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
    ts = [start + timedelta(minutes=interval_min * i) for i in range(n)]
    rows: list[dict] = []
    for t in ts:
        for s_idx in range(1, 5):
            sid = f"INV-01-SCB-01-STR-{s_idx:02d}"
            cur = outlier_a if sid == outlier_string else healthy_a
            r = _empty_rows(1)
            r["timestamp_utc"] = [t]
            r["device_id"] = [sid]
            r["device_type"] = ["string"]
            r["inverter_id"] = ["INV-01"]
            r["scb_id"] = ["INV-01-SCB-01"]
            r["string_id"] = [sid]
            r["dc_current_a"] = [cur]
            r["dc_voltage_v"] = [620.0]
            rows.append({k: v[0] for k, v in r.items()})
    return pd.DataFrame(rows)


def make_voltage_damage_plant(
    *,
    hours: float = 6.0,
    interval_min: int = 15,
    damage_scb: str = "INV-01-SCB-02",
    damage_drop_pct: float = 0.15,
    healthy_v: float = 620.0,
) -> pd.DataFrame:
    n = int(hours * 60 / interval_min)
    start = datetime(2026, 3, 15, 9, 0, 0, tzinfo=timezone.utc)
    ts = [start + timedelta(minutes=interval_min * i) for i in range(n)]
    rows: list[dict] = []
    for t in ts:
        for i in range(1, 5):
            scb = f"INV-01-SCB-{i:02d}"
            volts = healthy_v * (1.0 - damage_drop_pct) if scb == damage_scb else healthy_v
            r = _empty_rows(1)
            r["timestamp_utc"] = [t]
            r["device_id"] = [scb]
            r["device_type"] = ["scb"]
            r["inverter_id"] = ["INV-01"]
            r["scb_id"] = [scb]
            r["dc_voltage_v"] = [volts]
            r["dc_current_a"] = [40.0]
            rows.append({k: val[0] for k, val in r.items()})
    return pd.DataFrame(rows)


def make_clipping_power_plant(
    *,
    rated_kw: float = 90.0,
    must_clip: bool = True,
) -> pd.DataFrame:
    """Daytime inverter AC + irradiance.

    When must_clip=True: after healthy calibration band, AC sits at rated while GTI rises
    (virtual curve above nameplate → clip). When False: AC tracks ~0.5×GTI×k well below rated.
    """
    interval_min = 5
    start = datetime(2026, 3, 15, 7, 0, 0, tzinfo=timezone.utc)
    # 7:00–17:00 local-ish UTC window for hour gate 7–18
    n = int(10 * 60 / interval_min)
    ts = [start + timedelta(minutes=interval_min * i) for i in range(n)]
    rows: list[dict] = []
    for i, t in enumerate(ts):
        # Ramp GTI: morning healthy band 200–700, afternoon high
        hour = 7 + i * interval_min / 60.0
        if hour < 10:
            gti = 300.0 + (hour - 7) * 80.0  # ~300–540 healthy
            ac = min(rated_kw * 0.7, gti * 0.12)
        elif must_clip:
            gti = 700.0 + (hour - 10) * 50.0  # rising above healthy
            ac = rated_kw  # hard plateau at rated
        else:
            gti = 700.0 + (hour - 10) * 50.0
            ac = min(rated_kw * 0.75, gti * 0.10)

        r = _empty_rows(1)
        r["timestamp_utc"] = [t]
        r["device_id"] = ["INV-01"]
        r["device_type"] = ["inverter"]
        r["inverter_id"] = ["INV-01"]
        r["ac_power_kw"] = [ac]
        r["dc_power_kw"] = [ac / 0.98]
        r["poa_w_m2"] = [gti]
        rows.append({k: v[0] for k, v in r.items()})

        # Duplicate irradiance on plant row (optional; inverter has poa)
        r2 = _empty_rows(1)
        r2["timestamp_utc"] = [t]
        r2["device_id"] = ["PLANT-WMS-01"]
        r2["device_type"] = ["plant"]
        r2["poa_w_m2"] = [gti]
        rows.append({k: v[0] for k, v in r2.items()})

    return pd.DataFrame(rows)


def make_efficiency_plant(*, degraded_inv: str = "INV-02", factor: float = 0.90) -> pd.DataFrame:
    interval_min = 5
    start = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
    n = int(4 * 60 / interval_min)
    ts = [start + timedelta(minutes=interval_min * i) for i in range(n)]
    rows: list[dict] = []
    for t in ts:
        for inv, eff in (("INV-01", 0.985), (degraded_inv, factor)):
            dc = 80.0
            ac = dc * eff
            r = _empty_rows(1)
            r["timestamp_utc"] = [t]
            r["device_id"] = [inv]
            r["device_type"] = ["inverter"]
            r["inverter_id"] = [inv]
            r["ac_power_kw"] = [ac]
            r["dc_power_kw"] = [dc]
            rows.append({k: v[0] for k, v in r.items()})
    return pd.DataFrame(rows)
