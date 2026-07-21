"""Inverter clipping by power (GTI-based virtual power curve).

Ported (formulas only) from PIC's backend/engine/clipping_derating.py. Builds a virtual
power curve P_virtual(t) = k x GTI(t) per inverter, where k is the median of (P_actual /
GTI) over healthy, non-clipped samples. A sample is classified as power-clipped when the
inverter is at/above its rated hit-ratio AND the gap to the virtual curve exceeds a noise
floor. Consecutive gap hits seed detection (PIC parity); sustained at-rating plateaus that
accumulate enough gap hits expand to the full plateau so evidence bands match the flat
run. Loss = gap x dt_h summed over clipped samples.

The original PIC engine also classifies "derating" (static/dynamic) from the same virtual
curve; PIC Lite's MVP algorithm list only requires power clipping as a first-class result,
so derate classification is retained internally (it is required to correctly separate
clip-vs-derate before summing clip-only loss) but is not reported as its own ResultObject.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.charts.builders import bar_chart, diagnostic_line_chart, line_chart, to_plotly_time_x
from analytics.common.irradiance import extract_irradiance_frame
from analytics.common.irr_join import merge_irradiance_onto
from analytics.core.context import AnalysisContext
from analytics.core.registry import register_algorithm
from analytics.core.result import EvidenceRef, ResultObject, ResultStatus, ResultTable

ALGORITHM_ID = "clipping_power"
VERSION = "1.0.0-port"


def _rated_kw(inverter_id: str, context: AnalysisContext, observed_p99: dict[str, float]) -> float:
    spec = context.plant.equipment_ratings.get(inverter_id)
    if spec and spec > 0:
        return spec
    observed = observed_p99.get(inverter_id)
    if observed and observed > 0:
        return observed
    return context.plant.inverter_capacity_kw or 1.0


def _local_hour(ts_utc: pd.Series, timezone: str) -> pd.Series:
    """Hour-of-day in the plant's local timezone from a UTC (tz-aware or naive) series."""
    ts = pd.to_datetime(ts_utc, errors="coerce")
    try:
        if getattr(ts.dt, "tz", None) is None:
            ts = ts.dt.tz_localize("UTC")
        return ts.dt.tz_convert(timezone).dt.hour
    except Exception:
        return ts.dt.hour


def _grouped_persistence(mask: pd.Series, groups: pd.Series, min_run: int) -> pd.Series:
    if min_run <= 1 or not mask.any():
        return mask
    boundary = (mask != mask.shift(1)) | (groups != groups.shift(1))
    seg = boundary.cumsum()
    run_sizes = mask.groupby(seg).transform("size")
    return mask & (run_sizes >= min_run)


def _power_clip_mask(
    at_cap: pd.Series,
    gap_real: pd.Series,
    groups: pd.Series,
    persist_min: int,
) -> pd.Series:
    """Classify power-clip samples from at-rating plateaus + virtual headroom.

    PIC seed (unchanged): consecutive ``at_cap & gap_real`` runs of length ≥ ``persist_min``.

    Plateau expansion: a long flat at rating is still clipping when irradiance (via the
    virtual curve) supports more than nameplate — even if gap only intermittently clears
    the noise floor. For each sustained ``at_cap`` plateau (≥ ``persist_min`` samples) that
    contains ≥ ``persist_min`` gap-above-noise hits (not necessarily consecutive), mark the
    entire plateau as clipped so the red band matches the sustained run (not only peak spikes).
    """
    seed = _grouped_persistence(at_cap & gap_real, groups, persist_min)
    at_cap_persist = _grouped_persistence(at_cap, groups, persist_min)
    if not at_cap_persist.any():
        return seed

    boundary = (at_cap != at_cap.shift(1)) | (groups != groups.shift(1))
    seg = boundary.cumsum()
    gap_hits = gap_real.astype("int64").groupby(seg).transform("sum")
    # Full plateau: enough virtual-headroom evidence somewhere in the sustained at-cap run.
    expanded = at_cap_persist & (gap_hits >= persist_min)
    # Keep seed for short consecutive gap spikes that never formed a long at_cap run.
    return seed | expanded


