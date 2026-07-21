"""Fault-injection tolerance test for disconnected-string detection.

Ground truth (tests/fixtures/synthetic_generator.py DS_FAULT): INV-01-SCB-01-STR-01's
current is zeroed for 6 hours on day 2 (well past the 360-minute persistence threshold),
so the parent SCB (INV-01-SCB-01) must be confirmed with 1 missing string.
"""
from __future__ import annotations

from analytics.algorithms import disconnected_strings
from analytics.core.result import ResultStatus


def test_disconnected_string_is_detected_on_correct_scb(demo_context, ground_truth):
    result = disconnected_strings.run(demo_context)

    assert result.status == ResultStatus.OK
    expected_scb = "INV-01-SCB-01"
    assert expected_scb in result.affected_equipment
    assert result.loss_energy_kwh is not None
    assert result.loss_energy_kwh > 0

    row = next(r for r in result.tables[0].rows if r[0] == expected_scb)
    max_missing_strings = row[2]
    assert max_missing_strings >= 1

    assert result.evidence.time_range_start is not None
    assert result.evidence.affected_sample_count > 0


def test_disconnected_string_does_not_flag_healthy_scbs(demo_context):
    result = disconnected_strings.run(demo_context)
    healthy_scbs = {"INV-01-SCB-03", "INV-01-SCB-04", "INV-02-SCB-04"}
    flagged = set(result.affected_equipment)
    assert not healthy_scbs.intersection(flagged)
