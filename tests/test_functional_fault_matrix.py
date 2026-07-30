"""Fault detection functional matrix — MUST fire / MUST NOT fire vs reference logics.

Uses synthetic mini-plants (helpers_fault_context) plus the shared demo_context fixture.
"""
from __future__ import annotations

import dataclasses

import pandas as pd

from analytics.algorithms import (
    box_plot,
    clipping_current,
    clipping_power,
    disconnected_strings,
    inverter_efficiency,
    module_damage,
    string_outlier,
)
from analytics.core.result import ResultStatus
from tests.helpers_fault_context import (
    build_context,
    make_clipping_power_plant,
    make_efficiency_plant,
    make_scb_current_plant,
    make_string_current_plant,
    make_voltage_damage_plant,
)


# ---------------------------------------------------------------------------
# Disconnected strings
# ---------------------------------------------------------------------------

def test_ds_must_fire_one_of_four_strings_missing_for_7h():
    """1/4 string open for ≥360 min → confirmed DS (PIC missing_ratio ≥ 0.85).

    Currents stay under Isc_stc×strings (outlier ceiling) so peer SCBs remain in the
    virtual-reference pool — same gate as PIC ``ds_detection``.
    """
    frame = make_scb_current_plant(
        hours=8.0,
        fault_current_a=27.0,  # ~36 - 9 ≈ one string of ~9 A
        fault_duration_hours=7.0,
        fault_start_hour=0.5,
    )
    ctx = build_context(frame)
    result = disconnected_strings.run(ctx)
    assert result.status == ResultStatus.OK, result.summary
    assert "INV-01-SCB-01" in result.affected_equipment
    assert result.loss_energy_kwh is not None and result.loss_energy_kwh > 0


def test_ds_must_not_fire_brief_30min_drop():
    frame = make_scb_current_plant(
        hours=8.0,
        fault_current_a=27.0,
        fault_duration_hours=0.5,  # 30 min << 360 persistence
        fault_start_hour=2.0,
    )
    ctx = build_context(frame)
    result = disconnected_strings.run(ctx)
    assert "INV-01-SCB-01" not in (result.affected_equipment or [])
    assert result.status in (ResultStatus.OK, ResultStatus.UNAVAILABLE)


def test_ds_must_not_fire_healthy_equal_scbs():
    frame = make_scb_current_plant(
        hours=8.0,
        fault_current_a=40.0,  # same as healthy — no drop
        fault_duration_hours=8.0,
    )
    ctx = build_context(frame)
    result = disconnected_strings.run(ctx)
    assert result.status == ResultStatus.UNAVAILABLE or not result.affected_equipment


def test_ds_must_not_fire_spare_scb(demo_context):
    plant = dataclasses.replace(demo_context.plant)
    arch = {k: dict(v) for k, v in plant.architecture.items()}
    arch["INV-01-SCB-01"]["spare_flag"] = True
    plant = dataclasses.replace(plant, architecture=arch)
    ctx = dataclasses.replace(demo_context, plant=plant)
    result = disconnected_strings.run(ctx)
    assert "INV-01-SCB-01" not in result.affected_equipment


def test_ds_fires_on_demo_ground_truth(demo_context, ground_truth):
    result = disconnected_strings.run(demo_context)
    assert result.status == ResultStatus.OK
    assert "INV-01-SCB-01" in result.affected_equipment
    healthy = {"INV-01-SCB-03", "INV-01-SCB-04", "INV-02-SCB-04"}
    assert not healthy.intersection(set(result.affected_equipment))


def test_ds_standalone_smb_with_architecture_backfill():
    """OEM SMB-01 ids must still detect after architecture inverter_id backfill."""
    frame = make_scb_current_plant(hours=8.0, fault_current_a=27.0, fault_duration_hours=7.0)
    # Rewrite SCB ids to standalone SMB style
    rename = {f"INV-01-SCB-{i:02d}": f"SMB-{i:02d}" for i in range(1, 5)}
    frame = frame.copy()
    for col in ("device_id", "scb_id"):
        frame[col] = frame[col].map(lambda x, m=rename: m.get(x, x))
    frame.loc[frame["device_type"] == "scb", "inverter_id"] = pd.NA

    arch = {
        f"SMB-{i:02d}": {"inverter_id": "INV-01", "strings_per_scb": 4, "modules_per_string": 11}
        for i in range(1, 5)
    }
    ctx = build_context(frame, architecture=arch)
    result = disconnected_strings.run(ctx)
    assert result.status == ResultStatus.OK, result.summary
    assert "SMB-01" in result.affected_equipment


# ---------------------------------------------------------------------------
# Module damage / bypass
# ---------------------------------------------------------------------------

def test_module_damage_must_fire_15pct_voltage_drop():
    frame = make_voltage_damage_plant(damage_drop_pct=0.15, hours=8.0)
    ctx = build_context(frame)
    result = module_damage.run(ctx)
    assert result.status == ResultStatus.OK, result.summary
    assert "INV-01-SCB-02" in result.affected_equipment
    rows = {r[0]: r for r in result.tables[0].rows}
    assert rows["INV-01-SCB-02"][2] == "module_damage"


def test_bypass_diode_must_fire_5pct_voltage_drop():
    frame = make_voltage_damage_plant(damage_scb="INV-01-SCB-03", damage_drop_pct=0.05, hours=8.0)
    ctx = build_context(frame)
    result = module_damage.run(ctx)
    assert result.status == ResultStatus.OK, result.summary
    assert "INV-01-SCB-03" in result.affected_equipment
    rows = {r[0]: r for r in result.tables[0].rows}
    assert rows["INV-01-SCB-03"][2] == "bypass_diode"


