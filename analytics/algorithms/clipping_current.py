"""Inverter clipping by current (DC-side / MPPT current saturation) — v1.

NEW algorithm — not present in the source PIC codebase (its clipping_derating.py has a
`loss_current_clipping_kwh` field hard-coded to 0.0, reserved for future DC-side work; see
docs/algorithm_parity.md). This is a first version built for PIC Lite:

Mirrors the clipping-by-power approach (analytics/algorithms/clipping_power.py) but on the
DC current side: builds a virtual current curve I_virtual(t) = k x irradiance(t) per SCB/MPPT
from healthy, non-saturated samples, then flags sustained saturation at a configured fraction
of the equipment's rated current under sufficient irradiance. Loss is the missing DC power
(gap_current x voltage) integrated over time.

Because there is no PIC baseline to validate against, thresholds are marked v1 and must be
checked against real plant data (synthetic fault-injection tests live in
tests/test_clipping_current.py) before being trusted for production severity claims.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.charts.builders import bar_chart, line_chart
from analytics.common.irradiance import extract_irradiance_frame
from analytics.common.irr_join import merge_irradiance_onto
from analytics.core.context import AnalysisContext
from analytics.core.registry import register_algorithm
from analytics.core.result import EvidenceRef, ResultObject, ResultStatus, ResultTable

ALGORITHM_ID = "clipping_current"
VERSION = "0.1.0-v1"

DEFAULT_ISC_STC_A = 10.0


def _rated_current_a(scb_id: str, context: AnalysisContext, observed_p99: dict[str, float]) -> float:
    arch = context.plant.architecture.get(scb_id, {})
    strings_per_scb = arch.get("strings_per_scb") or context.plant.strings_per_scb
    if strings_per_scb:
        return float(strings_per_scb) * DEFAULT_ISC_STC_A
    observed = observed_p99.get(scb_id)
    return observed if observed and observed > 0 else DEFAULT_ISC_STC_A * 8


def _grouped_persistence(mask: pd.Series, groups: pd.Series, min_run: int) -> pd.Series:
    if min_run <= 1 or not mask.any():
        return mask
    boundary = (mask != mask.shift(1)) | (groups != groups.shift(1))
    seg = boundary.cumsum()
    run_sizes = mask.groupby(seg).transform("size")
    return mask & (run_sizes >= min_run)


@register_algorithm(ALGORITHM_ID, VERSION, required_fields=("dc_current_a",))
def run(context: AnalysisContext) -> ResultObject:
    t = context.threshold_group(ALGORITHM_ID)
    hit_ratio = t.get("current_limit_hit_ratio", 0.97)
    irr_min = t.get("irradiance_min_w_m2", 400.0)
    persist_min = int(t.get("persist_min_samples", 3))
    min_active_frac = t.get("min_active_frac", 0.03)

    scb = context.canonical.frame(columns=["timestamp_utc", "device_type", "scb_id", "dc_current_a", "dc_voltage_v"])
    scb = scb[scb["device_type"] == "scb"].dropna(subset=["scb_id", "dc_current_a"])
    if scb.empty:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "No SCB/MPPT-level DC current telemetry found in this upload.")

    irr = extract_irradiance_frame(context)
    if irr.empty:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "No plant/WMS irradiance telemetry found — current clipping cannot be classified without a reference curve.")

    scb["dc_current_a"] = pd.to_numeric(scb["dc_current_a"], errors="coerce")
    scb["dc_voltage_v"] = pd.to_numeric(scb.get("dc_voltage_v"), errors="coerce")
    scb = scb.dropna(subset=["dc_current_a"]).sort_values(["scb_id", "timestamp_utc"])

    df = merge_irradiance_onto(scb, irr, out_col="irr", tolerance_min=15.0)
    df = df.dropna(subset=["irr"])
    if df.empty:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "No SCB samples could be aligned with irradiance timestamps.")

    df["dt_h"] = (df.groupby("scb_id")["timestamp_utc"].diff().dt.total_seconds() / 3600.0)
    df["dt_h"] = df["dt_h"].fillna(context.sample_interval_minutes / 60.0).clip(lower=1 / 3600.0, upper=5 / 60.0)

    observed_p99 = scb.groupby("scb_id")["dc_current_a"].quantile(0.99).to_dict()
    df["rated_current"] = df["scb_id"].map(lambda s: _rated_current_a(s, context, observed_p99))

    min_active = min_active_frac * df["rated_current"]
    healthy = (df["irr"] >= irr_min) & (df["dc_current_a"] >= min_active) & (df["dc_current_a"] < hit_ratio * df["rated_current"])
    healthy_counts = healthy.groupby(df["scb_id"]).sum()

    ratio = df.loc[healthy, ["scb_id", "dc_current_a", "irr"]].copy()
    ratio["r"] = ratio["dc_current_a"] / ratio["irr"]
    ratio = ratio.replace([np.inf, -np.inf], np.nan).dropna(subset=["r"])
    k_per_scb = ratio[ratio["r"] > 0].groupby("scb_id")["r"].median()

    keep = [s for s in df["scb_id"].unique() if healthy_counts.get(s, 0) >= 10 and k_per_scb.get(s, 0) > 0]
    if not keep:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "Not enough healthy samples to calibrate a reference current curve for any SCB/MPPT.")

    df = df[df["scb_id"].isin(keep)].copy()
    df["k"] = df["scb_id"].map(k_per_scb)
    df["i_virtual"] = df["k"] * df["irr"]
    df["gap_a"] = (df["i_virtual"] - df["dc_current_a"]).clip(lower=0.0)

    saturated = (df["irr"] >= irr_min) & (df["dc_current_a"] >= hit_ratio * df["rated_current"]) & (df["gap_a"] > 0.05 * df["rated_current"])
    is_clip = _grouped_persistence(saturated, df["scb_id"], persist_min)

    voltage = df["dc_voltage_v"].fillna(df.groupby("scb_id")["dc_voltage_v"].transform("median")).fillna(600.0)
    df["loss_step_kwh"] = np.where(is_clip, (df["gap_a"] * voltage / 1000.0) * df["dt_h"], 0.0)
    df["is_clip"] = is_clip

    per_scb = df.groupby("scb_id").agg(loss_kwh=("loss_step_kwh", "sum"), clip_points=("is_clip", "sum")).reset_index()
    per_scb = per_scb[per_scb["clip_points"] > 0].sort_values("loss_kwh", ascending=False)

    if per_scb.empty:
        return ResultObject(
            algorithm_id=ALGORITHM_ID,
            algorithm_version=VERSION,
            status=ResultStatus.OK,
            title="Inverter Clipping by Current (v1)",
            summary="Current clipping module ran - no SCB/MPPT showed sustained DC current saturation in this period.",

            severity="info",
            confidence=0.6,
            metrics={"clipped_equipment_count": 0.0},
            recommendations=["No DC current clipping events detected under the configured thresholds."],
            thresholds_used={"current_limit_hit_ratio": hit_ratio, "irradiance_min_w_m2": irr_min, "persist_min_samples": float(persist_min)},
            evidence=EvidenceRef(
                source_fields=["dc_current_a", "poa_w_m2", "ghi_w_m2"],
                total_sample_count=int(len(df)),
            ),
        )

    total_loss = float(per_scb["loss_kwh"].sum())
    events = df[df["is_clip"]].copy()
    events["hour"] = events["timestamp_utc"].dt.floor("h")
    hourly = events.groupby("hour")["loss_step_kwh"].sum().reset_index()

    charts = [bar_chart("clipping_current_loss_by_scb", "Current Clipping Loss by SCB/MPPT", per_scb["scb_id"].tolist(), per_scb["loss_kwh"].round(3).tolist(), y_title="Loss (kWh)", color="#7c3aed")]
    if not hourly.empty:
        charts.append(line_chart("clipping_current_trend", "DC Current Clipping Loss Trend", hourly["hour"].dt.strftime("%Y-%m-%d %H:%M").tolist(), {"Loss (kWh)": hourly["loss_step_kwh"].round(3).tolist()}, y_title="Loss (kWh)"))

    table = ResultTable(
        title="DC current clipping by SCB/MPPT",
        columns=["SCB/MPPT", "Loss (kWh)", "Saturated samples"],
        rows=[[r.scb_id, round(r.loss_kwh, 3), int(r.clip_points)] for r in per_scb.itertuples()],
    )

    return ResultObject(
        algorithm_id=ALGORITHM_ID,
        algorithm_version=VERSION,
        status=ResultStatus.OK,
        title="Inverter Clipping by Current (v1)",
        summary=f"{len(per_scb)} SCB/MPPT unit(s) show sustained DC current saturation totaling {total_loss:.2f} kWh. This is a v1 algorithm — validate against real plant data.",
        severity="medium" if total_loss > 0 else "info",
        confidence=0.6,
        affected_equipment=per_scb["scb_id"].tolist(),
        loss_energy_kwh=round(total_loss, 3),
        metrics={"clipped_equipment_count": float(len(per_scb))},
        tables=[table],
        charts=charts,
        recommendations=[
            "This is a v1 algorithm with no production baseline yet — treat magnitudes as directional until validated against real plant data.",
            "Sustained DC current saturation near the string/MPPT rating can indicate an undersized MPPT channel relative to installed strings, or high-irradiance/low-temperature conditions pushing Isc above design assumptions.",
        ],
        thresholds_used={"current_limit_hit_ratio": hit_ratio, "irradiance_min_w_m2": irr_min, "persist_min_samples": float(persist_min)},
        evidence=EvidenceRef(
            equipment_ids=per_scb["scb_id"].tolist(),
            time_range_start=str(df["timestamp_utc"].min()),
            time_range_end=str(df["timestamp_utc"].max()),
            source_fields=["dc_current_a", "poa_w_m2", "ghi_w_m2"],
            affected_sample_count=int(df["is_clip"].sum()),
            total_sample_count=int(len(df)),
        ),
    )
