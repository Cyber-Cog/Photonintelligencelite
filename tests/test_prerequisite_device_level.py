"""Device-level prerequisite honesty: Validation will_run must match runtime availability.

Module Damage needs SCB-level DC voltage — a mapped ``dc_voltage_v`` column on inverter
or string-only rows must not produce a false green on Validation / Upload.
"""
from __future__ import annotations

import pandas as pd

from analytics.algorithms import module_damage
from analytics.common.config_loader import resolve_thresholds
from analytics.common.prerequisites import (
    evaluate_prerequisites,
    missing_fields_for_algorithm,
)
from analytics.core.context import (
    AnalysisContext,
    CanonicalDataAccess,
    JobMeta,
    PlantConfig,
    ResolvedMapping,
)
from analytics.core.orchestrator import AnalysisOrchestrator
from analytics.core.result import ResultStatus
from analytics.core.registry import get_registry


def _plant() -> PlantConfig:
    return PlantConfig(
        plant_name="Test",
        ac_capacity_mw=1.0,
        dc_capacity_mwp=1.2,
        module_rating_wp=540,
        inverter_capacity_kw=100,
        module_technology="mono",
        bifacial=False,
        timezone="UTC",
        strings_per_scb=8,
        plant_type="fixed_tilt",
        architecture={
            "INV-01-SCB-01": {"inverter_id": "INV-01", "strings_per_scb": 8},
            "INV-01-SCB-02": {"inverter_id": "INV-01", "strings_per_scb": 8},
        },
        equipment_ratings={"INV-01": 100.0},
    )


def _ctx(df: pd.DataFrame) -> AnalysisContext:
    plant = _plant()
    return AnalysisContext(
        canonical=CanonicalDataAccess.from_frame(df),
        plant=plant,
        mapping=ResolvedMapping(column_to_canonical={}, confidence_by_column={}),
        timezone="UTC",
        sample_interval_minutes=5.0,
        thresholds=resolve_thresholds(plant.plant_type, plant.bifacial),
        job_meta=JobMeta(job_id="test-level", created_at="2024-01-01T00:00:00Z", trace_id="test-level"),
    )


def test_module_damage_false_green_inverter_only_voltage():
    """Voltage on inverter rows only → will_run False and algorithm unavailable."""
    df = pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime(
                ["2024-06-01T10:00:00Z", "2024-06-01T10:05:00Z"]
            ),
            "device_type": ["inverter", "inverter"],
            "device_id": ["INV-01", "INV-01"],
            "inverter_id": ["INV-01", "INV-01"],
            "scb_id": [None, None],
            "ac_power_kw": [80.0, 82.0],
            "dc_voltage_v": [620.0, 622.0],  # present — but NOT on SCB rows
            "dc_current_a": [None, None],
            "poa_w_m2": [800.0, 810.0],
        }
    )
    access = CanonicalDataAccess.from_frame(df)
    present = access.populated_columns()
    by_type = access.populated_columns_by_device_type()

    assert "dc_voltage_v" in present
    assert "dc_voltage_v" not in by_type.get("scb", set())

    rows = evaluate_prerequisites(
        available_fields=present,
        available_by_device_type=by_type,
        has_architecture=True,
        has_equipment_ratings=True,
        algorithm_ids=["module_damage"],
    )
    assert rows[0]["will_run"] is False
    assert "SCB-level" in rows[0]["message"] or "scb:dc_voltage_v" in str(rows[0]["missing_fields"])

    missing = missing_fields_for_algorithm(
        "module_damage", present, available_by_device_type=by_type
    )
    assert "dc_voltage_v" in missing

    result = module_damage.run(_ctx(df))
    assert result.status == ResultStatus.UNAVAILABLE
    assert "SCB-level" in result.summary


def test_module_damage_will_run_matches_runtime_with_scb_voltage():
    ts = pd.to_datetime(
        ["2024-06-01T10:00:00Z", "2024-06-01T10:05:00Z", "2024-06-01T10:10:00Z", "2024-06-01T10:15:00Z"]
        * 2
    )
    n = len(ts) // 2
    df = pd.DataFrame(
        {
            "timestamp_utc": ts,
            "device_type": ["scb"] * n + ["scb"] * n,
            "device_id": ["INV-01-SCB-01"] * n + ["INV-01-SCB-02"] * n,
            "scb_id": ["INV-01-SCB-01"] * n + ["INV-01-SCB-02"] * n,
            "inverter_id": ["INV-01"] * (2 * n),
            "dc_voltage_v": [620.0] * n + [620.0 * 0.85] * n,  # 15% drop on SCB-02
            "dc_current_a": [10.0] * (2 * n),
            "ac_power_kw": [None] * (2 * n),
            "poa_w_m2": [800.0] * (2 * n),
        }
    )
    access = CanonicalDataAccess.from_frame(df)
    present = access.populated_columns()
    by_type = access.populated_columns_by_device_type()

    rows = evaluate_prerequisites(
        available_fields=present,
        available_by_device_type=by_type,
        has_architecture=True,
        has_equipment_ratings=True,
        algorithm_ids=["module_damage"],
    )
    assert rows[0]["will_run"] is True, rows[0]

    missing = missing_fields_for_algorithm(
        "module_damage", present, available_by_device_type=by_type
    )
    assert not missing

    result = module_damage.run(_ctx(df))
    assert result.status == ResultStatus.OK


