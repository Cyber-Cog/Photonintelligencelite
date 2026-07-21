"""Fault-injection test: INV-01-SCB-02 (15% voltage drop -> module_damage band) and
INV-02-SCB-01 (5% voltage drop -> bypass_diode band), both sustained for 56 hours.
"""
from __future__ import annotations

from analytics.algorithms import module_damage
from analytics.core.result import ResultStatus


def test_module_damage_and_bypass_diode_classification(demo_context):
    result = module_damage.run(demo_context)

    assert result.status == ResultStatus.OK
    assert "INV-01-SCB-02" in result.affected_equipment
    assert "INV-02-SCB-01" in result.affected_equipment

    rows_by_scb = {r[0]: r for r in result.tables[0].rows}
    assert rows_by_scb["INV-01-SCB-02"][2] == "module_damage"
    assert rows_by_scb["INV-02-SCB-01"][2] == "bypass_diode"

    assert result.metrics["module_damage_scb_count"] >= 1
    assert result.metrics["bypass_diode_scb_count"] >= 1
    assert result.loss_energy_kwh > 0
