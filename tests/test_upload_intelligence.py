"""Tests for upload intelligence: multi-level hierarchy matrix, architecture, module impact."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from analytics.common.complete_analysis_pack import SCADA_COLUMNS
from backend.app.services.upload_intelligence import (
    build_architecture_summary,
    build_hierarchy_levels,
    build_module_impact_preview,
    build_upload_intelligence,
    enrich_file_inventory_item,
)
from backend.app.services.upload_inventory import inventory_item_from_csv


def _signal(level: dict, field_id: str) -> dict:
    return next(s for s in level["signals"] if s["id"] == field_id)


def test_hierarchy_levels_group_by_plant_inverter_scb():
    present = {"timestamp", "poa_w_m2", "ac_power_kw", "device_id", "dc_current_a"}
    levels = build_hierarchy_levels(present)
    assert len(levels) == 4
    plant = next(l for l in levels if l["level_id"] == "plant_wms")
    inv = next(l for l in levels if l["level_id"] == "inverter")
    scb = next(l for l in levels if l["level_id"] == "scb")
    string = next(l for l in levels if l["level_id"] == "string")
    assert plant["detected_count"] >= 2  # timestamp + irradiance (+ plant AC if credited)
    assert inv["detected_count"] >= 2  # id (via device_id) + ac power
    assert scb["detected_count"] >= 1  # dc current
    # device_id must NOT falsely mark both scb_id and string_id present
    assert _signal(scb, "scb_id")["present"] is False
    assert _signal(string, "string_id")["present"] is False
    # Multi-level: DC current is valid at inverter, SCB, and string — not uniquely partitioned
    assert _signal(inv, "dc_current_a")["present"] is True
    assert _signal(scb, "dc_current_a")["present"] is True
    assert _signal(string, "dc_current_a")["present"] is True
    assert _signal(scb, "dc_voltage_v")["present"] is False


def test_hierarchy_inverter_dc_ivp_and_scb_dc_power_not_mutually_exclusive():
    """Inverter may carry DC I/V/P; SCB may carry DC power — no unique division."""
    present = {
        "timestamp",
        "device_id",
        "ac_power_kw",
        "dc_power_kw",
        "dc_current_a",
        "dc_voltage_v",
        "scb_id",
    }
    levels = build_hierarchy_levels(present)
    inv = next(l for l in levels if l["level_id"] == "inverter")
    scb = next(l for l in levels if l["level_id"] == "scb")

    for field in ("dc_power_kw", "dc_current_a", "dc_voltage_v"):
        assert _signal(inv, field)["present"] is True, field
        assert _signal(scb, field)["present"] is True, field

    assert _signal(inv, "dc_current_a")["evidence"] == "mapped_level_tbd"
    assert _signal(scb, "dc_power_kw")["evidence"] == "mapped_level_tbd"
    assert _signal(scb, "scb_id")["present"] is True
    assert _signal(scb, "scb_id")["evidence"] == "confirmed"


def test_hierarchy_by_device_type_distinguishes_confirmed_vs_mapped_tbd():
    present = {"timestamp", "device_id", "dc_current_a", "dc_voltage_v", "dc_power_kw"}
    by_type = {
        "inverter": {"device_id", "dc_power_kw", "dc_current_a", "dc_voltage_v"},
        "scb": set(),
    }
    levels = build_hierarchy_levels(present, by_device_type=by_type)
    inv = next(l for l in levels if l["level_id"] == "inverter")
    scb = next(l for l in levels if l["level_id"] == "scb")

    assert _signal(inv, "dc_current_a")["evidence"] == "confirmed"
    assert _signal(inv, "dc_power_kw")["evidence"] == "confirmed"
    # Still present under SCB as job-available (valid metric) but not confirmed at scb device_type
    assert _signal(scb, "dc_current_a")["present"] is True
    assert _signal(scb, "dc_current_a")["evidence"] == "mapped_level_tbd"
    assert _signal(scb, "dc_power_kw")["evidence"] == "mapped_level_tbd"


def test_architecture_inferred_from_device_ids(tmp_path: Path):
    csv = tmp_path / "input.csv"
    rows = [
        {"Timestamp": "2024-01-01 10:00", "Equipment ID": "INV-01", "AC Power kW": 100},
        {"Timestamp": "2024-01-01 10:05", "Equipment ID": "INV-01-SCB-01", "DC Current A": 5.2},
        {"Timestamp": "2024-01-01 10:05", "Equipment ID": "INV-01-SCB-01-STR-01", "DC Current A": 1.1},
    ]
    pd.DataFrame(rows).to_csv(csv, index=False)
    suggestions = [
        type("S", (), {"column_name": "Timestamp", "canonical_field": "timestamp"})(),
        type("S", (), {"column_name": "Equipment ID", "canonical_field": "device_id"})(),
        type("S", (), {"column_name": "AC Power kW", "canonical_field": "ac_power_kw"})(),
        type("S", (), {"column_name": "DC Current A", "canonical_field": "dc_current_a"})(),
    ]
    arch = build_architecture_summary(plant_config={}, csv_path=csv, suggestions=suggestions)
    assert arch["detected"] is True
    assert arch["inverter_count"] >= 1
    assert arch["scb_count"] >= 1


def test_module_impact_blocks_clipping_without_irradiance():
    suggestions = [
        type("S", (), {"column_name": "AC", "canonical_field": "ac_power_kw"})(),
        type("S", (), {"column_name": "TS", "canonical_field": "timestamp"})(),
    ]
    impact = build_module_impact_preview(
        suggestions=suggestions,
        plant_config={"equipment_ratings": {"INV-01": 100}},
        architecture_summary={"detected": True},
    )
    blocked_ids = {m["algorithm_id"] for m in impact["blocked_modules"]}
    assert "clipping_power" in blocked_ids
    assert impact["blocked_count"] >= 1


def test_inventory_item_includes_hierarchy(tmp_path: Path):
    csv = tmp_path / "pack.csv"
    pd.DataFrame({c: [1] for c in SCADA_COLUMNS[:8]}).to_csv(csv, index=False)
    item = inventory_item_from_csv(csv, display_name="pack.csv")
    assert item.get("hierarchy_levels")
    assert len(item["hierarchy_levels"]) == 4


def test_enrich_rebuilds_hierarchy_from_signals_present():
    item = enrich_file_inventory_item({"signals_present": ["timestamp", "dc_current_a"]})
    scb = next(l for l in item["hierarchy_levels"] if l["level_id"] == "scb")
    inv = next(l for l in item["hierarchy_levels"] if l["level_id"] == "inverter")
    assert scb["detected_count"] >= 1
    assert _signal(inv, "dc_current_a")["present"] is True


def test_module_impact_marks_module_damage_preliminary_not_ready():
    """Column-only voltage must not count Module Damage as confirmed ready."""
    suggestions = [
        type("S", (), {"column_name": "V", "canonical_field": "dc_voltage_v"})(),
        type("S", (), {"column_name": "TS", "canonical_field": "timestamp"})(),
        type("S", (), {"column_name": "ID", "canonical_field": "device_id"})(),
    ]
    impact = build_module_impact_preview(
        suggestions=suggestions,
        plant_config={"architecture": {"SCB-01": {"inverter_id": "INV-01", "strings_per_scb": 8}}},
        architecture_summary={"detected": True},
    )
    may_ids = {m["algorithm_id"] for m in impact.get("may_run_modules") or []}
    blocked_ids = {m["algorithm_id"] for m in impact["blocked_modules"]}
    assert "preliminary" in impact["preview_note"].lower()
    assert "module_damage" in may_ids
    assert "module_damage" not in blocked_ids
    assert impact["may_run_count"] >= 1


def test_build_upload_intelligence_bundle():
    suggestions = [
        type("S", (), {"column_name": "TS", "canonical_field": "timestamp"})(),
        type("S", (), {"column_name": "POA", "canonical_field": "poa_w_m2"})(),
        type("S", (), {"column_name": "AC", "canonical_field": "ac_power_kw"})(),
    ]
    bundle = build_upload_intelligence(
        suggestions=suggestions,
        plant_config={},
        csv_path=None,
        file_inventory=[{"filename": "a.csv", "signals_present": ["timestamp", "ac_power_kw"]}],
    )
    assert bundle["hierarchy_overview"]
    assert bundle["architecture_summary"]["source"] == "not_detected"
    assert "module_impact_preview" in bundle
    assert bundle["file_inventory"][0].get("hierarchy_levels")
    # AC power credited at plant + inverter (multi-level), not uniquely locked
    plant = next(l for l in bundle["hierarchy_overview"] if l["level_id"] == "plant_wms")
    inv = next(l for l in bundle["hierarchy_overview"] if l["level_id"] == "inverter")
    assert _signal(plant, "ac_power_kw")["present"] is True
    assert _signal(inv, "ac_power_kw")["present"] is True
