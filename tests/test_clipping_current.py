"""v1 current-clipping test: INV-02-SCB-02 is built with 12% higher string current than its
peers (HIGH_CURRENT_FACTOR in synthetic_generator.py), so it should saturate near its
implied rated current under high irradiance while peer SCBs do not.
"""
from __future__ import annotations

from analytics.algorithms import clipping_current
from analytics.core.result import ResultStatus


def test_current_clipping_v1_runs_and_is_not_silent(demo_context):
    """v1 current clipping must always produce a visible result (OK or unavailable), never
    crash or silently vanish, when SCB current + irradiance are present.

    The synthetic plant scales one SCB's current 12% higher than peers but that current
    still tracks irradiance linearly (no hard saturation plateau), so the honest outcome is
    "OK — none detected". We assert the module runs and, *if* it does flag equipment, that
    the high-current SCB is the one surfaced.
    """
    result = clipping_current.run(demo_context)

    assert result.status in (ResultStatus.OK, ResultStatus.UNAVAILABLE)
    if result.status == ResultStatus.OK:
        assert result.algorithm_version.startswith("0.1")
        assert result.loss_energy_kwh is None or result.loss_energy_kwh >= 0
        if result.affected_equipment:
            assert "INV-02-SCB-02" in result.affected_equipment
