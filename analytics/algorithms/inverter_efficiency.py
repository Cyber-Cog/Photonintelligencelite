"""Inverter efficiency loss.

Ported (formulas only) from PIC's
backend/routers/faults.py::_compute_inverter_efficiency_analysis_payload.

Efficiency (%) = AC power / DC power x 100, computed only on samples where DC > AC (a
physically valid efficiency point). Loss (kWh) = (DC - AC) x dt_h, summed per inverter.
`compute_efficiency_frame` is shared with analytics/algorithms/box_plot.py so both
algorithms use identical underlying per-sample efficiency values (see docs/algorithm_parity.md).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from analytics.charts.builders import bar_chart, line_chart
from analytics.core.context import AnalysisContext
from analytics.core.registry import register_algorithm
from analytics.core.result import EvidenceRef, ResultObject, ResultStatus, ResultTable

ALGORITHM_ID = "inverter_efficiency"
VERSION = "1.0.0-port"


@dataclass
class EfficiencyFrame:
    df_valid: pd.DataFrame
    dt_h: float
    dc_synthesized: bool = False
    """True when at least one inverter's DC power was derived from child SCB I×V (PIC fallback)."""


def _synthesize_dc_from_scb(context: AnalysisContext) -> pd.DataFrame | None:
    """Derive inverter DC power from the sum of child-SCB (I × V / 1000) per timestamp.

    Ported (formula only) from PIC's
    ``faults.py::_compute_inverter_efficiency_analysis_payload`` SCB fallback block:
    ``Pdc = ΣI_scb × avg(V_scb) / 1000`` grouped by (timestamp, parent inverter), with a
    dummy 1000 V assumed when SCB voltage telemetry is absent. Used only where an inverter
    has no native ``dc_power_kw`` at that timestamp.
    """
    scb = context.canonical.frame(
        columns=["timestamp_utc", "device_type", "inverter_id", "dc_current_a", "dc_voltage_v"]
    )
    scb = scb[scb["device_type"] == "scb"].dropna(subset=["inverter_id"])
    if scb.empty:
        return None
    scb["dc_current_a"] = pd.to_numeric(scb["dc_current_a"], errors="coerce")
    scb["dc_voltage_v"] = pd.to_numeric(scb["dc_voltage_v"], errors="coerce")
    scb = scb.dropna(subset=["dc_current_a"])
    if scb.empty:
        return None
    grp = (
        scb.groupby(["timestamp_utc", "inverter_id"])
        .agg(total_scb_curr=("dc_current_a", "sum"), avg_scb_volt=("dc_voltage_v", "mean"))
        .reset_index()
    )
    grp["avg_scb_volt"] = grp["avg_scb_volt"].fillna(1000.0)  # PIC dummy 1000 V when voltage missing
    grp["dc_from_scb_kw"] = grp["total_scb_curr"] * grp["avg_scb_volt"] / 1000.0
    grp = grp[grp["dc_from_scb_kw"] > 0]
    if grp.empty:
        return None
    return grp[["timestamp_utc", "inverter_id", "dc_from_scb_kw"]]


def compute_efficiency_frame(context: AnalysisContext) -> EfficiencyFrame:
    df = context.canonical.frame(columns=["timestamp_utc", "device_type", "inverter_id", "ac_power_kw", "dc_power_kw"])
    df = df[df["device_type"] == "inverter"].dropna(subset=["inverter_id"]).copy()
    df["ac_power_kw"] = pd.to_numeric(df["ac_power_kw"], errors="coerce").fillna(0.0)
    df["dc_power_kw"] = pd.to_numeric(df["dc_power_kw"], errors="coerce").fillna(0.0)

    dt_h = context.sample_interval_minutes / 60.0

    # PIC parity: derive DC from child SCB I×V wherever inverter DC telemetry is absent/zero.
    dc_synthesized = False
    if df.empty or (df["dc_power_kw"] <= 0).any():
        scb_dc = _synthesize_dc_from_scb(context)
        if scb_dc is not None and not scb_dc.empty:
            if df.empty:
                # No inverter rows carry DC — still allow efficiency if AC exists elsewhere.
                df = df.merge(scb_dc, on=["timestamp_utc", "inverter_id"], how="outer")
                df["ac_power_kw"] = pd.to_numeric(df.get("ac_power_kw"), errors="coerce").fillna(0.0)
                df["dc_power_kw"] = pd.to_numeric(df.get("dc_power_kw"), errors="coerce").fillna(0.0)
            else:
                df = df.merge(scb_dc, on=["timestamp_utc", "inverter_id"], how="left")
            need = (df["dc_power_kw"] <= 0) & (df["dc_from_scb_kw"].fillna(0.0) > 0)
            if need.any():
                df.loc[need, "dc_power_kw"] = df.loc[need, "dc_from_scb_kw"]
                dc_synthesized = True
            df = df.drop(columns=[c for c in ("dc_from_scb_kw",) if c in df.columns])

    df_valid = df[df["dc_power_kw"] > df["ac_power_kw"]].copy()
    if df_valid.empty:
        return EfficiencyFrame(df_valid, dt_h, dc_synthesized)

    df_valid["eff_pct"] = np.where(
        df_valid["dc_power_kw"] > 0,
        (df_valid["ac_power_kw"] / df_valid["dc_power_kw"]) * 100.0,
        np.nan,
    )
    df_valid["loss_kwh"] = (df_valid["dc_power_kw"] - df_valid["ac_power_kw"]) * dt_h
    df_valid["dc_kwh"] = df_valid["dc_power_kw"] * dt_h
    df_valid["ac_kwh"] = df_valid["ac_power_kw"] * dt_h
    return EfficiencyFrame(df_valid, dt_h, dc_synthesized)


