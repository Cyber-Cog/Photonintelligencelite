"""Fault-injection test: INV-02-SCB-03-STR-02 runs at 55% of its peer strings' current for
the entire dataset window (STRING_OUTLIER_FAULT in synthetic_generator.py) — a sustained
partial underperformance, distinct from the full disconnection tested in
test_disconnected_strings.py.
"""
from __future__ import annotations

from analytics.algorithms import string_outlier
from analytics.core.result import ResultStatus


def test_string_outlier_detected_at_string_granularity(demo_context):
    result = string_outlier.run(demo_context)

    assert result.status == ResultStatus.OK
    assert "INV-02-SCB-03-STR-02" in result.affected_equipment
    assert result.metrics["granularity"] == 1.0  # string-level, not SCB fallback
    assert result.loss_energy_kwh is not None
    assert result.loss_energy_kwh > 0