def test_module_damage_string_voltage_not_scb():
    """String-level voltage must not satisfy Module Damage SCB requirement."""
    df = pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime(["2024-06-01T10:00:00Z", "2024-06-01T10:05:00Z"]),
            "device_type": ["string", "string"],
            "device_id": ["INV-01-SCB-01-STR-01", "INV-01-SCB-01-STR-01"],
            "string_id": ["INV-01-SCB-01-STR-01", "INV-01-SCB-01-STR-01"],
            "scb_id": ["INV-01-SCB-01", "INV-01-SCB-01"],
            "inverter_id": ["INV-01", "INV-01"],
            "dc_voltage_v": [40.0, 40.5],
            "dc_current_a": [8.0, 8.1],
            "poa_w_m2": [800.0, 810.0],
        }
    )
    access = CanonicalDataAccess.from_frame(df)
    by_type = access.populated_columns_by_device_type()
    assert "dc_voltage_v" in by_type.get("string", set())
    assert "dc_voltage_v" not in by_type.get("scb", set())

    rows = evaluate_prerequisites(
        available_fields=access.populated_columns(),
        available_by_device_type=by_type,
        has_architecture=True,
        algorithm_ids=["module_damage"],
    )
    assert rows[0]["will_run"] is False

    result = module_damage.run(_ctx(df))
    assert result.status == ResultStatus.UNAVAILABLE


def test_upload_preview_no_false_green_for_module_damage():
    """Column-only preview must not confirm Module Damage will_run."""
    rows = evaluate_prerequisites(
        available_fields={"dc_voltage_v", "poa_w_m2", "ac_power_kw"},
        has_architecture=True,
        has_equipment_ratings=True,
        level_evidence=False,
        algorithm_ids=["module_damage", "kpis"],
    )
    by_id = {r["algorithm_id"]: r for r in rows}
    assert by_id["module_damage"]["will_run"] is False
    assert by_id["module_damage"]["preliminary"] is True
    assert by_id["kpis"]["will_run"] is True


def test_orchestrator_skips_module_damage_without_scb_voltage():
    df = pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime(["2024-06-01T10:00:00Z"]),
            "device_type": ["inverter"],
            "device_id": ["INV-01"],
            "inverter_id": ["INV-01"],
            "scb_id": [None],
            "string_id": [None],
            "ac_power_kw": [100.0],
            "dc_voltage_v": [600.0],
            "dc_power_kw": [110.0],
            "dc_current_a": [None],
            "poa_w_m2": [800.0],
            "ghi_w_m2": [None],
            "module_temp_c": [None],
            "ambient_temp_c": [None],
            "energy_kwh": [None],
        }
    )
    registry = {k: v for k, v in get_registry().items() if k in {"module_damage", "kpis"}}
    run = AnalysisOrchestrator(algorithms=registry).run(_ctx(df))
    md = next(r for r in run.results if r.algorithm_id == "module_damage")
    assert md.status == ResultStatus.UNAVAILABLE
    assert "SCB-level" in md.summary or "DC voltage" in md.summary


def test_disconnected_strings_accepts_string_or_scb_current():
    df = pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime(["2024-06-01T10:00:00Z", "2024-06-01T10:05:00Z"]),
            "device_type": ["string", "string"],
            "string_id": ["S1", "S1"],
            "scb_id": ["SCB-01", "SCB-01"],
            "inverter_id": ["INV-01", "INV-01"],
            "dc_current_a": [5.0, 5.1],
            "poa_w_m2": [800.0, 810.0],
        }
    )
    access = CanonicalDataAccess.from_frame(df)
    rows = evaluate_prerequisites(
        available_fields=access.populated_columns(),
        available_by_device_type=access.populated_columns_by_device_type(),
        has_architecture=True,
        algorithm_ids=["disconnected_strings"],
    )
    assert rows[0]["will_run"] is True