def test_module_damage_must_not_fire_1pct_noise():
    frame = make_voltage_damage_plant(damage_drop_pct=0.01, hours=8.0)
    ctx = build_context(frame)
    result = module_damage.run(ctx)
    assert "INV-01-SCB-02" not in (result.affected_equipment or [])
    assert result.status in (ResultStatus.OK, ResultStatus.UNAVAILABLE)


def test_module_damage_demo_ground_truth(demo_context):
    result = module_damage.run(demo_context)
    assert result.status == ResultStatus.OK
    assert "INV-01-SCB-02" in result.affected_equipment
    assert "INV-02-SCB-01" in result.affected_equipment


# ---------------------------------------------------------------------------
# String outlier
# ---------------------------------------------------------------------------

def test_string_outlier_must_fire_even_when_rows_are_time_major():
    """Regression: persistence must not depend on equipment-major CSV order."""
    frame = make_string_current_plant(outlier_a=4.0, healthy_a=10.0, hours=3.0)
    # Explicitly time-major (all strings at t, then t+1) — common after standardize merges.
    frame = frame.sort_values(["timestamp_utc", "string_id"]).reset_index(drop=True)
    ctx = build_context(frame)
    result = string_outlier.run(ctx)
    assert result.status == ResultStatus.OK, result.summary
    assert "INV-01-SCB-01-STR-02" in result.affected_equipment


def test_string_outlier_must_not_fire_equal_strings():
    frame = make_string_current_plant(outlier_a=10.0, healthy_a=10.0, hours=3.0)
    ctx = build_context(frame)
    result = string_outlier.run(ctx)
    assert result.status == ResultStatus.UNAVAILABLE or not result.affected_equipment


def test_string_outlier_demo_ground_truth(demo_context):
    result = string_outlier.run(demo_context)
    assert result.status == ResultStatus.OK
    assert "INV-02-SCB-03-STR-02" in result.affected_equipment


# ---------------------------------------------------------------------------
# Clipping by power
# ---------------------------------------------------------------------------

def test_clipping_power_must_fire_at_rated_with_rising_gti():
    frame = make_clipping_power_plant(must_clip=True)
    ctx = build_context(frame, equipment_ratings={"INV-01": 90.0})
    result = clipping_power.run(ctx)
    assert result.status == ResultStatus.OK, result.summary
    assert "INV-01" in result.affected_equipment
    assert result.loss_energy_kwh is not None and result.loss_energy_kwh > 0


def test_clipping_power_must_not_fire_well_below_rated():
    frame = make_clipping_power_plant(must_clip=False)
    ctx = build_context(frame, equipment_ratings={"INV-01": 90.0})
    result = clipping_power.run(ctx)
    assert "INV-01" not in (result.affected_equipment or [])
    assert result.status in (ResultStatus.OK, ResultStatus.UNAVAILABLE)


def test_clipping_power_demo_oversized_inv(demo_context):
    result = clipping_power.run(demo_context)
    assert result.status == ResultStatus.OK
    assert "INV-01" in result.affected_equipment


# ---------------------------------------------------------------------------
# Clipping by current (v1) — honest weak-signal expectations
# ---------------------------------------------------------------------------

def test_clipping_current_runs_on_demo_without_crash(demo_context):
    result = clipping_current.run(demo_context)
    assert result.status in (ResultStatus.OK, ResultStatus.UNAVAILABLE)
    if result.affected_equipment:
        assert "INV-02-SCB-02" in result.affected_equipment


# ---------------------------------------------------------------------------
# Inverter efficiency / underperformance proxy + box plot
# ---------------------------------------------------------------------------

def test_efficiency_must_rank_degraded_inverter_worse():
    frame = make_efficiency_plant(degraded_inv="INV-02", factor=0.90)
    ctx = build_context(frame)
    result = inverter_efficiency.run(ctx)
    assert result.status == ResultStatus.OK, result.summary
    # Table rows: inverter, efficiency, loss — INV-02 should have lower efficiency / more loss
    rows = {r[0]: r for r in result.tables[0].rows}
    assert "INV-01" in rows and "INV-02" in rows
    # columns: Inverter, DC Energy, AC Energy, Loss, Efficiency (%)
    assert float(rows["INV-02"][4]) < float(rows["INV-01"][4])


def test_efficiency_demo_degraded_inv(demo_context, ground_truth):
    result = inverter_efficiency.run(demo_context)
    assert result.status == ResultStatus.OK
    assert ground_truth.low_efficiency_inverter in result.affected_equipment or any(
        ground_truth.low_efficiency_inverter in str(r) for r in result.tables[0].rows
    )


def test_box_plot_runs_and_surfaces_stats(demo_context):
    result = box_plot.run(demo_context)
    assert result.status == ResultStatus.OK
    assert result.tables or result.charts


# ---------------------------------------------------------------------------
# Reference gaps documented as expected absences (not failures)
# ---------------------------------------------------------------------------

def test_soiling_and_power_limitation_not_in_mvp():
    """Reference codex engines not ported — document residual scope via prerequisites."""
    import analytics.algorithms  # noqa: F401 — populate registry
    from analytics.common.prerequisites import ALGORITHM_PREREQUISITES
    from analytics.core.registry import get_registry

    mvp = set(ALGORITHM_PREREQUISITES.keys())
    registered = set(get_registry().keys())
    assert "soiling" not in mvp and "soiling" not in registered
    assert "power_limitation" not in mvp and "power_limitation" not in registered
    assert "inverter_shutdown" not in mvp
    assert "disconnected_strings" in mvp
    assert "clipping_power" in mvp