@register_algorithm(ALGORITHM_ID, VERSION, required_fields=("ac_power_kw", "dc_power_kw"))
def run(context: AnalysisContext) -> ResultObject:
    thresholds = context.threshold_group(ALGORITHM_ID)
    target_default = thresholds.get("default_target_efficiency_pct", 98.5)

    ef = compute_efficiency_frame(context)
    if ef.df_valid.empty:
        return ResultObject.unavailable(
            ALGORITHM_ID, VERSION, "No samples found where DC power exceeds AC power — efficiency cannot be computed."
        )

    df_valid = ef.df_valid
    inv_grp = df_valid.groupby("inverter_id").agg(dc_kwh=("dc_kwh", "sum"), ac_kwh=("ac_kwh", "sum"), loss_kwh=("loss_kwh", "sum")).reset_index()
    inv_grp["efficiency_pct"] = (inv_grp["ac_kwh"] / inv_grp["dc_kwh"]).replace([np.inf, -np.inf], np.nan) * 100
    inv_grp = inv_grp.fillna(0).sort_values("loss_kwh", ascending=False)

    total_dc_kwh = float(inv_grp["dc_kwh"].sum())
    total_ac_kwh = float(inv_grp["ac_kwh"].sum())
    total_loss_kwh = float(inv_grp["loss_kwh"].sum())
    avg_eff = (total_ac_kwh / total_dc_kwh * 100.0) if total_dc_kwh > 0 else 0.0

    hourly = df_valid.copy()
    hourly["hour"] = hourly["timestamp_utc"].dt.floor("h")
    trend = hourly.groupby("hour").agg(dc_kwh=("dc_kwh", "sum"), ac_kwh=("ac_kwh", "sum")).reset_index()
    trend["efficiency_pct"] = (trend["ac_kwh"] / trend["dc_kwh"]).replace([np.inf, -np.inf], np.nan) * 100
    trend = trend.fillna(0)

    charts = [
        line_chart(
            "inverter_efficiency_trend",
            "Inverter Efficiency Trend",
            trend["hour"].dt.strftime("%Y-%m-%d %H:%M").tolist(),
            {"Actual Efficiency (%)": trend["efficiency_pct"].round(2).tolist(), "Target (%)": [round(target_default, 1)] * len(trend)},
            y_title="Efficiency (%)",
        ),
        bar_chart(
            "inverter_efficiency_loss_by_inverter",
            "Energy Loss by Inverter",
            inv_grp["inverter_id"].tolist(),
            inv_grp["loss_kwh"].round(2).tolist(),
            y_title="Loss (kWh)",
            color="#dc2626",
        ),
    ]

    table = ResultTable(
        title="Per-inverter efficiency",
        columns=["Inverter", "DC Energy (kWh)", "AC Energy (kWh)", "Loss (kWh)", "Efficiency (%)"],
        rows=[
            [r.inverter_id, round(r.dc_kwh, 1), round(r.ac_kwh, 1), round(r.loss_kwh, 1), round(r.efficiency_pct, 2)]
            for r in inv_grp.itertuples()
        ],
    )

    worst = inv_grp.iloc[0] if len(inv_grp) else None
    recommendations = []
    if worst is not None and worst.efficiency_pct < target_default - 2:
        recommendations.append(
            f"Inspect {worst.inverter_id}: efficiency {worst.efficiency_pct:.1f}% is below the "
            f"{target_default:.1f}% target and accounts for the largest single share of loss."
        )
    recommendations.append("Efficiency loss values below the target band typically indicate thermal derating, aging DC components, or MPPT tracking error — cross-check against ambient/module temperature.")

    severity = "high" if avg_eff < target_default - 3 else ("medium" if avg_eff < target_default - 1 else "low")

    summary = (
        f"Average inverter efficiency is {avg_eff:.2f}% against a {target_default:.1f}% target, "
        f"representing {total_loss_kwh:.1f} kWh of loss."
    )
    if ef.dc_synthesized:
        summary += " DC power was derived from SCB current × voltage where inverter DC telemetry was missing."
        recommendations.append(
            "DC power for one or more inverters was reconstructed from child-SCB current × voltage "
            "(no native DC telemetry) — efficiency for those inverters is an estimate."
        )

    return ResultObject(
        algorithm_id=ALGORITHM_ID,
        algorithm_version=VERSION,
        status=ResultStatus.OK,
        title="Inverter Efficiency Loss",
        summary=summary,
        severity=severity,
        confidence=0.9,
        affected_equipment=inv_grp.loc[inv_grp["loss_kwh"] > 0, "inverter_id"].tolist(),
        loss_energy_kwh=round(total_loss_kwh, 2),
        metrics={
            "total_dc_energy_kwh": round(total_dc_kwh, 2),
            "total_ac_energy_kwh": round(total_ac_kwh, 2),
            "average_efficiency_pct": round(avg_eff, 2),
            "target_efficiency_pct": round(target_default, 1),
        },
        tables=[table],
        charts=charts,
        recommendations=recommendations,
        thresholds_used={"default_target_efficiency_pct": target_default},
        evidence=EvidenceRef(
            equipment_ids=inv_grp["inverter_id"].tolist(),
            time_range_start=str(df_valid["timestamp_utc"].min()),
            time_range_end=str(df_valid["timestamp_utc"].max()),
            source_fields=["ac_power_kw", "dc_power_kw"],
            affected_sample_count=int(len(df_valid)),
            total_sample_count=int(len(df_valid)),
        ),
    )
