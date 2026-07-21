"""String outlier detection.

Promoted (PRD gap fix #2) from PIC's backend/modules/fault_diagnostics/fault_engine.py
placeholder rules `low_current_fault` and `scb_unbalance`, which in PIC were snapshot-only
(no persistence filter) and operated on a generic long-format frame. PIC Lite makes this a
first-class, configurable algorithm, separate from disconnected-string detection (§7.8),
with a persistence filter so single-sample sensor noise does not get reported as an outlier.

Runs at string-level current when available; falls back to SCB-level current compared
within its parent inverter when the upload has no per-string telemetry.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.charts.builders import bar_chart
from analytics.core.context import AnalysisContext
from analytics.core.registry import register_algorithm
from analytics.core.result import EvidenceRef, ResultObject, ResultStatus, ResultTable

ALGORITHM_ID = "string_outlier"
VERSION = "1.0.0-promoted"


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
    low_current_frac = t.get("low_current_fraction_of_median", 0.5)
    imbalance_frac = t.get("scb_imbalance_fraction", 0.3)
    min_persist = int(t.get("min_persist_samples", 3))

    df = context.canonical.frame(columns=["timestamp_utc", "device_type", "string_id", "scb_id", "inverter_id", "dc_current_a", "dc_voltage_v"])
    string_df = df[(df["device_type"] == "string") & df["string_id"].notna()].copy()

    if not string_df.empty:
        group_col = "scb_id"
        unit_col = "string_id"
        working = string_df
    else:
        working = df[(df["device_type"] == "scb") & df["scb_id"].notna()].copy()
        group_col = "inverter_id"
        unit_col = "scb_id"

    working["dc_current_a"] = pd.to_numeric(working["dc_current_a"], errors="coerce")
    working = working.dropna(subset=["dc_current_a", group_col, unit_col])
    if working.empty:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "No string- or SCB-level current telemetry with a resolvable group was found.")

    group_median = working.groupby(["timestamp_utc", group_col])["dc_current_a"].median().rename("group_median").reset_index()
    working = working.merge(group_median, on=["timestamp_utc", group_col], how="left")
    working["deviation_frac"] = np.where(working["group_median"] > 0, (working["dc_current_a"] - working["group_median"]).abs() / working["group_median"], 0.0)

    is_low = (working["group_median"] > 0) & (working["dc_current_a"] < low_current_frac * working["group_median"])
    is_imbalanced = working["deviation_frac"] > imbalance_frac
    flagged = is_low | is_imbalanced

    working["flagged"] = _grouped_persistence(flagged, working[unit_col], min_persist)
    confirmed = working[working["flagged"]]
    if confirmed.empty:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "No unit showed a sustained current outlier relative to its group.")

    dt_h = context.sample_interval_minutes / 60.0
    voltage = pd.to_numeric(confirmed["dc_voltage_v"], errors="coerce").fillna(600.0)
    gap = np.maximum(0.0, confirmed["group_median"] - confirmed["dc_current_a"])
    loss_kwh_step = (gap * voltage / 1000.0) * dt_h

    per_unit = pd.DataFrame({unit_col: confirmed[unit_col], "loss_kwh": loss_kwh_step, "flag_points": 1})
    per_unit = per_unit.groupby(unit_col).agg(loss_kwh=("loss_kwh", "sum"), flag_points=("flag_points", "sum")).reset_index().sort_values("loss_kwh", ascending=False)

    total_loss = float(per_unit["loss_kwh"].sum())

    chart = bar_chart("string_outlier_loss", f"Outlier Loss by {unit_col.replace('_', ' ').title()}", per_unit[unit_col].tolist(), per_unit["loss_kwh"].round(3).tolist(), color="#0891b2")
    table = ResultTable(
        title=f"Outlier {unit_col.replace('_', ' ')}s",
        columns=[unit_col.replace("_", " ").title(), "Estimated loss (kWh)", "Flagged samples"],
        rows=[[getattr(r, unit_col), round(r.loss_kwh, 3), int(r.flag_points)] for r in per_unit.itertuples()],
    )

    return ResultObject(
        algorithm_id=ALGORITHM_ID,
        algorithm_version=VERSION,
        status=ResultStatus.OK,
        title="String Outlier Detection",
        summary=f"{len(per_unit)} {unit_col.replace('_', ' ')}(s) show sustained current deviation from their group, totaling an estimated {total_loss:.2f} kWh.",
        severity="medium" if total_loss > 0 else "low",
        confidence=0.7,
        affected_equipment=per_unit[unit_col].tolist(),
        loss_energy_kwh=round(total_loss, 3),
        metrics={"affected_unit_count": float(len(per_unit)), "granularity": 1.0 if unit_col == "string_id" else 0.0},
        tables=[table],
        charts=[chart],
        recommendations=[
            f"Loss estimates here are a proxy (deviation from the group median), not a confirmed-fault energy balance like disconnected-string detection — use as a triage list for field inspection: {', '.join(per_unit[unit_col].head(5).astype(str))}.",
        ],
        thresholds_used={"low_current_fraction_of_median": low_current_frac, "scb_imbalance_fraction": imbalance_frac, "min_persist_samples": float(min_persist)},
        evidence=EvidenceRef(
            equipment_ids=per_unit[unit_col].tolist(),
            time_range_start=str(confirmed["timestamp_utc"].min()),
            time_range_end=str(confirmed["timestamp_utc"].max()),
            source_fields=["dc_current_a"],
            affected_sample_count=int(len(confirmed)),
            total_sample_count=int(len(working)),
        ),
    )
