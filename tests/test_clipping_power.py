"""Power clipping should be detected on INV-01 around solar noon: the synthetic plant is
built with a ~1.1 DC:AC oversizing ratio (docs in synthetic_generator.py), so DC power
naturally exceeds the 90 kW AC rating at peak irradiance on the non-degraded inverter.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from analytics.algorithms import clipping_power
from analytics.algorithms.clipping_power import _mask_time_bands, _power_clip_mask
from analytics.core.result import ResultStatus


def test_power_clipping_detected_on_oversized_inverter(demo_context):
    result = clipping_power.run(demo_context)

    assert result.status == ResultStatus.OK
    assert "INV-01" in result.affected_equipment
    assert result.loss_energy_kwh is not None
    assert result.loss_energy_kwh > 0
    assert result.metrics["clipped_inverter_count"] >= 1


def test_power_clipping_evidence_chart_shows_power_plateau_with_fault_bands(demo_context):
    """Primary Investigate chart: AC power timeseries + red clip bands (not loss-only)."""
    result = clipping_power.run(demo_context)
    assert result.status == ResultStatus.OK
    assert result.evidence_charts, "Expected diagnostic evidence chart when clipping is detected"

    evidence = result.evidence_charts[0]
    assert evidence.chart_type == "diagnostic"
    assert "INV-01" in evidence.chart_id or "INV-01" in evidence.title

    dumped = evidence.model_dump(mode="json")
    layout = dumped["figure"]["layout"]
    traces = dumped["figure"]["data"]
    assert layout.get("xaxis", {}).get("type") == "date"
    assert len(traces) >= 2, "Need AC power plus at least rated/virtual reference"

    power_trace = next((t for t in traces if "AC power" in str(t.get("name", ""))), traces[0])
    xs = power_trace["x"]
    ys = power_trace["y"]
    assert len(xs) >= 2
    assert len(xs) == len(ys)
    assert all(isinstance(v, str) for v in xs)
    assert all("T" in v for v in xs), "x values must be ISO-8601 for Plotly date axes"

    parsed = [datetime.strptime(v[:19], "%Y-%m-%dT%H:%M:%S") for v in xs]
    span = parsed[-1] - parsed[0]
    assert span.total_seconds() >= 3600, f"Expected ≥1h span on evidence chart, got {span}"

    shapes = layout.get("shapes") or []
    rects = [s for s in shapes if isinstance(s, dict) and s.get("type") == "rect"]
    assert rects, "Expected red fault-band shapes for classified clip windows"
    assert any(float(y) > 0 for y in ys if y is not None), "AC power series must be non-empty"


def test_power_clipping_evidence_includes_irradiance_on_secondary_axis(demo_context):
    """Investigate chart plots POA/GTI on yaxis2 so users can see why plateaus are/aren't clip."""
    result = clipping_power.run(demo_context)
    assert result.status == ResultStatus.OK
    evidence = result.evidence_charts[0]
    dumped = evidence.model_dump(mode="json")
    traces = dumped["figure"]["data"]
    layout = dumped["figure"]["layout"]

    irr = next((t for t in traces if "Irradiance" in str(t.get("name", ""))), None)
    assert irr is not None, "Expected irradiance series on the evidence chart"
    assert irr.get("yaxis") == "y2"
    assert any(float(v) > 0 for v in irr["y"] if v is not None)
    assert "yaxis2" in layout
    assert layout["yaxis2"].get("overlaying") == "y"
    assert layout["yaxis2"].get("side") == "right"

    rule = ""
    for ann in layout.get("annotations") or []:
        rule += str(ann.get("text") or "")
    assert "Red" in rule and "Amber" in rule


