"""Module damage and bypass diode failure detection from SCB DC voltage telemetry.

Ported (formulas only) from PIC's backend/engine/module_damage.py. Classification uses %
deviation of each SCB's voltage from a plant-level reference (median of the top-quartile
inverter-median voltage per timestamp):
  3-8%   -> bypass_diode  (one bypass zone partially short-circuits the string)
  8-30%  -> module_damage (one or more modules fully disconnected/shorted)
Energy loss proxy = dc_kw x pct_deviation x dt_h, summed over confirmed-fault samples.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.charts.builders import bar_chart, diagnostic_line_chart, line_chart
from analytics.core.context import AnalysisContext
from analytics.core.registry import register_algorithm
from analytics.core.result import EvidenceRef, ResultObject, ResultStatus, ResultTable

ALGORITHM_ID = "module_damage"
VERSION = "1.0.0-port"

DEFAULT_MODULES_PER_STRING = 20


def _forward_dt_hours(ts: pd.Series, fallback_min: float) -> pd.Series:
    """Per-sample forward Δt (time to *next* sample) in hours.

    Ported from PIC's ``module_damage.py::_forward_dt_hours`` so a data gap after a sample
    is not integrated as an unbounded loss interval. Δt is capped at 2× the per-SCB median
    cadence; the last sample of each SCB uses the median.
    """
    t = pd.to_datetime(ts, errors="coerce")
    dt = t.shift(-1).sub(t).dt.total_seconds() / 3600.0
    valid = dt[(dt > 0) & (dt <= 2.0)]
    median = float(valid.median()) if not valid.empty else (fallback_min / 60.0)
    if not np.isfinite(median) or median <= 0:
        median = fallback_min / 60.0
    cap = max(2.0 * median, 1.0 / 60.0)
    return dt.fillna(median).clip(lower=1.0 / 3600.0, upper=cap)


def _plant_ref_v(vals: pd.Series) -> float:
    x = vals.dropna().to_numpy(dtype=float)
    if x.size == 0:
        return float("nan")
    q75 = float(np.percentile(x, 75))
    top = x[x >= q75 - 1e-6]
    return float(np.median(top)) if top.size else float(np.median(x))


def _scb_dc_kw(scb_id: str, context: AnalysisContext) -> float:
    arch = context.plant.architecture.get(scb_id, {})
    strings_per_scb = arch.get("strings_per_scb") or context.plant.strings_per_scb or 8
    modules_per_string = arch.get("modules_per_string") or DEFAULT_MODULES_PER_STRING
    modules_total = max(1, int(strings_per_scb) * int(modules_per_string))
    return modules_total * context.plant.module_rating_wp / 1000.0


@register_algorithm(ALGORITHM_ID, VERSION, required_fields=("dc_voltage_v",))
def run(context: AnalysisContext) -> ResultObject:
    thresholds = context.threshold_group(ALGORITHM_ID)
    bypass_lo = thresholds.get("bypass_pct_lo", 0.03)
    bypass_hi = thresholds.get("bypass_pct_hi", 0.08)
    damage_min = thresholds.get("damage_pct_min", 0.08)
    damage_max = thresholds.get("damage_pct_max", 0.30)
    min_samples = int(thresholds.get("min_persist_samples", 4))

    df = context.canonical.frame(columns=["timestamp_utc", "device_type", "scb_id", "inverter_id", "dc_voltage_v", "dc_current_a"])
    df = df[df["device_type"] == "scb"].dropna(subset=["scb_id", "dc_voltage_v"])
    if df.empty:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "No SCB-level DC voltage telemetry found in this upload.")

    df["dc_voltage_v"] = pd.to_numeric(df["dc_voltage_v"], errors="coerce")
    df = df.dropna(subset=["dc_voltage_v"])
    if df["inverter_id"].isna().all():
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "SCB rows are missing an inverter parent — cannot build a reference voltage.")

    inv_med = df.groupby(["timestamp_utc", "inverter_id"])["dc_voltage_v"].median().rename("inv_median_v").reset_index()
    df = df.merge(inv_med, on=["timestamp_utc", "inverter_id"], how="left")

    ref_map = inv_med.groupby("timestamp_utc")["inv_median_v"].apply(_plant_ref_v)
    df["ref_v"] = df["timestamp_utc"].map(ref_map)

    df["pct_dev"] = np.where(df["ref_v"] > 1.0, ((df["ref_v"] - df["dc_voltage_v"]) / df["ref_v"]).clip(lower=0.0), 0.0)

    def classify(pct: float) -> str:
        if bypass_lo <= pct < bypass_hi:
            return "bypass_diode"
        if damage_min <= pct <= damage_max:
            return "module_damage"
        return "normal"

    df["fault_kind"] = df["pct_dev"].map(classify)
    df["is_fault"] = df["fault_kind"] != "normal"

    # PIC parity: integrate loss with per-SCB *forward* Δt (capped) instead of a flat
    # interval, so gaps after a sample are not counted as loss time.
    df = df.sort_values(["scb_id", "timestamp_utc"]).reset_index(drop=True)
    df["dt_h"] = df.groupby("scb_id", sort=False)["timestamp_utc"].transform(
        lambda s: _forward_dt_hours(s, context.sample_interval_minutes)
    )
    df["dc_kw"] = df["scb_id"].map(lambda s: _scb_dc_kw(s, context))
    df["loss_kwh_step"] = np.where(df["is_fault"], df["dc_kw"] * df["pct_dev"] * df["dt_h"], 0.0)

    rows = []
    for scb_id, g in df.groupby("scb_id"):
        fault_g = g[g["is_fault"]]
        if len(fault_g) < min_samples:
            continue
        kind = fault_g["fault_kind"].mode().iloc[0]
        rows.append(
            {
                "scb_id": scb_id,
                "inverter_id": g["inverter_id"].iloc[0],
                "fault_kind": kind,
                "voltage_drop_pct": round(float(fault_g["pct_dev"].median()) * 100.0, 2),
                "loss_kwh": round(float(g["loss_kwh_step"].sum()), 3),
                "fault_points": int(len(fault_g)),
            }
        )

    if not rows:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "No SCB sustained a voltage deviation long enough to confirm a fault.")

    status_df = pd.DataFrame(rows).sort_values("loss_kwh", ascending=False)
    bypass = status_df[status_df["fault_kind"] == "bypass_diode"]
    damage = status_df[status_df["fault_kind"] == "module_damage"]
    total_loss = float(status_df["loss_kwh"].sum())

    trend = df[df["is_fault"]].copy()
    trend["hour"] = trend["timestamp_utc"].dt.floor("h")
    hourly_loss = trend.groupby("hour")["loss_kwh_step"].sum().reset_index()

    charts = [
        bar_chart("module_damage_loss_by_scb", "Energy Loss by SCB", status_df["scb_id"].tolist(), status_df["loss_kwh"].round(2).tolist(), y_title="Loss (kWh)", color="#d97706"),
    ]
    if not hourly_loss.empty:
        charts.append(
            line_chart(
                "module_damage_loss_trend",
                "Voltage-Deviation Loss Trend",
                hourly_loss["hour"].dt.strftime("%Y-%m-%d %H:%M").tolist(),
                {"Loss (kWh)": hourly_loss["loss_kwh_step"].round(3).tolist()},
                y_title="Loss (kWh)",
            )
        )

    top_scb = status_df.iloc[0]["scb_id"]
    scb_df = df[df["scb_id"] == top_scb].sort_values("timestamp_utc")
    if len(scb_df) > 4000:
        scb_df = scb_df.iloc[:: max(1, len(scb_df) // 4000)]
    ts_labels = scb_df["timestamp_utc"].dt.strftime("%Y-%m-%d %H:%M").tolist()
    evidence_charts = [
        diagnostic_line_chart(
            f"md_evidence_{top_scb}",
            f"Investigate: {top_scb} — plant reference vs measured voltage",
            ts_labels,
            {
                "Plant reference V": scb_df["ref_v"].round(2).tolist(),
                "Measured SCB voltage (V)": scb_df["dc_voltage_v"].round(2).tolist(),
            },
            fault_bands=[
                {"start": str(g["timestamp_utc"].min()), "end": str(g["timestamp_utc"].max())}
                for _, g in scb_df[scb_df["is_fault"]].groupby((scb_df["is_fault"] != scb_df["is_fault"].shift()).cumsum())
            ][:8],
            y_title="Voltage (V)",
            rule_text=(
                f"Rule: bypass diode {bypass_lo*100:.0f}–{bypass_hi*100:.0f}% drop; module damage {damage_min*100:.0f}–{damage_max*100:.0f}% "
                f"below plant reference (median of top-quartile inverter medians). Orange/red bands = fault samples."
            ),
        )
    ]

    table = ResultTable(
        title="Confirmed SCB faults",
        columns=["SCB", "Inverter", "Fault kind", "Voltage drop (%)", "Loss (kWh)", "Fault samples"],
        rows=[[r.scb_id, r.inverter_id, r.fault_kind, r.voltage_drop_pct, r.loss_kwh, r.fault_points] for r in status_df.itertuples()],
    )

    recommendations = []
    if len(damage) > 0:
        recommendations.append(f"{len(damage)} SCB(s) show module-damage-level voltage drop (8-30%) — schedule a physical string inspection: {', '.join(damage['scb_id'].head(5))}.")
    if len(bypass) > 0:
        recommendations.append(f"{len(bypass)} SCB(s) show bypass-diode-level voltage drop (3-8%) — monitor for progression before it becomes full module damage.")

    severity = "high" if len(damage) > 0 else ("medium" if len(bypass) > 0 else "low")

    return ResultObject(
        algorithm_id=ALGORITHM_ID,
        algorithm_version=VERSION,
        status=ResultStatus.OK,
        title="Module Damage & Bypass Diode Failure",
        summary=f"{len(damage)} SCB(s) show module-damage-level deviation and {len(bypass)} show bypass-diode-level deviation, totaling {total_loss:.1f} kWh of loss.",
        severity=severity,
        confidence=0.8,
        affected_equipment=status_df["scb_id"].tolist(),
        loss_energy_kwh=round(total_loss, 2),
        metrics={"bypass_diode_scb_count": float(len(bypass)), "module_damage_scb_count": float(len(damage))},
        tables=[table],
        charts=charts,
        recommendations=recommendations or ["No sustained voltage-deviation faults require action."],
        thresholds_used={"bypass_pct_lo": bypass_lo, "bypass_pct_hi": bypass_hi, "damage_pct_min": damage_min, "damage_pct_max": damage_max},
        evidence=EvidenceRef(
            equipment_ids=status_df["scb_id"].tolist(),
            time_range_start=str(df["timestamp_utc"].min()),
            time_range_end=str(df["timestamp_utc"].max()),
            source_fields=["dc_voltage_v"],
            affected_sample_count=int(status_df["fault_points"].sum()),
            total_sample_count=int(len(df)),
            notes=f"Top evidence: {top_scb} — reference vs measured voltage with fault-window shading.",
        ),
        evidence_charts=evidence_charts,
    )
