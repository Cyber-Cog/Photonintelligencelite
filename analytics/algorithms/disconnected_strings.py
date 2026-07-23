"""Disconnected String (DS) detection.

Ported (formulas only) from PIC's backend/engine/ds_detection.py `run_ds_detection`, with
all SQLAlchemy/session/DB-write code removed and every input (architecture, irradiance)
resolved from the shared AnalysisContext/canonical data instead of ad-hoc SQL. The
MPPT-specific comparison branch (keyed off a hardcoded plant-name string in PIC) is not
ported — PIC Lite only implements the SCB central-inverter comparison path; see
docs/algorithm_parity.md for this and other documented simplifications.

Pipeline (unchanged order from the source engine):
  1. Resolve architecture (strings_per_scb) from plant config.
  2. Leakage-current removal on unfiltered data (low irradiance + high current all day).
  3. Irradiance/time-of-day gate.
  4. Outlier removal (current < 0 or > Isc_stc x strings).
  5. Near-constant value removal (frozen SCB-day).
  6. Normalize to per-string current; build a virtual reference (top-quartile SCBs per
     inverter+timestamp).
  7. Candidate detection: relative current drop vs reference.
  8. Persistence window (>= configured minutes) -> confirmed fault.
  9. Energy loss = V x I_missing integrated with per-sample dt.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.charts.builders import bar_chart, diagnostic_line_chart, timeline_chart
from analytics.common.irradiance import extract_irradiance_frame
from analytics.core.context import AnalysisContext
from analytics.core.registry import register_algorithm
from analytics.core.result import EvidenceRef, ResultObject, ResultStatus, ResultTable

ALGORITHM_ID = "disconnected_strings"
VERSION = "1.0.0-port"


def _smooth_measurements(df: pd.DataFrame, window: int) -> pd.DataFrame:
    """Per-SCB centered rolling-median smoothing of current/voltage (PIC Step 5b).

    Ported from PIC ``ds_detection.py::_smooth_measurements`` — kills single-sample sensor
    spikes/dropouts before persistence detection so transient noise is not confirmed as a
    disconnected string. ``window <= 1`` is a no-op.
    """
    if df.empty or window <= 1:
        return df
    df = df.sort_values(["scb_id", "timestamp_utc"]).copy()
    for col in ("dc_current_a", "dc_voltage_v"):
        if col not in df.columns:
            continue
        med = df.groupby("scb_id", sort=False)[col].transform(
            lambda s: s.rolling(window=window, min_periods=1, center=True).median()
        )
        df[col] = pd.to_numeric(med, errors="coerce")
    return df


def _virtual_reference(group: pd.Series, top_percentile: float) -> float:
    vals = group.to_numpy(dtype=float)
    vals = vals[np.isfinite(vals) & (vals > 0)]
    if vals.size == 0:
        return np.nan
    vals.sort()
    top_n = max(1, int(np.ceil(vals.size * top_percentile)))
    return float(np.median(vals[-top_n:]))


@register_algorithm(ALGORITHM_ID, VERSION, required_fields=("dc_current_a",))
def run(context: AnalysisContext) -> ResultObject:
    t = context.threshold_group(ALGORITHM_ID)
    irr_min = t.get("irradiance_min_w_m2", 150.0)
    irr_max = t.get("irradiance_max_w_m2", 1200.0)
    leak_irr_max = t.get("leakage_irradiance_max_w_m2", 200.0)
    leak_curr_min = t.get("leakage_current_min_a", 20.0)
    isc_stc = t.get("isc_stc_a", 10.0)
    top_pct = t.get("top_percentile", 0.25)
    const_tol = t.get("const_delta_tolerance", 0.01)
    const_flat_ratio_min = t.get("const_flat_ratio_min", 0.995)
    const_unique_max = int(t.get("const_unique_max", 3))
    persistence_minutes = t.get("persistence_minutes", 360)
    drop_pct = t.get("current_drop_pct", 0.30)
    compare_ratio = max(0.0, min(1.0, 1.0 - drop_pct))
    missing_tolerance = t.get("missing_string_tolerance", 0.85)
    energy_v_min = t.get("energy_voltage_min_v", 50.0)
    min_dt_sec = t.get("min_energy_dt_sec", 30)
    max_dt_sec = t.get("max_energy_dt_sec", 900)
    rolling_median_window = int(t.get("rolling_median_window", 5))

    df = context.canonical.frame(columns=["timestamp_utc", "device_type", "inverter_id", "scb_id", "dc_current_a", "dc_voltage_v"])
    df = df[df["device_type"] == "scb"].dropna(subset=["scb_id", "dc_current_a"]).copy()
    if df.empty:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "No SCB-level DC current telemetry was found.")

    # Backfill parent inverter from architecture for standalone SMB/SCB equipment ids.
    missing_inv = df["inverter_id"].isna()
    if missing_inv.any() and context.plant.architecture:
        from analytics.common.equipment_ids import resolve_inverter_from_architecture

        df.loc[missing_inv, "inverter_id"] = df.loc[missing_inv, "scb_id"].map(
            lambda sid: resolve_inverter_from_architecture(sid, context.plant.architecture)
        )
    df = df.dropna(subset=["inverter_id"]).copy()
    if df.empty:
        return ResultObject.unavailable(
            ALGORITHM_ID,
            VERSION,
            "No SCB-level DC current telemetry with a resolved inverter parent was found. "
            "Map SMB/SCB current and provide plant architecture (SMB → inverter).",
        )

    # Spare SCB support (PIC parity): SCBs flagged spare in architecture do not carry live
    # strings, so excluding them prevents them being flagged as "disconnected".
    spare_scbs = {sid for sid, a in context.plant.architecture.items() if a.get("spare_flag")}
    if spare_scbs:
        df = df[~df["scb_id"].isin(spare_scbs)].copy()
        if df.empty:
            return ResultObject.unavailable(ALGORITHM_ID, VERSION, "All SCBs with current telemetry are marked as spare in the architecture.")

    df["dc_current_a"] = pd.to_numeric(df["dc_current_a"], errors="coerce")
    df["dc_voltage_v"] = pd.to_numeric(df.get("dc_voltage_v"), errors="coerce")
    df = df.dropna(subset=["dc_current_a"])
    if df.empty:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "SCB current values could not be parsed as numeric.")

    def string_count(scb_id: str) -> int:
        arch = context.plant.architecture.get(scb_id, {})
        return int(arch.get("strings_per_scb") or context.plant.strings_per_scb or 8)

    df["string_count"] = df["scb_id"].map(string_count)
    df = df[df["string_count"] > 0]
    total_rows_pre_filter = len(df)

    irr_frame = extract_irradiance_frame(context)
    irr_map: dict = {}
    if not irr_frame.empty:
        irr_map = irr_frame.set_index("timestamp_utc")["irr_val"].to_dict()

    # ── Leakage detection on unfiltered data ────────────────────────────────
    if irr_map:
        df["_irr"] = df["timestamp_utc"].map(irr_map)
        df["_day"] = df["timestamp_utc"].dt.date
        leakage_keys: set = set()
        for (scb_id, day), g in df.groupby(["scb_id", "_day"], sort=False):
            irr_vals = g["_irr"].dropna()
            if irr_vals.empty:
                continue
            if (irr_vals < leak_irr_max).all() and (g["dc_current_a"] > leak_curr_min).all():
                leakage_keys.add((scb_id, day))
        if leakage_keys:
            mask = pd.Series(list(zip(df["scb_id"], df["_day"]))).isin(leakage_keys).values
            df = df[~mask].copy()

    # ── Irradiance / time-of-day gate ───────────────────────────────────────
    if irr_map:
        df["_irr"] = df["timestamp_utc"].map(irr_map)
        df = df[df["_irr"].notna() & (df["_irr"] >= irr_min) & (df["_irr"] <= irr_max)].copy()
    else:
        # Local solar hours (timestamp_utc is UTC; use the plant timezone so the 10–16
        # daytime window is not shifted by the UTC offset).
        ts = pd.to_datetime(df["timestamp_utc"], errors="coerce")
        try:
            if getattr(ts.dt, "tz", None) is None:
                ts = ts.dt.tz_localize("UTC")
            hour = ts.dt.tz_convert(context.timezone).dt.hour
        except Exception:
            hour = ts.dt.hour
        df = df[(hour >= 10) & (hour <= 16)].copy()

    if df.empty:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "No SCB samples remained after the irradiance/time-of-day operating filter.")

    # ── Outlier removal (per timestamp) ─────────────────────────────────────
    outlier_mask = (~np.isfinite(df["dc_current_a"])) | (df["dc_current_a"] < 0) | (df["dc_current_a"] > isc_stc * df["string_count"])
    df = df[~outlier_mask].copy()
    if df.empty:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "All SCB samples were rejected as physically implausible outliers.")

    # ── Step 5b — Rolling-median smoothing (PIC parity) ─────────────────────
    df = _smooth_measurements(df, rolling_median_window)
    df = df.dropna(subset=["dc_current_a"])
    if df.empty:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "No SCB samples remained after rolling-median smoothing.")

    # ── Near-constant (frozen) SCB-day removal ──────────────────────────────
    df = df.sort_values(["scb_id", "timestamp_utc"]).reset_index(drop=True)
    df["_day"] = df["timestamp_utc"].dt.date
    frozen: set = set()
    for (scb_id, day), g in df.groupby(["scb_id", "_day"], sort=False):
        vals = g.sort_values("timestamp_utc")["dc_current_a"].to_numpy()
        if vals.size < 2:
            continue
        diffs = np.abs(np.diff(vals))
        flat_ratio = float(np.mean(diffs < const_tol))
        uniq = int(pd.Series(vals).nunique())
        if flat_ratio >= const_flat_ratio_min and uniq <= const_unique_max:
            frozen.add((scb_id, day))
    if frozen:
        mask = pd.Series(list(zip(df["scb_id"], df["_day"]))).isin(frozen).values
        df = df[~mask].copy()
    df = df.drop(columns=[c for c in ("_day", "_irr") if c in df.columns])
    if df.empty:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "No SCB-day remained after removing frozen/flat sensor readings.")

    # ── Normalize + virtual reference per inverter+timestamp ───────────────
    df["per_string_current"] = df["dc_current_a"] / df["string_count"]
    ref = df.groupby(["timestamp_utc", "inverter_id"])["per_string_current"].apply(lambda s: _virtual_reference(s, top_pct))
    ref_df = ref.reset_index().rename(columns={"per_string_current": "ref_current"})
    df = df.merge(ref_df, on=["timestamp_utc", "inverter_id"], how="left")
    df = df[np.isfinite(df["ref_current"]) & (df["ref_current"] > 0)].copy()
    if df.empty:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "Could not build a reference current curve for any inverter+timestamp group.")

    # ── Candidate + persistence + energy loss ───────────────────────────────
    df["expected_scb_current"] = df["ref_current"] * df["string_count"]
    df["missing_current"] = np.maximum(0.0, df["expected_scb_current"] - df["dc_current_a"])
    df["missing_ratio"] = np.where(df["ref_current"] > 0, df["missing_current"] / df["ref_current"], 0.0)
    df["candidate"] = (df["missing_ratio"] >= missing_tolerance) & (df["dc_current_a"] < df["expected_scb_current"])
    df["missing_strings"] = np.where(df["candidate"], np.maximum(1, np.floor(df["missing_ratio"] + (1.0 - missing_tolerance)).astype(int)), 0)

    df = df.sort_values(["scb_id", "timestamp_utc"]).reset_index(drop=True)
    n = len(df)
    ts_epoch = df["timestamp_utc"].astype("int64").to_numpy() // 10**9
    scb_arr = df["scb_id"].to_numpy()
    candidate_arr = df["candidate"].to_numpy()
    missing_current_arr = df["missing_current"].to_numpy(dtype=float)
    voltage_arr = pd.to_numeric(df["dc_voltage_v"], errors="coerce").to_numpy(dtype=float)
    missing_strings_arr = df["missing_strings"].to_numpy()

    persistence_seconds = persistence_minutes * 60
    consecutive_tol_sec = max(90, int(context.sample_interval_minutes * 60 * 1.5))
    fault_flag = np.zeros(n, dtype=bool)
    energy_loss = np.zeros(n, dtype=float)
    confirmed_missing = np.zeros(n, dtype=int)

    peer_voltage = df.groupby(["timestamp_utc", "inverter_id"])["dc_voltage_v"].transform(
        lambda s: float(np.nanmedian(pd.to_numeric(s, errors="coerce"))) if s.notna().any() else np.nan
    ).to_numpy(dtype=float)

    scb_change = np.concatenate([[True], scb_arr[1:] != scb_arr[:-1]])
    starts = np.where(scb_change)[0]
    ends = np.concatenate([starts[1:], [n]])

    for si, ei in zip(starts, ends):
        i = si
        while i < ei:
            if not candidate_arr[i]:
                i += 1
                continue
            run_start = i
            run_end = i + 1
            while run_end < ei and candidate_arr[run_end]:
                gap = int(ts_epoch[run_end]) - int(ts_epoch[run_end - 1])
                if not (0 < gap <= consecutive_tol_sec):
                    break
                run_end += 1

            elapsed = int(ts_epoch[run_end - 1]) - int(ts_epoch[run_start])
            if elapsed >= persistence_seconds:
                win_min = int(np.min(missing_strings_arr[run_start:run_end]))
                for j in range(run_start, run_end):
                    fault_flag[j] = True
                    confirmed_missing[j] = win_min
                    v = voltage_arr[j] if np.isfinite(voltage_arr[j]) and voltage_arr[j] >= energy_v_min else peer_voltage[j]
                    if not (np.isfinite(v) and v >= energy_v_min and missing_current_arr[j] > 0):
                        continue
                    if j + 1 < ei and scb_arr[j + 1] == scb_arr[j]:
                        dt_sec = int(ts_epoch[j + 1]) - int(ts_epoch[j])
                    elif j > run_start:
                        dt_sec = int(ts_epoch[j]) - int(ts_epoch[j - 1])
                    else:
                        dt_sec = context.sample_interval_minutes * 60
                    dt_sec = max(min_dt_sec, min(dt_sec, max_dt_sec))
                    energy_loss[j] = (v * missing_current_arr[j] / 1000.0) * (dt_sec / 3600.0)
            i = run_end

    df["fault_flag"] = fault_flag
    df["energy_loss_kwh"] = energy_loss
    df["confirmed_missing_strings"] = confirmed_missing

    confirmed = df[df["fault_flag"]]
    if confirmed.empty:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "No SCB sustained a current drop long enough to confirm a disconnected string.")

    per_scb = confirmed.groupby("scb_id").agg(
        loss_kwh=("energy_loss_kwh", "sum"),
        max_missing_strings=("confirmed_missing_strings", "max"),
        fault_points=("fault_flag", "sum"),
        inverter_id=("inverter_id", "first"),
    ).reset_index().sort_values("loss_kwh", ascending=False)

    total_loss = float(per_scb["loss_kwh"].sum())

    events = [
        {"equipment_id": r.scb_id, "start": str(g["timestamp_utc"].min()), "end": str(g["timestamp_utc"].max()), "kind": "disconnected_string"}
        for r, (_, g) in zip(per_scb.itertuples(), confirmed.groupby("scb_id"))
    ]

    # PIC-style diagnostic evidence for the worst SCB: reference vs actual current + fault shading
    top_scb = per_scb.iloc[0]["scb_id"]
    scb_df = df[df["scb_id"] == top_scb].sort_values("timestamp_utc")
    if len(scb_df) > 4000:
        scb_df = scb_df.iloc[:: max(1, len(scb_df) // 4000)]
    ts_labels = scb_df["timestamp_utc"].dt.strftime("%Y-%m-%d %H:%M").tolist()
    evidence_charts = [
        diagnostic_line_chart(
            f"ds_evidence_{top_scb}",
            f"Investigate: {top_scb} — expected vs measured SCB current",
            ts_labels,
            {
                "Expected SCB current (A)": scb_df["expected_scb_current"].round(3).tolist(),
                "Measured SCB current (A)": scb_df["dc_current_a"].round(3).tolist(),
            },
            fault_bands=[
                {"start": str(g["timestamp_utc"].min()), "end": str(g["timestamp_utc"].max())}
                for _, g in confirmed[confirmed["scb_id"] == top_scb].groupby(
                    (confirmed["fault_flag"] != confirmed["fault_flag"].shift()).cumsum()
                )
                if g["fault_flag"].any()
            ][:8],
            y_title="Current (A)",
            rule_text=(
                f"Rule: per-string current drops ≥{drop_pct:.0%} below virtual reference for ≥{persistence_minutes} min "
                f"(persistence window). Red bands = confirmed fault samples."
            ),
        )
    ]

    charts = [
        bar_chart("ds_loss_by_scb", "Disconnected String Loss by SCB", per_scb["scb_id"].tolist(), per_scb["loss_kwh"].round(3).tolist(), color="#dc2626"),
        timeline_chart("ds_fault_timeline", "Disconnected String Fault Timeline", events),
    ]

    table = ResultTable(
        title="Confirmed disconnected strings",
        columns=["SCB", "Inverter", "Max missing strings", "Loss (kWh)", "Fault samples"],
        rows=[[r.scb_id, r.inverter_id, int(r.max_missing_strings), round(r.loss_kwh, 3), int(r.fault_points)] for r in per_scb.itertuples()],
    )

    max_missing = int(per_scb["max_missing_strings"].max())
    return ResultObject(
        algorithm_id=ALGORITHM_ID,
        algorithm_version=VERSION,
        status=ResultStatus.OK,
        title="Disconnected Strings",
        summary=f"{len(per_scb)} SCB(s) show a confirmed disconnected string (up to {max_missing} string(s) missing), totaling {total_loss:.2f} kWh of loss.",
        severity="high" if max_missing >= 2 else "medium",
        confidence=0.9,
        affected_equipment=per_scb["scb_id"].tolist(),
        loss_energy_kwh=round(total_loss, 3),
        metrics={"affected_scb_count": float(len(per_scb)), "max_missing_strings": float(max_missing)},
        tables=[table],
        charts=charts,
        recommendations=[
            f"Dispatch a field crew to inspect {', '.join(per_scb['scb_id'].head(5))} for open fuses, disconnected MC4 connectors, or blown string protection.",
        ],
        thresholds_used={"persistence_minutes": persistence_minutes, "current_drop_pct": drop_pct, "missing_string_tolerance": missing_tolerance},
        evidence=EvidenceRef(
            equipment_ids=per_scb["scb_id"].tolist(),
            time_range_start=str(confirmed["timestamp_utc"].min()),
            time_range_end=str(confirmed["timestamp_utc"].max()),
            source_fields=["dc_current_a", "dc_voltage_v", "poa_w_m2", "ghi_w_m2"],
            affected_sample_count=int(len(confirmed)),
            total_sample_count=int(total_rows_pre_filter),
            notes=f"Top evidence: {top_scb} — compare virtual reference curve to measured SCB current in diagnostic chart.",
        ),
        evidence_charts=evidence_charts,
    )