def test_power_clipping_multi_interval_clip_bands_cover_plateau_not_only_peak(demo_context):
    """Classified clip bands must span sustained at-rating plateaus, not a single 10-min peak.

    Regression: consecutive gap>noise persistence alone left only 06:05–06:15 red while AC
    sat at rated for ~2h; plateau expansion marks the full virtual>rated run.
    """
    result = clipping_power.run(demo_context)
    assert result.status == ResultStatus.OK
    evidence = result.evidence_charts[0]
    shapes = evidence.figure["layout"].get("shapes") or []
    red = [
        s
        for s in shapes
        if isinstance(s, dict) and s.get("type") == "rect" and "220,38,38" in str(s.get("fillcolor", ""))
    ]
    assert red, "Expected at least one red classified-clip band"

    def _span_seconds(shape: dict) -> float:
        t0 = datetime.strptime(str(shape["x0"])[:19], "%Y-%m-%dT%H:%M:%S")
        t1 = datetime.strptime(str(shape["x1"])[:19], "%Y-%m-%dT%H:%M:%S")
        return (t1 - t0).total_seconds()

    assert max(_span_seconds(s) for s in red) >= 30 * 60, (
        "Expected a classified clip band covering ≥30 minutes of the at-rating plateau"
    )
    # Multiple solar-noon days in the synthetic set should yield multiple clip intervals.
    assert len(red) >= 2, f"Expected multi-day clip bands, got {len(red)}"


def test_power_clip_mask_expands_plateau_with_nonconsecutive_gap_hits():
    """Unit: ≥persist_min gap hits anywhere in a sustained at_cap run expand the whole plateau."""
    idx = pd.RangeIndex(12)
    groups = pd.Series(["INV-01"] * 12, index=idx)
    at_cap = pd.Series([False, True, True, True, True, True, True, True, True, True, False, False], index=idx)
    # Gap clears noise on samples 2, 5, 8 only (not consecutive) — old logic would miss this run.
    gap_real = pd.Series([False, False, True, False, False, True, False, False, True, False, False, False], index=idx)

    mask = _power_clip_mask(at_cap, gap_real, groups, persist_min=3)
    assert int(mask.sum()) == 9  # full at_cap plateau indices 1..9
    assert bool(mask.iloc[1]) and bool(mask.iloc[9])
    assert not bool(mask.iloc[0]) and not bool(mask.iloc[10])


def test_mask_time_bands_emits_all_contiguous_runs():
    ts = pd.to_datetime(
        [
            "2026-01-01 06:00",
            "2026-01-01 06:05",
            "2026-01-01 06:10",
            "2026-01-01 07:00",
            "2026-01-01 07:05",
            "2026-01-01 08:00",
        ]
    )
    mask = pd.Series([True, True, True, False, False, True])
    bands = _mask_time_bands(pd.Series(ts), mask)
    assert len(bands) == 2
    assert "06:00" in bands[0]["start"]
    assert "06:10" in bands[0]["end"]
    assert "08:00" in bands[1]["start"]


def test_power_clipping_trend_chart_uses_iso_timestamps_with_real_span(demo_context):
    """Secondary loss trend: ISO datetime x spanning the analysis window.

    A single hourly clip bucket previously produced mode=lines with one point; Plotly's
    date autorange collapsed to ~2 ms around that timestamp and drew no series.
    """
    result = clipping_power.run(demo_context)
    assert result.status == ResultStatus.OK

    trend = next((c for c in result.charts if c.chart_id == "clipping_power_trend"), None)
    assert trend is not None, "Expected clipping_power_trend when clip loss > 0"

    dumped = trend.model_dump(mode="json")
    trace = dumped["figure"]["data"][0]
    xs = trace["x"]
    ys = trace["y"]

    assert len(xs) >= 2, "Trend must cover more than one hour so the date axis has real duration"
    assert len(xs) == len(ys)
    assert all(isinstance(v, str) for v in xs)
    assert all("T" in v for v in xs), "x values must be ISO-8601 (YYYY-MM-DDTHH:MM:SS)"
    assert trace.get("mode") == "lines+markers"
    assert dumped["figure"]["layout"]["xaxis"].get("type") == "date"

    parsed = [datetime.strptime(v[:19], "%Y-%m-%dT%H:%M:%S") for v in xs]
    span = parsed[-1] - parsed[0]
    assert span.total_seconds() >= 3600, f"Expected ≥1h span, got {span}"
    assert any(float(y) > 0 for y in ys), "Loss series must include the clipped-hour spike"
