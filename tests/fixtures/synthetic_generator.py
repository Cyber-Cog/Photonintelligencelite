"""Deterministic synthetic SCADA data generator.

Produces a wide-format CSV (one row per equipment reading per timestamp, vendor-like
column headers) that exercises every algorithm in analytics/algorithms/ at least once, with
known faults injected at known equipment/timestamps. Used for:
  - the "Try Demo" landing page CTA (docs/PRD.md §7.1) — same file, no separate demo dataset
  - Phase 2 fault-injection tolerance tests (tests/test_*_algorithm.py)
  - benchmarking ingest/standardization/algorithm wall-clock time (docs/PRD.md §21 Phase 0/2)

Determinism: a fixed numpy Generator seed means re-running this script byte-for-byte
reproduces the same CSV and the same ground-truth fault windows every time.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from analytics.common.complete_analysis_pack import SCADA_COLUMNS

SEED = 20260101
RNG = np.random.default_rng(SEED)

PLANT_TIMEZONE = "Asia/Kolkata"
START_DATE = datetime(2026, 1, 1, 0, 0, 0)
DAYS = 3
INTERVAL_MINUTES = 5

INVERTERS = ["INV-01", "INV-02"]
SCBS_PER_INVERTER = 4
STRINGS_PER_SCB = 4

# Nameplate is sized to the string model below (16 strings × ~10 A × 620 V ≈ 99 kW DC peak
# per inverter) so the synthetic telemetry is *internally consistent* with the stated plant
# capacity — a plant owner viewing the demo sees realistic PR / specific-yield, and INV-01
# naturally clips at its AC rating around solar noon (DC:AC ≈ 1.1).
INVERTER_AC_RATED_KW = 90.0
INVERTER_DC_RATED_KWP = 100.0
STRING_ISC_STC_A = 10.0
SCB_VOLTAGE_NOMINAL_V = 620.0

# Known injected faults (ground truth for test assertions).
DS_FAULT = {"equipment_id": "INV-01-SCB-01-STR-01", "start_hour_offset": 33, "duration_hours": 9}  # day 2, 09:00-18:00 (well past the 360-min persistence gate, robust to rolling-median smoothing)
MODULE_DAMAGE_FAULT = {"equipment_id": "INV-01-SCB-02", "voltage_drop_pct": 0.15, "start_hour_offset": 9, "duration_hours": 56}
BYPASS_DIODE_FAULT = {"equipment_id": "INV-02-SCB-01", "voltage_drop_pct": 0.05, "start_hour_offset": 9, "duration_hours": 56}
STRING_OUTLIER_FAULT = {"equipment_id": "INV-02-SCB-03-STR-02", "current_fraction": 0.55, "start_hour_offset": 0, "duration_hours": 72}
LOW_EFFICIENCY_INVERTER = "INV-02"
LOW_EFFICIENCY_FACTOR = 0.965
HIGH_CURRENT_SCB = "INV-02-SCB-02"  # naturally saturates near Isc -> current clipping v1
HIGH_CURRENT_FACTOR = 1.12


@dataclass
class GroundTruth:
    disconnected_string: dict = field(default_factory=lambda: dict(DS_FAULT))
    module_damage: dict = field(default_factory=lambda: dict(MODULE_DAMAGE_FAULT))
    bypass_diode: dict = field(default_factory=lambda: dict(BYPASS_DIODE_FAULT))
    string_outlier: dict = field(default_factory=lambda: dict(STRING_OUTLIER_FAULT))
    low_efficiency_inverter: str = LOW_EFFICIENCY_INVERTER
    high_current_scb: str = HIGH_CURRENT_SCB
    generated_at: str = ""
    seed: int = SEED


def _timestamps() -> pd.DatetimeIndex:
    periods = int(DAYS * 24 * 60 / INTERVAL_MINUTES)
    return pd.date_range(START_DATE, periods=periods, freq=f"{INTERVAL_MINUTES}min")


def _irradiance_profile(ts: pd.DatetimeIndex) -> np.ndarray:
    hour_frac = ts.hour + ts.minute / 60.0
    base = np.clip(np.sin(np.pi * (hour_frac - 6.0) / 12.0), 0.0, None)
    base = np.where((hour_frac >= 6.0) & (hour_frac <= 18.0), base, 0.0)
    noise = RNG.normal(0.0, 0.015, size=len(ts))
    return np.clip(base * 950.0 * (1 + noise), 0.0, 1050.0)


def _in_fault_window(ts: pd.DatetimeIndex, start_hour_offset: float, duration_hours: float) -> np.ndarray:
    start = START_DATE + timedelta(hours=start_hour_offset)
    end = start + timedelta(hours=duration_hours)
    return (ts >= start) & (ts <= end)


def generate() -> tuple[pd.DataFrame, GroundTruth]:
    # Re-seed the module RNG so generate() is byte-for-byte reproducible regardless of how
    # many times it (or the irradiance helper) has already been called this process — the
    # session-scoped test fixtures rely on identical data every run.
    global RNG
    RNG = np.random.default_rng(SEED)
    ts = _timestamps()
    n = len(ts)
    poa = _irradiance_profile(ts)
    ghi = poa * (0.97 + RNG.normal(0, 0.01, size=n))
    ambient_temp = 22.0 + 8.0 * np.clip(np.sin(np.pi * (ts.hour - 6) / 12.0), 0, None) + RNG.normal(0, 0.5, size=n)
    module_temp = ambient_temp + poa * 0.03

    rows: list[dict] = []

    for inv in INVERTERS:
        inv_is_low_eff = inv == LOW_EFFICIENCY_INVERTER
        for scb_idx in range(1, SCBS_PER_INVERTER + 1):
            scb_id = f"{inv}-SCB-{scb_idx:02d}"
            scb_is_high_current = scb_id == HIGH_CURRENT_SCB
            for str_idx in range(1, STRINGS_PER_SCB + 1):
                string_id = f"{scb_id}-STR-{str_idx:02d}"
                base_current = (poa / 1000.0) * STRING_ISC_STC_A * (1 + RNG.normal(0, 0.01, size=n))
                base_current = np.clip(base_current, 0.0, None)

                if scb_is_high_current:
                    base_current = base_current * HIGH_CURRENT_FACTOR

                if string_id == STRING_OUTLIER_FAULT["equipment_id"]:
                    mask = _in_fault_window(ts, STRING_OUTLIER_FAULT["start_hour_offset"], STRING_OUTLIER_FAULT["duration_hours"])
                    base_current = np.where(mask, base_current * STRING_OUTLIER_FAULT["current_fraction"], base_current)

                if string_id == DS_FAULT["equipment_id"]:
                    mask = _in_fault_window(ts, DS_FAULT["start_hour_offset"], DS_FAULT["duration_hours"])
                    base_current = np.where(mask, 0.0, base_current)

                voltage = SCB_VOLTAGE_NOMINAL_V + RNG.normal(0, 1.5, size=n)
                dc_power = base_current * voltage / 1000.0
                for i in range(n):
                    if poa[i] <= 1.0 and base_current[i] <= 0.01:
                        continue
                    rows.append(
                        {
                            "Timestamp": ts[i],
                            "Equipment ID": string_id,
                            "DC Current (A)": round(float(base_current[i]), 3),
                            "DC Voltage (V)": round(float(voltage[i]), 2),
                            "DC Power (kW)": round(float(dc_power[i]), 4),
                        }
                    )

            # SCB rollup = sum of its strings' current, with SCB-level voltage/damage applied.
            scb_currents = np.zeros(n)
            for str_idx in range(1, STRINGS_PER_SCB + 1):
                string_id = f"{scb_id}-STR-{str_idx:02d}"
                base_current = (poa / 1000.0) * STRING_ISC_STC_A * (1 + RNG.normal(0, 0.01, size=n))
                base_current = np.clip(base_current, 0.0, None)
                if scb_id == HIGH_CURRENT_SCB:
                    base_current = base_current * HIGH_CURRENT_FACTOR
                if string_id == STRING_OUTLIER_FAULT["equipment_id"]:
                    mask = _in_fault_window(ts, STRING_OUTLIER_FAULT["start_hour_offset"], STRING_OUTLIER_FAULT["duration_hours"])
                    base_current = np.where(mask, base_current * STRING_OUTLIER_FAULT["current_fraction"], base_current)
                if string_id == DS_FAULT["equipment_id"]:
                    mask = _in_fault_window(ts, DS_FAULT["start_hour_offset"], DS_FAULT["duration_hours"])
                    base_current = np.where(mask, 0.0, base_current)
                scb_currents += base_current

            scb_voltage = SCB_VOLTAGE_NOMINAL_V + RNG.normal(0, 1.0, size=n)
            if scb_id == MODULE_DAMAGE_FAULT["equipment_id"]:
                mask = _in_fault_window(ts, MODULE_DAMAGE_FAULT["start_hour_offset"], MODULE_DAMAGE_FAULT["duration_hours"])
                scb_voltage = np.where(mask, scb_voltage * (1 - MODULE_DAMAGE_FAULT["voltage_drop_pct"]), scb_voltage)
            if scb_id == BYPASS_DIODE_FAULT["equipment_id"]:
                mask = _in_fault_window(ts, BYPASS_DIODE_FAULT["start_hour_offset"], BYPASS_DIODE_FAULT["duration_hours"])
                scb_voltage = np.where(mask, scb_voltage * (1 - BYPASS_DIODE_FAULT["voltage_drop_pct"]), scb_voltage)

            scb_dc_power = scb_currents * scb_voltage / 1000.0
            for i in range(n):
                if poa[i] <= 1.0 and scb_currents[i] <= 0.01:
                    continue
                rows.append(
                    {
                        "Timestamp": ts[i],
                        "Equipment ID": scb_id,
                        "DC Current (A)": round(float(scb_currents[i]), 3),
                        "DC Voltage (V)": round(float(scb_voltage[i]), 2),
                        "DC Power (kW)": round(float(scb_dc_power[i]), 4),
                    }
                )

        # Inverter rollup: sum of its SCBs' DC power (approximated from string current model),
        # then apply an efficiency curve + AC rated-power clipping (natural, not forced).
        inv_dc_power = np.zeros(n)
        for scb_idx in range(1, SCBS_PER_INVERTER + 1):
            scb_id = f"{inv}-SCB-{scb_idx:02d}"
            scb_currents = np.zeros(n)
            for str_idx in range(1, STRINGS_PER_SCB + 1):
                string_id = f"{scb_id}-STR-{str_idx:02d}"
                base_current = (poa / 1000.0) * STRING_ISC_STC_A * (1 + RNG.normal(0, 0.01, size=n))
                base_current = np.clip(base_current, 0.0, None)
                if scb_id == HIGH_CURRENT_SCB:
                    base_current = base_current * HIGH_CURRENT_FACTOR
                if string_id == STRING_OUTLIER_FAULT["equipment_id"]:
                    mask = _in_fault_window(ts, STRING_OUTLIER_FAULT["start_hour_offset"], STRING_OUTLIER_FAULT["duration_hours"])
                    base_current = np.where(mask, base_current * STRING_OUTLIER_FAULT["current_fraction"], base_current)
                if string_id == DS_FAULT["equipment_id"]:
                    mask = _in_fault_window(ts, DS_FAULT["start_hour_offset"], DS_FAULT["duration_hours"])
                    base_current = np.where(mask, 0.0, base_current)
                scb_currents += base_current
            inv_dc_power += scb_currents * SCB_VOLTAGE_NOMINAL_V / 1000.0

        eff = 0.985 - 0.01 * (inv_dc_power / INVERTER_DC_RATED_KWP)
        if inv_is_low_eff:
            eff = eff * LOW_EFFICIENCY_FACTOR
        ac_power_uncapped = inv_dc_power * np.clip(eff, 0.90, 0.99)
        ac_power = np.minimum(ac_power_uncapped, INVERTER_AC_RATED_KW)

        for i in range(n):
            if inv_dc_power[i] <= 0.01:
                continue
            rows.append(
                {
                    "Timestamp": ts[i],
                    "Equipment ID": inv,
                    "AC Power (kW)": round(float(ac_power[i]), 3),
                    "DC Power (kW)": round(float(inv_dc_power[i]), 3),
                }
            )

    for i in range(n):
        rows.append(
            {
                "Timestamp": ts[i],
                "Equipment ID": "PLANT-WMS-01",
                "Irradiance (W/m2)": round(float(poa[i]), 2),
                "GHI (W/m2)": round(float(ghi[i]), 2),
                "Module Temp (C)": round(float(module_temp[i]), 2),
                "Ambient Temp (C)": round(float(ambient_temp[i]), 2),
            }
        )

    columns = list(SCADA_COLUMNS)
    df = pd.DataFrame(rows)
    for col in columns:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[columns].sort_values(["Timestamp", "Equipment ID"]).reset_index(drop=True)
    df["Timestamp"] = df["Timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

    truth = GroundTruth(generated_at=datetime.utcnow().isoformat() + "Z")
    return df, truth


def write_demo_files(csv_path: Path, ground_truth_path: Path) -> None:
    df, truth = generate()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    ground_truth_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ground_truth_path, "w", encoding="utf-8") as f:
        json.dump(asdict(truth), f, indent=2)


if __name__ == "__main__":
    import sys

    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    write_demo_files(out_dir / "demo_plant_scada.csv", out_dir / "demo_plant_ground_truth.json")
    print(f"Wrote synthetic demo CSV and ground truth to {out_dir}")
