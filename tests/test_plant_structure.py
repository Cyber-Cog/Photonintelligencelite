"""Tests for equipment hierarchy inference used by Setup onboarding."""
from __future__ import annotations

from pathlib import Path

from analytics.common.equipment_ids import derive_level
from analytics.common.plant_structure import infer_from_csv, infer_from_ids, normalize_plant_type


def test_derive_level_handles_pandas_na():
    import pandas as pd

    assert derive_level(pd.NA) is None
    assert derive_level(float("nan")) is None
    assert derive_level(None) is None
    assert derive_level("INV-01-SCB-01-STR-01") == "string"


def test_infer_from_ids_mixed_plant():
    ids = [
        "INV-01",
        "INV-01-SCB-01",
        "INV-01-SCB-01-STR-01",
        "INV-01-SCB-01-STR-02",
        "INV-01-SCB-02",
        "INV-01-SCB-02-STR-01",
        "INV-02",
        "INV-02-SCB-01",
        "INV-02-SCB-01-STR-01",
        "INV-02-SCB-01-STR-02",
        "INV-02-SCB-01-STR-03",
        "PLANT-WMS-01",
    ]
    structure = infer_from_ids(ids)
    assert structure.detected
    assert set(structure.inverters) == {"INV-01", "INV-02"}
    assert structure.inverters["INV-01"].scbs["INV-01-SCB-01"].strings_per_scb == 2
    assert structure.inverters["INV-01"].scbs["INV-01-SCB-02"].strings_per_scb == 1
    assert structure.inverters["INV-02"].scbs["INV-02-SCB-01"].strings_per_scb == 3

    arch = structure.to_architecture()
    assert arch["INV-01-SCB-01"]["inverter_id"] == "INV-01"
    assert arch["INV-01-SCB-01"]["strings_per_scb"] == 2
    assert arch["INV-02-SCB-01"]["strings_per_scb"] == 3


def test_infer_from_demo_csv():
    csv_path = Path(__file__).resolve().parent / "fixtures" / "demo_plant_scada.csv"
    structure = infer_from_csv(csv_path, {"Equipment ID": "device_id", "Timestamp": "timestamp"})
    assert structure.detected
    assert set(structure.inverters) == {"INV-01", "INV-02"}
    for inv in ("INV-01", "INV-02"):
        assert len(structure.inverters[inv].scbs) == 4
        for scb in structure.inverters[inv].scbs.values():
            assert scb.strings_per_scb == 4
            assert scb.strings_detected


def test_normalize_plant_type():
    assert normalize_plant_type("single_axis_tracker") == "tracker"
    assert normalize_plant_type("tracker") == "tracker"
    assert normalize_plant_type("fixed_tilt") == "fixed_tilt"
