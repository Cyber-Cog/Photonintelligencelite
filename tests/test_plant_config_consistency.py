"""Plant / architecture capacity consistency — OI-style ±5% + Excel vs Setup ratings."""
from __future__ import annotations

from analytics.common.plant_config_consistency import (
    check_plant_config_consistency,
    snapshot_imported_nameplate,
)


def _base_plant(**overrides):
    plant = {
        "plant_name": "Test Plant",
        "ac_capacity_mw": 0.18,
        "dc_capacity_mwp": 0.22,
        "module_rating_wp": 545.0,
        "inverter_capacity_kw": 90.0,
        "module_technology": "Mono PERC",
        "bifacial": False,
        "timezone": "Asia/Kolkata",
        "equipment_ratings": {"INV-01": 90.0, "INV-02": 90.0},
        "architecture": {
            "INV-01-SCB-01": {"inverter_id": "INV-01", "strings_per_scb": 16, "dc_capacity_kwp": 55.0},
            "INV-02-SCB-01": {"inverter_id": "INV-02", "strings_per_scb": 16, "dc_capacity_kwp": 55.0},
        },
        "imported_equipment_ratings": {"INV-01": 90.0, "INV-02": 90.0},
        "imported_inverter_capacity_kw": 90.0,
        "imported_ac_capacity_mw": 0.18,
        "imported_dc_capacity_mwp": 0.22,
        "architecture_imported": True,
    }
    plant.update(overrides)
    return plant


def test_excel_90_vs_plant_details_100_warns():
    """User bug: pack/Excel rating 90 kW, Plant details default filled as 100 kW."""
    plant = _base_plant(inverter_capacity_kw=100.0)
    issues = check_plant_config_consistency(plant)
    codes = {i.code for i in issues}
    assert "inverter_rating_mismatch" in codes
    assert "imported_inverter_rating_mismatch" in codes
    mismatch = next(i for i in issues if i.code == "inverter_rating_mismatch")
    assert mismatch.severity == "warning"
    assert not mismatch.blocks_analysis
    assert "100" in mismatch.message
    assert "90" in mismatch.message


def test_apply_100_to_all_after_import_still_warns_vs_pack():
    """Apply default 100 kW to all overwrites equipment_ratings but imported snapshot remains 90."""
    plant = _base_plant(
        inverter_capacity_kw=100.0,
        equipment_ratings={"INV-01": 100.0, "INV-02": 100.0},
    )
    issues = check_plant_config_consistency(plant)
    codes = {i.code for i in issues}
    assert "imported_inverter_rating_mismatch" in codes
    assert "imported_equipment_rating_mismatch" in codes
    # Default and equipment now agree — no live default-vs-equipment mismatch
    assert "inverter_rating_mismatch" not in codes


def test_aligned_90_kw_has_no_rating_mismatch():
    plant = _base_plant()
    issues = check_plant_config_consistency(plant)
    codes = {i.code for i in issues}
    assert "inverter_rating_mismatch" not in codes
    assert "imported_inverter_rating_mismatch" not in codes
    assert "ac_capacity_mismatch" not in codes


def test_ac_capacity_mismatch_when_sum_differs_over_5pct():
    # 2 × 90 = 180 kW declared plant AC, but plant form says 0.3 MW = 300 kW (>5%)
    plant = _base_plant(ac_capacity_mw=0.3)
    issues = check_plant_config_consistency(plant)
    assert any(i.code == "ac_capacity_mismatch" for i in issues)


def test_dc_capacity_mismatch_from_architecture_scb_nameplates():
    # Architecture SCBs sum to 110 kWp; plant says 0.5 MWp = 500 kWp
    plant = _base_plant(dc_capacity_mwp=0.5)
    issues = check_plant_config_consistency(plant)
    assert any(i.code == "dc_capacity_mismatch" for i in issues)


def test_orphan_scb_is_blocker():
    plant = _base_plant(
        architecture={"ORPHAN-SCB": {"inverter_id": "", "strings_per_scb": 8}},
    )
    issues = check_plant_config_consistency(plant)
    blockers = [i for i in issues if i.blocks_analysis]
    assert any(i.code == "architecture_scb_missing_inverter" for i in blockers)


def test_empty_architecture_is_warning_not_blocker():
    plant = _base_plant(architecture={})
    issues = check_plant_config_consistency(plant)
    arch = next(i for i in issues if i.code == "architecture_missing")
    assert arch.severity == "warning"
    assert not arch.blocks_analysis


def test_snapshot_imported_nameplate_from_pack_draft():
    snap = snapshot_imported_nameplate(
        {
            "equipment_ratings": {"INV-01": 90.0, "INV-02": 90.0},
            "inverter_capacity_kw": 90.0,
            "ac_capacity_mw": 0.18,
            "dc_capacity_mwp": 0.22,
        }
    )
    assert snap["imported_equipment_ratings"]["INV-01"] == 90.0
    assert snap["imported_inverter_capacity_kw"] == 90.0
    assert snap["imported_ac_capacity_mw"] == 0.18
