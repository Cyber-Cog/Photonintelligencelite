"""Smoke tests for PDF report generation — tight content parity with Results UI."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from reportlab.platypus import Image as RLImage, KeepTogether, Paragraph, Table

from analytics.core.context import PlantConfig
from analytics.core.orchestrator import OrchestratorRun
from analytics.core.result import ChartSpec, EvidenceRef, ResultObject, ResultStatus, ResultTable
from analytics.preprocessing.interval_normalize import IntervalNormalizationResult
from analytics.preprocessing.validation import ValidationReport
from analytics.reports.loss_bridge import build_loss_bridge
from analytics.reports.owner_brief import build_owner_brief, derive_plant_status
from analytics.reports.pdf_builder import (
    _fault_rows_from_results,
    _worth_detail_section,
    build_pdf,
    build_pdf_story,
)
from analytics.reports.pdf_charts import chart_has_plottable_data, render_chart_spec, render_waterfall
from analytics.reports.report_data import ReportContext


def _sample_ctx() -> ReportContext:
    plant = PlantConfig(
        plant_name="Demo Solar Plant",
        ac_capacity_mw=1.0,
        dc_capacity_mwp=1.2,
        module_rating_wp=545.0,
        inverter_capacity_kw=100.0,
        module_technology="Mono PERC",
        bifacial=False,
        timezone="Asia/Kolkata",
        tariff_inr_per_kwh=3.5,
        pr_benchmark_pct=80.0,
    )
    ts = [
        "2024-01-01 06:00",
        "2024-01-01 07:00",
        "2024-01-01 08:00",
        "2024-01-01 09:00",
        "2024-01-01 10:00",
        "2024-01-01 11:00",
        "2024-01-01 12:00",
        "2024-01-01 13:00",
    ]
    ds = ResultObject(
        algorithm_id="disconnected_strings",
        algorithm_version="1.0",
        status=ResultStatus.OK,
        title="Disconnected Strings",
        summary="2 SCB(s) show a confirmed disconnected string.",
        severity="high",
        confidence=0.9,
        affected_equipment=["INV-01-SCB-01", "INV-01-SCB-02"],
        loss_energy_kwh=120.5,
        loss_revenue=421.75,
        metrics={"affected_scb_count": 2.0},
        tables=[
            ResultTable(
                title="Confirmed disconnected strings",
                columns=["SCB", "Inverter", "Max missing strings", "Loss (kWh)", "Fault samples"],
                rows=[
                    ["INV-01-SCB-01", "INV-01", 1, 80.25, 40],
                    ["INV-01-SCB-02", "INV-01", 1, 40.25, 20],
                ],
            )
        ],
        charts=[
            ChartSpec(
                chart_id="ds_loss_by_scb",
                title="Disconnected String Loss by SCB",
                chart_type="bar",
                figure={
                    "data": [
                        {
                            "type": "bar",
                            "x": ["INV-01-SCB-01", "INV-01-SCB-02"],
                            "y": [80.25, 40.25],
                            "marker": {"color": "#dc2626"},
                        }
                    ],
                    "layout": {"yaxis": {"title": {"text": "Loss (kWh)"}}},
                },
            )
        ],
        recommendations=["Inspect open fuses on INV-01-SCB-01."],
        thresholds_used={"persist_min_samples": 3.0},
        evidence=EvidenceRef(
            equipment_ids=["INV-01-SCB-01", "INV-01-SCB-02"],
            time_range_start="2024-01-01T06:00:00",
            time_range_end="2024-01-01T18:00:00",
            source_fields=["dc_current_a"],
            affected_sample_count=60,
            total_sample_count=1000,
        ),
        evidence_charts=[
            ChartSpec(
                chart_id="ds_evidence_INV-01-SCB-01",
                title="Investigate: INV-01-SCB-01",
                chart_type="diagnostic",
                figure={
                    "data": [
                        {
                            "type": "scatter",
                            "mode": "lines",
                            "name": "Expected SCB current (A)",
                            "x": ts,
                            "y": [10, 12, 14, 15, 16, 15, 14, 12],
                            "line": {"color": "#d97706"},
                        },
                        {
                            "type": "scatter",
                            "mode": "lines",
                            "name": "Measured SCB current (A)",
                            "x": ts,
                            "y": [10, 12, 7, 6, 6, 15, 14, 12],
                            "line": {"color": "#059669"},
                        },
                    ],
                    "layout": {
                        "yaxis": {"title": {"text": "Current (A)"}},
                        "shapes": [
                            {
                                "type": "rect",
                                "xref": "x",
                                "yref": "paper",
                                "x0": "2024-01-01 08:00",
                                "x1": "2024-01-01 11:00",
                                "y0": 0,
                                "y1": 1,
                                "fillcolor": "rgba(220,38,38,0.12)",
                                "line": {"width": 0},
                            }
                        ],
                    },
                },
            )
        ],
    )
    clip = ResultObject(
        algorithm_id="clipping_power",
        algorithm_version="1.0",
        status=ResultStatus.OK,
        title="Clipping (Power)",
        summary="Power clipping on INV-01.",
        severity="medium",
        affected_equipment=["INV-01"],
        loss_energy_kwh=50.0,
        metrics={"clipped_inverters": 1.0},
        tables=[
            ResultTable(
                title="Power clipping by inverter",
                columns=["Inverter", "Loss (kWh)", "Clipped samples"],
                rows=[["INV-01", 50.0, 12]],
            )
        ],
        charts=[
            ChartSpec(
                chart_id="clip_bar",
                title="Clipping loss by inverter",
                chart_type="bar",
                figure={
                    "data": [{"type": "bar", "x": ["INV-01"], "y": [50.0], "marker": {"color": "#d97706"}}],
                    "layout": {},
                },
            ),
            ChartSpec(
                chart_id="clip_eff_box",
                title="Inverter efficiency distribution",
                chart_type="box",
                figure={
                    "data": [
                        {
                            "type": "box",
                            "x": ["INV-01", "INV-02"],
                            "q1": [92.0, 90.0],
                            "median": [95.0, 93.0],
                            "q3": [97.0, 96.0],
                            "lowerfence": [88.0, 86.0],
                            "upperfence": [99.0, 98.0],
                        }
                    ],
                    "layout": {"yaxis": {"title": {"text": "Efficiency (%)"}}},
                },
            ),
        ],
        recommendations=[
            "This is a v1 algorithm with no production baseline yet — treat magnitudes as directional.",
            "Review inverter AC nameplate vs DC array sizing on INV-01.",
        ],
        thresholds_used={"min_coverage_frac": 0.7},
        evidence=EvidenceRef(
            equipment_ids=["INV-01"],
            time_range_start="2024-01-01T10:00:00",
            time_range_end="2024-01-01T14:00:00",
            affected_sample_count=12,
            total_sample_count=500,
        ),
    )
    empty_ok = ResultObject(
        algorithm_id="clipping_current",
        algorithm_version="1.0",
        status=ResultStatus.OK,
        title="Clipping (Current)",
        summary="Current clipping module ran - no SCB/MPPT showed sustained saturation.",
        severity="info",
        metrics={"clipped_equipment_count": 0.0},
        recommendations=["No DC current clipping events detected under the configured thresholds."],
        thresholds_used={"current_limit_hit_ratio": 0.95},
        evidence=EvidenceRef(source_fields=["dc_current_a"], total_sample_count=500),
    )
    empty_chart = ResultObject(
        algorithm_id="string_outlier",
        algorithm_version="1.0",
        status=ResultStatus.OK,
        title="String Outlier",
        summary="No outliers.",
        severity="info",
        charts=[
            ChartSpec(
                chart_id="empty_bar",
                title="Empty loss bar",
                chart_type="bar",
                figure={"data": [{"type": "bar", "x": [], "y": []}], "layout": {}},
            ),
            ChartSpec(
                chart_id="zero_bar",
                title="Zero loss bar",
                chart_type="bar",
                figure={"data": [{"type": "bar", "x": ["A"], "y": [0.0]}], "layout": {}},
            ),
        ],
        recommendations=["No outliers detected."],
    )
    unavailable = ResultObject.unavailable("module_damage", "1.0", "Missing dc_voltage_v")

    run = OrchestratorRun(
        results=[ds, clip, empty_ok, empty_chart, unavailable],
        kpis={
            "plant_availability_pct": 98.5,
            "performance_ratio_pct": 82.0,
            "specific_yield_kwh_per_kwp": 4.2,
            "estimated_energy_loss_kwh": 170.5,
            "revenue_loss_inr": 596.75,
            "revenue_loss_available": True,
            "fault_count": 3,
            "total_ac_energy_kwh": 10000.0,
        },
    )
    validation = ValidationReport(row_count=1000, column_count=12)
    interval = IntervalNormalizationResult(
        detected_interval_minutes=15.0,
        resampled=False,
        is_irregular=False,
        notes=[],
    )
    return ReportContext(
        job_id="test-job-pdf",
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        plant=plant,
        run=run,
        validation=validation,
        interval_result=interval,
        mapping_confidence_by_column={"AC Power (kW)": 0.95},
    )


def _paragraph_texts(story: list) -> list[str]:
    texts: list[str] = []

    def walk(items: list) -> None:
        for item in items:
            if isinstance(item, Paragraph):
                texts.append(item.getPlainText())
            elif isinstance(item, Table) and hasattr(item, "_cellvalues"):
                for row in item._cellvalues:
                    for cell in row:
                        if isinstance(cell, Paragraph):
                            texts.append(cell.getPlainText())
                        elif isinstance(cell, Table):
                            walk([cell])
                        elif isinstance(cell, (list, tuple)):
                            walk(list(cell))
            elif isinstance(item, KeepTogether) and hasattr(item, "_content"):
                walk(list(item._content))
            elif hasattr(item, "_content"):
                walk(list(item._content))
            elif isinstance(item, (list, tuple)):
                walk(list(item))

    walk(story)
    return texts


def _count_images(story: list) -> int:
    n = 0

    def walk(items: list) -> None:
        nonlocal n
        for item in items:
            if isinstance(item, RLImage):
                n += 1
            elif isinstance(item, KeepTogether) and hasattr(item, "_content"):
                walk(list(item._content))
            elif hasattr(item, "_content"):
                walk(list(item._content))
            elif isinstance(item, (list, tuple)):
                walk(list(item))

    walk(story)
    return n


def _count_table_headers(story: list, first_cell: str) -> int:
    n = 0
    for item in story:
        if isinstance(item, Table) and hasattr(item, "_cellvalues") and item._cellvalues:
            header = item._cellvalues[0]
            if header and str(header[0]) == first_cell:
                n += 1
        elif isinstance(item, KeepTogether) and hasattr(item, "_content"):
            n += _count_table_headers(list(item._content), first_cell)
    return n


def test_build_loss_bridge_expected_actual():
    ctx = _sample_ctx()
    bridge = build_loss_bridge(ctx.run.kpis, ctx.run.results)
    assert bridge is not None
    assert bridge.mode == "bridge"
    assert bridge.expected_mwh == pytest.approx(10000.0 / 1000.0 / 0.82, rel=1e-6)
    assert bridge.actual_mwh == pytest.approx(10.0)
    assert bridge.diagnosed_mwh == pytest.approx(0.1705, rel=1e-3)
    labels = [s.label for s in bridge.segments]
    assert "Expected energy" in labels
    assert "Actual energy (metered)" in labels


def test_render_waterfall_image():
    ctx = _sample_ctx()
    bridge = build_loss_bridge(ctx.run.kpis, ctx.run.results)
    assert bridge is not None
    img = render_waterfall(bridge)
    assert img is not None
    assert isinstance(img, RLImage)
    assert img.drawWidth > 0
    assert img.drawHeight > 0


def test_render_bar_and_diagnostic_charts():
    ctx = _sample_ctx()
    ds = ctx.run.results[0]
    bar = render_chart_spec(ds.charts[0])
    assert bar is not None
    diag = render_chart_spec(ds.evidence_charts[0])
    assert diag is not None
    box = render_chart_spec(ctx.run.results[1].charts[1])
    assert box is not None


def test_empty_and_zero_charts_skipped():
    empty = ChartSpec(
        chart_id="e",
        title="Empty",
        chart_type="bar",
        figure={"data": [{"type": "bar", "x": [], "y": []}], "layout": {}},
    )
    zero = ChartSpec(
        chart_id="z",
        title="Zero",
        chart_type="bar",
        figure={"data": [{"type": "bar", "x": ["A"], "y": [0.0]}], "layout": {}},
    )
    assert chart_has_plottable_data(empty) is False
    assert chart_has_plottable_data(zero) is False
    assert render_chart_spec(empty) is None
    assert render_chart_spec(zero) is None


def test_fault_rows_flattened():
    ctx = _sample_ctx()
    rows = _fault_rows_from_results(ctx.run.results)
    assert len(rows) == 3  # 2 DS + 1 clipping; empty modules excluded
    assert any("Disconnected" in r[0] for r in rows)
    assert any(r[1] == "INV-01" for r in rows)


def test_worth_detail_skips_noise_modules():
    ctx = _sample_ctx()
    by_id = {r.algorithm_id: r for r in ctx.run.results}
    assert _worth_detail_section(by_id["disconnected_strings"]) is True
    assert _worth_detail_section(by_id["clipping_power"]) is True
    assert _worth_detail_section(by_id["clipping_current"]) is False
    assert _worth_detail_section(by_id["string_outlier"]) is False
    assert _worth_detail_section(by_id["module_damage"]) is False


def _all_table_cell_texts(story: list) -> list[str]:
    texts: list[str] = []

    def walk(items: list) -> None:
        for item in items:
            if isinstance(item, Table) and hasattr(item, "_cellvalues"):
                for row in item._cellvalues:
                    for cell in row:
                        if isinstance(cell, Paragraph):
                            texts.append(cell.getPlainText())
                        elif isinstance(cell, Table):
                            walk([cell])
                        elif isinstance(cell, (list, tuple)):
                            walk(list(cell))
                        elif cell is not None:
                            texts.append(str(cell))
            elif isinstance(item, KeepTogether) and hasattr(item, "_content"):
                walk(list(item._content))
            elif hasattr(item, "_content"):
                walk(list(item._content))
            elif isinstance(item, (list, tuple)):
                walk(list(item))

    walk(story)
    return texts


def test_owner_brief_status_and_top_problems():
    ctx = _sample_ctx()
    brief = build_owner_brief(ctx.run.results)
    assert brief.status == "Needs attention"
    assert brief.fault_module_count == 2
    assert len(brief.problems) == 2
    assert any("disconnected" in p.problem.lower() for p in brief.problems)
    assert any(p.impact_kwh and p.impact_kwh > 0 for p in brief.problems)
    assert brief.next_steps
    assert any("fuse" in s.lower() or "scb" in s.lower() for s in brief.next_steps)
    # Blocked module_damage should surface a setup next step
    assert any("missing" in s.lower() or "setup" in s.lower() for s in brief.next_steps)

    status, _ = derive_plant_status([])
    assert status == "Healthy"

    critical = ResultObject(
        algorithm_id="disconnected_strings",
        algorithm_version="1.0",
        status=ResultStatus.OK,
        title="Disconnected Strings",
        summary="Critical outage",
        severity="critical",
        affected_equipment=["INV-01-SCB-01"],
        loss_energy_kwh=500.0,
        evidence=EvidenceRef(),
    )
    status_c, _ = derive_plant_status([critical])
    assert status_c == "Critical"


def test_build_pdf_story_sections():
    ctx = _sample_ctx()
    story = build_pdf_story(ctx)
    texts = _paragraph_texts(story)
    joined = "\n".join(texts)
    table_joined = "\n".join(_all_table_cell_texts(story))

    for needle in (
        "Photon Intelligence Center Lite · Solar Performance Analysis",
        "Demo Solar Plant",
        "Status: Needs attention",
        "Top problems",
        "What to do next",
        "Key Performance Indicators",
        "Energy Loss Bridge",
        "All Faults",
        "Fault-wise Analysis",
        "Disconnected Strings",
        "Technical Appendix",
        "Evidence — Investigate: INV-01-SCB-01",
        "Modules not detailed in this report",
    ):
        assert needle in joined, f"missing expected PDF section: {needle}"

    # Cover includes job id + owner-facing diagnosis (not metadata-only)
    assert "test-job-pdf" in joined
    assert "string groups look disconnected" in joined or "disconnected or offline" in joined
    assert "Impact ≈" in joined
    assert "120.5" in joined or "120.5 kWh" in joined
    # Thin analyst-only executive paragraph removed in favor of owner brief
    assert "Executive Summary" not in joined

    # Noise / duplicates removed
    assert "Diagnosed Loss by Module" not in joined
    assert "Non-default thresholds applied" not in joined
    assert "persist_min_samples=3" not in joined
    assert "[unavailable]" not in joined
    assert "could not be rendered" not in joined
    assert "No DC current clipping events detected" not in joined
    assert "This is a v1 algorithm" not in joined
    # Finding table not repeated under Fault-wise (lives in All Faults only)
    assert "Confirmed disconnected strings" not in joined
    assert "Power clipping by inverter" not in joined
    # Actionable rec kept; empty / unavailable modules only in appendix table
    assert "Inspect open fuses on INV-01-SCB-01." in joined
    assert "Review inverter AC nameplate" in joined
    assert "Clipping (Current)" in table_joined
    assert "Module Damage" in table_joined or "module_damage" in table_joined.lower()
    assert "Unavailable" in table_joined
    assert "No findings" in table_joined

    # Single All Faults table header
    assert _count_table_headers(story, "Fault type") == 1

    # KPI strip + waterfall + algorithm charts should embed multiple images
    assert _count_images(story) >= 4, "PDF should embed waterfall/chart images"


def test_build_pdf_bytes_smoke():
    ctx = _sample_ctx()
    pdf = build_pdf(ctx)
    assert pdf.startswith(b"%PDF")
    # Visual PDF with real charts; still leaner than dumping every empty module
    assert len(pdf) > 15000
    assert len(pdf) < 2_500_000