def _mask_time_bands(ts: pd.Series, mask: pd.Series) -> list[dict[str, str]]:
    """Contiguous True runs → {start, end} ISO-ish strings for Plotly shapes."""
    if mask.empty or not bool(mask.any()):
        return []
    runs = (mask != mask.shift(1)).cumsum()
    bands: list[dict[str, str]] = []
    for _, g in ts.groupby(runs):
        m = mask.loc[g.index]
        if not bool(m.any()):
            continue
        g_on = g.loc[m]
        bands.append({"start": str(g_on.min()), "end": str(g_on.max())})
    return bands


@register_algorithm(ALGORITHM_ID, VERSION, required_fields=("ac_power_kw",))
def run(context: AnalysisContext) -> ResultObject:
    t = context.threshold_group(ALGORITHM_ID)
    rated_hit_ratio = t.get("rated_hit_ratio", 0.97)
    gti_floor = t.get("gti_floor_w_m2", 150.0)
    healthy_min = t.get("healthy_gti_min_w_m2", 200.0)
    healthy_max = t.get("healthy_gti_max_w_m2", 700.0)
    healthy_max_of_rated = t.get("healthy_max_of_rated", 0.85)
    noise_frac = t.get("noise_frac_of_rated", 0.03)
    static_std_frac = t.get("static_std_frac_rated", 0.015)
    min_active_frac = t.get("min_active_frac", 0.03)
    min_active_abs_kw = t.get("min_active_abs_kw", 5.0)
    persist_min = int(t.get("persist_min_samples", 3))
    hour_start = int(t.get("hour_start", 7))
    hour_end = int(t.get("hour_end", 18))
    min_healthy_samples = int(t.get("min_healthy_samples", 20))
    min_coverage_frac = float(t.get("min_coverage_frac", 0.40))
    roll_window_min = t.get("roll_window_minutes", 10)

    ac = context.canonical.frame(columns=["timestamp_utc", "device_type", "inverter_id", "ac_power_kw"])
    ac = ac[ac["device_type"] == "inverter"].dropna(subset=["inverter_id"])
    if ac.empty:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "No inverter AC power telemetry found in this upload.")

    irr = extract_irradiance_frame(context)
    if irr.empty:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "No plant/WMS irradiance telemetry found — clipping cannot be classified without a reference curve.")

    ac["ac_power_kw"] = pd.to_numeric(ac["ac_power_kw"], errors="coerce")
    ac = ac.dropna(subset=["ac_power_kw"]).sort_values(["inverter_id", "timestamp_utc"])
    df = merge_irradiance_onto(ac, irr, out_col="gti", tolerance_min=roll_window_min + 2)
    df = df.dropna(subset=["gti"])
    if df.empty:
        return ResultObject.unavailable(ALGORITHM_ID, VERSION, "No inverter samples could be aligned with irradiance timestamps.")

    df["dt_h"] = (df.groupby("inverter_id")["timestamp_utc"].diff().dt.total_seconds() / 3600.0)
    median_dt = df.groupby("inverter_id")["dt_h"].transform("median")
    df["dt_h"] = df["dt_h"].fillna(median_dt).fillna(context.sample_interval_minutes / 60.0).clip(lower=1 / 3600.0, upper=5 / 60.0)

    observed_p99 = ac.groupby("inverter_id")["ac_power_kw"].quantile(0.99).to_dict()
    df["rated"] = df["inverter_id"].map(lambda i: _rated_kw(i, context, observed_p99))

    # Productive-hour gate must use *local* solar time — timestamp_utc is UTC, so for a
    # plant at a large offset (e.g. Asia/Kolkata +5:30) using UTC hours would exclude local
    # solar noon (~06:30 UTC) and miss the very samples where clipping occurs.
    df["hour"] = _local_hour(df["timestamp_utc"], context.timezone)
    in_hours = df["hour"].between(hour_start, hour_end - 1)
    valid = df["gti"] > gti_floor

    min_active_kw = np.maximum(min_active_frac * df["rated"], min_active_abs_kw)
    healthy = valid & in_hours & (df["gti"] >= healthy_min) & (df["gti"] <= healthy_max) & (df["ac_power_kw"] >= min_active_kw) & (df["ac_power_kw"] <= healthy_max_of_rated * df["rated"])

    healthy_counts = healthy.groupby(df["inverter_id"]).sum()
    ratio_frame = df.loc[healthy, ["inverter_id", "ac_power_kw", "gti"]].copy()
    ratio_frame["r"] = ratio_frame["ac_power_kw"] / ratio_frame["gti"]
    ratio_frame = ratio_frame.replace([np.inf, -np.inf], np.nan).dropna(subset=["r"])
    k_per_inv = ratio_frame[ratio_frame["r"] > 0].groupby("inverter_id")["r"].median()

    # ── Coverage guard (PIC parity) ─────────────────────────────────────────
    # Skip inverters whose usable daytime samples fall below `min_coverage_frac` of the
    # expected count, so a sparsely-reporting inverter is not falsely calibrated/classified.
    # Ported from clipping_derating.py; the denominator is capped by the AC↔GTI pairs we
    # actually observed in productive hours so sparse-but-complete uploads don't false-fail.
    ts_all = df["timestamp_utc"]
    try:
        n_days = max(1, (ts_all.max().normalize() - ts_all.min().normalize()).days + 1)
    except Exception:
        n_days = 1
    daylight_minutes = max(1, (hour_end - hour_start)) * 60 * n_days
    cadence_min = max(context.sample_interval_minutes, 0.5)
    cadence_expected = max(1.0, daylight_minutes / cadence_min)

    pairs_in_hours = (df["ac_power_kw"].notna() & df["gti"].notna() & in_hours)
    pairs_per_inv = pairs_in_hours.groupby(df["inverter_id"]).sum().astype(float)
    observed_counts = (valid & in_hours).groupby(df["inverter_id"]).sum().astype(float)
    expected_per_inv = np.minimum(cadence_expected, pairs_per_inv.clip(lower=1.0))
    cov_ratio = (observed_counts / expected_per_inv.replace(0.0, np.nan)).fillna(0.0)
    low_cov_invs = set(cov_ratio[cov_ratio < min_coverage_frac].index)

    all_invs = list(df["inverter_id"].unique())
    skipped: list[dict] = []
    keep_invs: list[str] = []
    for i in all_invs:
        if i in low_cov_invs:
            skipped.append({"inverter_id": i, "reason": f"low data coverage ({cov_ratio.get(i, 0.0) * 100:.0f}%)"})
        elif healthy_counts.get(i, 0) < min_healthy_samples or (k_per_inv.get(i, 0) or 0) <= 0:
            skipped.append({"inverter_id": i, "reason": f"not enough healthy calibration samples ({int(healthy_counts.get(i, 0))})"})
        else:
            keep_invs.append(i)

    if not keep_invs:
        detail = ""
        if skipped:
            detail = " Skipped: " + "; ".join(f"{s['inverter_id']} ({s['reason']})" for s in skipped[:8])
            if len(skipped) > 8:
                detail += f" and {len(skipped) - 8} more"
        return ResultObject.unavailable(
            ALGORITHM_ID,
            VERSION,
            "Not enough healthy, non-clipped samples to calibrate a reference power curve for any inverter." + detail,
        )

    df = df[df["inverter_id"].isin(keep_invs)].copy()
    in_hours = df["hour"].between(hour_start, hour_end - 1)
    valid = (df["gti"] > gti_floor) & in_hours

    df["k"] = df["inverter_id"].map(k_per_inv)
    df["p_virtual"] = df["k"] * df["gti"]
    df["gap"] = (df["p_virtual"] - df["ac_power_kw"]).clip(lower=0.0)

    roll_n = max(3, int(round(roll_window_min / max(context.sample_interval_minutes, 0.5))))
    df["ac_std"] = df.groupby("inverter_id")["ac_power_kw"].transform(lambda s: s.rolling(roll_n, min_periods=max(3, roll_n // 2), center=True).std()).fillna(0.0)

    noise_abs = noise_frac * df["rated"]
    static_std_abs = static_std_frac * df["rated"]
    min_active_kw_f = np.maximum(min_active_frac * df["rated"], min_active_abs_kw)

    active = valid & (df["ac_power_kw"] >= min_active_kw_f)
    at_cap = active & (df["ac_power_kw"] >= rated_hit_ratio * df["rated"])
    gap_real = active & (df["gap"] > noise_abs)

    is_power_clip = _power_clip_mask(at_cap, gap_real, df["inverter_id"], persist_min)

    df["loss_step"] = np.where(is_power_clip, df["gap"] * df["dt_h"], 0.0)
    df["is_clip"] = is_power_clip
    df["at_cap"] = at_cap
    # Sustained at-rating plateau without enough virtual headroom to classify as clip.
    at_cap_persist = _grouped_persistence(at_cap, df["inverter_id"], persist_min)
    df["at_rating_unclassified"] = at_cap_persist & ~is_power_clip

    per_inv = df.groupby("inverter_id").agg(loss_kwh=("loss_step", "sum"), clip_points=("is_clip", "sum")).reset_index()
    per_inv = per_inv[per_inv["clip_points"] > 0].sort_values("loss_kwh", ascending=False)

    if per_inv.empty:
        return ResultObject(
            algorithm_id=ALGORITHM_ID,
            algorithm_version=VERSION,
            status=ResultStatus.OK,
            title="Inverter Clipping by Power",
            summary="Power clipping module ran - no inverter showed sustained AC power clipping in this period.",
            severity="info",
            confidence=0.85,
            metrics={"clipped_inverter_count": 0.0, "skipped_inverter_count": float(len(skipped))},
            recommendations=(
                ["No power clipping events detected under the configured thresholds."]
                + ([f"{len(skipped)} inverter(s) were skipped for low data coverage or insufficient calibration samples."] if skipped else [])
            ),
            thresholds_used={"min_coverage_frac": min_coverage_frac},
            evidence=EvidenceRef(source_fields=["ac_power_kw", "poa_w_m2", "ghi_w_m2"], total_sample_count=int(len(df))),
        )

    total_loss = float(per_inv["loss_kwh"].sum())

    clip_events = df[df["is_clip"]].copy()
    clip_events["hour"] = clip_events["timestamp_utc"].dt.floor("h")
    hourly = clip_events.groupby("hour")["loss_step"].sum()

    # Primary evidence: AC power timeseries for the worst clipped inverter, with red bands
    # on classified clip windows so the flat plateau at rating is visible (same pattern as
    # disconnected_strings / module_damage diagnostic charts).
    top_inv = str(per_inv.iloc[0]["inverter_id"])
    inv_full = df[df["inverter_id"] == top_inv].sort_values("timestamp_utc")
    # Build bands from full-resolution masks *before* downsample so stride cannot drop runs.
    fault_bands = _mask_time_bands(inv_full["timestamp_utc"], inv_full["is_clip"])
    info_bands = _mask_time_bands(inv_full["timestamp_utc"], inv_full["at_rating_unclassified"])
    inv_df = inv_full
    if len(inv_df) > 4000:
        inv_df = inv_df.iloc[:: max(1, len(inv_df) // 4000)]
    ts_labels = inv_df["timestamp_utc"].dt.strftime("%Y-%m-%d %H:%M").tolist()
    rated_kw = float(inv_df["rated"].iloc[0]) if len(inv_df) else 0.0
    evidence_charts = [
        diagnostic_line_chart(
            f"clipping_power_evidence_{top_inv}",
            f"Investigate: {top_inv} — AC power plateau at rating during clip",
            ts_labels,
            {
                "AC power (kW)": inv_df["ac_power_kw"].round(2).tolist(),
                "Virtual power (kW)": inv_df["p_virtual"].round(2).tolist(),
                "Rated AC capacity (kW)": [round(rated_kw, 2)] * len(inv_df),
            },
            fault_bands=fault_bands,
            info_bands=info_bands,
            secondary_series={"Irradiance / POA (W/m²)": inv_df["gti"].round(1).tolist()},
            y_title="Power (kW)",
            y2_title="Irradiance (W/m²)",
            rule_text=(
                f"Rule: AC ≥ {rated_hit_ratio:.0%} of rated AND virtual gap > noise "
                f"(≥{persist_min} hits on a sustained at-rating plateau). "
                f"Red = classified clip window (full plateau). "
                f"Amber = at rating but not classified (insufficient virtual headroom / irradiance)."
            ),
        )
    ]

    charts = [
        bar_chart("clipping_power_loss_by_inverter", "Clipping Loss by Inverter", per_inv["inverter_id"].tolist(), per_inv["loss_kwh"].round(2).tolist(), y_title="Loss (kWh)"),
    ]
    if not hourly.empty:
        # Secondary loss trend — reindex across the full analysis window so the series has a
        # real time span (noon-only clipping would otherwise collapse to one hourly bucket).
        t0 = pd.Timestamp(df["timestamp_utc"].min()).floor("h")
        t1 = pd.Timestamp(df["timestamp_utc"].max()).floor("h")
        full_idx = pd.date_range(t0, t1, freq="h", tz=getattr(t0, "tz", None))
        hourly = hourly.reindex(full_idx, fill_value=0.0).rename_axis("hour").reset_index(name="loss_step")
        charts.append(
            line_chart(
                "clipping_power_trend",
                "Power Clipping Loss Trend",
                to_plotly_time_x(hourly["hour"].tolist()),
                {"Loss (kWh)": [float(v) for v in hourly["loss_step"].round(2).tolist()]},
                y_title="Loss (kWh)",
            )
        )

    table = ResultTable(
        title="Power clipping by inverter",
        columns=["Inverter", "Loss (kWh)", "Clipped samples"],
        rows=[[r.inverter_id, round(r.loss_kwh, 2), int(r.clip_points)] for r in per_inv.itertuples()],
    )

    return ResultObject(
        algorithm_id=ALGORITHM_ID,
        algorithm_version=VERSION,
        status=ResultStatus.OK,
        title="Inverter Clipping by Power",
        summary=f"{len(per_inv)} inverter(s) show sustained power clipping totaling {total_loss:.1f} kWh.",
        severity="medium" if total_loss > 0 else "info",
        confidence=0.85,
        affected_equipment=per_inv["inverter_id"].tolist(),
        loss_energy_kwh=round(total_loss, 2),
        metrics={"clipped_inverter_count": float(len(per_inv)), "skipped_inverter_count": float(len(skipped))},
        tables=[table],
        charts=charts,
        recommendations=[
            "Power clipping at the inverter's rated AC capacity is often expected behavior around solar noon on high-irradiance days — confirm this matches expected DC/AC oversizing before treating it as a loss to remediate.",
        ]
        + ([f"{len(skipped)} inverter(s) were excluded from clipping analysis for low data coverage or insufficient healthy calibration samples."] if skipped else []),
        thresholds_used={"rated_hit_ratio": rated_hit_ratio, "gti_floor_w_m2": gti_floor, "noise_frac_of_rated": noise_frac, "persist_min_samples": float(persist_min), "min_coverage_frac": min_coverage_frac},
        evidence=EvidenceRef(
            equipment_ids=per_inv["inverter_id"].tolist(),
            time_range_start=str(df["timestamp_utc"].min()),
            time_range_end=str(df["timestamp_utc"].max()),
            source_fields=["ac_power_kw", "poa_w_m2", "ghi_w_m2"],
            affected_sample_count=int(df["is_clip"].sum()),
            total_sample_count=int(len(df)),
            notes=(
                f"Top evidence: {top_inv} — red bands = classified clip plateaus at rating; "
                f"amber = at rating without enough irradiance/virtual headroom; POA on secondary axis."
            ),
        ),
        evidence_charts=evidence_charts,
    )
