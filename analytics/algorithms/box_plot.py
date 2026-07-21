"""Box plot analysis — inverter efficiency distribution.

Extracted as a first-class algorithm/result module (PRD gap fix #3: in PIC this lived
embedded inside the inverter-efficiency payload as `inverter_box_stats`; PIC Lite promotes
it to its own dashboard fault card / result object so the mapping to PRD §7.10 is 1:1).
Reuses analytics.algorithms.inverter_efficiency.compute_efficiency_frame so both modules
agree on the same underlying per-sample efficiency values.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.algorithms.inverter_efficiency import compute_efficiency_frame
from analytics.charts.builders import box_plot_chart
from analytics.core.context import AnalysisContext
from analytics.core.registry import register_algorithm
from analytics.core.result import EvidenceRef, ResultObject, ResultStatus, ResultTable

ALGORITHM_ID = "box_plot"
VERSION = "1.0.0-port"


def _box_stats(series: pd.Series, clamp_min: float, clamp_max: float) -> dict[str, float] | None:
    arr = series.dropna()
    arr = arr[(arr >= clamp_min) & (arr <= clamp_max)]
    if arr.empty:
        return None
    return {
        "min": float(round(np.min(arr), 2)),
        "q1": float(round(np.nanpercentile(arr, 25), 2)),
        "median": float(round(np.median(arr), 2)),
        "q3": float(round(np.nanpercentile(arr, 75), 2)),
        "max": float(round(np.max(arr), 2)),
    }


@register_algorithm(ALGORITHM_ID, VERSION, required_fields=("ac_power_kw", "dc_power_kw"))
def run(context: AnalysisContext) -> ResultObject:
    thresholds = context.threshold_group(ALGORITHM_ID)
    clamp_min = thresholds.get("efficiency_clamp_min_pct", 0.0)
    clamp_max = thresholds.get("efficiency_clamp_max_pct", 200.0)

    ef = compute_efficiency_frame(context)
    if ef.df_valid.empty:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "No valid DC/AC samples to build an efficiency distribution.")

    df_valid = ef.df_valid
    # Build stats explicitly — groupby.apply(dict) expands into a MultiIndex float Series
    # on modern pandas, so **stats unpacking would crash with TypeError.
    stats_list: list[dict[str, float | str]] = []
    for inv_id, series in df_valid.groupby("inverter_id", sort=True)["eff_pct"]:
        stats = _box_stats(series, clamp_min, clamp_max)
        if stats is None:
            continue
        stats_list.append({"name": str(inv_id), **stats})
    if not stats_list:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "No inverter had enough valid samples for a distribution.")

    outliers = [
        str(s["name"])
        for s in stats_list
        if (s["q3"] - s["q1"]) > 0 and (s["median"] < (s["q1"] - 1.5 * (s["q3"] - s["q1"])))
    ]

    # Pass clamped samples so Plotly draws real boxes (precomputed-only traces were blank).
    samples_by_name: dict[str, list[float]] = {}
    for inv_id, series in df_valid.groupby("inverter_id", sort=True)["eff_pct"]:
        arr = series.dropna()
        arr = arr[(arr >= clamp_min) & (arr <= clamp_max)]
        if arr.empty:
            continue
        samples_by_name[str(inv_id)] = [float(v) for v in arr.tolist()]

    chart = box_plot_chart(
        "efficiency_box_plot",
        "Inverter Efficiency Distribution (Box Plot)",
        stats_list,
        samples_by_name=samples_by_name,
    )
    table = ResultTable(
        title="Efficiency distribution per inverter",
        columns=["Inverter", "Min", "Q1", "Median", "Q3", "Max"],
        rows=[[s["name"], s["min"], s["q1"], s["median"], s["q3"], s["max"]] for s in stats_list],
    )

    recommendations = []
    if outliers:
        recommendations.append(
            f"{len(outliers)} inverter(s) show a low-median efficiency distribution with wide spread "
            f"({', '.join(outliers[:5])}) — investigate for intermittent underperformance."
        )
    else:
        recommendations.append("Efficiency distributions are tight and consistent across inverters — no distributional outliers detected.")

    return ResultObject(
        algorithm_id=ALGORITHM_ID,
        algorithm_version=VERSION,
        status=ResultStatus.OK,
        title="Box Plot Analysis",
        summary=f"Efficiency distributions computed for {len(stats_list)} inverter(s); {len(outliers)} show outlier spread.",
        severity="medium" if outliers else "info",
        confidence=0.85,
        affected_equipment=outliers,
        loss_energy_kwh=None,
        metrics={"inverters_analyzed": float(len(stats_list)), "outlier_count": float(len(outliers))},
        tables=[table],
        charts=[chart],
        recommendations=recommendations,
        thresholds_used={"efficiency_clamp_min_pct": clamp_min, "efficiency_clamp_max_pct": clamp_max},
        evidence=EvidenceRef(
            equipment_ids=[str(s["name"]) for s in stats_list],
            time_range_start=str(df_valid["timestamp_utc"].min()),
            time_range_end=str(df_valid["timestamp_utc"].max()),
            source_fields=["ac_power_kw", "dc_power_kw"],
            affected_sample_count=int(len(df_valid)),
            total_sample_count=int(len(df_valid)),
        ),
    )
