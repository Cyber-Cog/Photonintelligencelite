"""Tests for upload intelligence: hierarchy matrix, architecture, module impact."""
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


def test_hierarchy_levels_group_by_plant_inverter_scb():
    present = {"timestamp", "poa_w_m2", "ac_power_kw", "device_id", "dc_current_a"}
    levels = build_hierarchy_levels(present)
    assert len(levels) == 4
    plant = next(l for l in levels if l["level_id"] == "plant_wms")
    inv = next(l for l in levels if l["level_id"] == "inverter")
    scb = next(l for l in levels if l["level_id"] == "scb")
    string = next(l for l in levels if l["level_id"] == "string")
    assert plant["detected_count"] >= 2  # timestamp + irradiance
    assert inv["detected_count"] >= 2  # id (via device_id) + ac power
    assert scb["detected_count"] >= 1  # dc current
    # device_id must NOT falsely mark both scb_id and string_id present
    scb_id = next(s for s in scb["signals"] if s["id"] == "scb_id")
    str_id = next(s for s in string["signals"] if s["id"] == "string_id")
    assert scb_id["present"] is False
    assert str_id["present"] is False
    dc = next(s for s in scb["signals"] if s["id"] == "dc_current_a")
    assert dc["present"] is True
    volt = next(s for s in scb["signals"] if s["id"] == "dc_voltage_v")
    assert volt["present"] is False


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
    assert scb["detected_count"] >= 1


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
