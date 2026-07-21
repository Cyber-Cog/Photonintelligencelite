"""INV-02 is built with a systematic 3.5% efficiency penalty (LOW_EFFICIENCY_FACTOR in
synthetic_generator.py) relative to INV-01, so it must show up as the lower-efficiency,
higher-loss inverter in both the efficiency and box-plot modules.
"""
from __future__ import annotations

from analytics.algorithms import box_plot, inverter_efficiency
from analytics.core.result import ResultStatus


def test_inverter_efficiency_flags_degraded_inverter(demo_context):
    result = inverter_efficiency.run(demo_context)
    assert result.status == ResultStatus.OK

    rows_by_inv = {r[0]: r for r in result.tables[0].rows}
    assert "INV-01" in rows_by_inv and "INV-02" in rows_by_inv
    eff_inv01 = rows_by_inv["INV-01"][4]
    eff_inv02 = rows_by_inv["INV-02"][4]
    assert eff_inv02 < eff_inv01
    assert result.loss_energy_kwh > 0


def test_box_plot_covers_both_inverters(demo_context):
    result = box_plot.run(demo_context)
    assert result.status == ResultStatus.OK
    assert result.metrics["inverters_analyzed"] == 2.0
    assert len(result.tables[0].rows) == 2
    assert result.charts, "box plot must emit a chart"
    fig = result.charts[0].figure
    assert fig["data"], "chart data must be non-empty"
    trace = fig["data"][0]
    assert trace["type"] == "box"
    assert ("y" in trace and len(trace["y"]) > 0) or ("q1" in trace and len(trace["q1"]) > 0)
    assert "layout" in fig and fig["layout"].get("title")
    names = {row[0] for row in result.tables[0].rows}
    assert names == {"INV-01", "INV-02"}
