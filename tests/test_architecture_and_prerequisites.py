"""Architecture Excel template / parse / pattern + prerequisite honesty."""
from __future__ import annotations

from analytics.common.architecture_excel import (
    apply_smb_pattern,
    build_template_bytes,
    parse_architecture_excel,
)
from analytics.common.prerequisites import evaluate_prerequisites, missing_fields_for_algorithm


def test_template_roundtrip():
    raw = build_template_bytes(example_inverters=2, scbs_per_inverter=3, strings_per_scb=8, default_rated_kw=1500)
    parsed = parse_architecture_excel(raw)
    assert parsed.ok
    assert len(parsed.inverters) == 2
    assert len(parsed.architecture) == 6
    assert parsed.equipment_ratings["INV-01"] == 1500.0
    assert parsed.architecture["INV-01-SCB-01"]["strings_per_scb"] == 8


def test_pattern_applies_to_selected():
    existing = [
        {
            "inverter_id": "KEEP-01",
            "rated_kw": 1000,
            "scbs": [{"scb_id": "KEEP-01-SCB-01", "strings_per_scb": 10, "strings_detected": False}],
        }
    ]
    out = apply_smb_pattern(
        ["INV-01", "INV-02"],
        smbs_per_inverter=2,
        strings_per_smb=24,
        rated_kw=1500,
        existing=existing,
    )
    ids = {i["inverter_id"] for i in out}
    assert ids == {"KEEP-01", "INV-01", "INV-02"}
    inv01 = next(i for i in out if i["inverter_id"] == "INV-01")
    assert len(inv01["scbs"]) == 2
    assert inv01["scbs"][0]["strings_per_scb"] == 24


def test_prerequisites_block_clipping_current_without_irr():
    rows = evaluate_prerequisites(
        available_fields={"dc_current_a"},
        has_architecture=True,
        has_equipment_ratings=True,
        algorithm_ids=["clipping_current"],
    )
    assert len(rows) == 1
    assert rows[0]["will_run"] is False
    assert "You have not provided" in rows[0]["message"]


def test_prerequisites_run_when_complete():
    rows = evaluate_prerequisites(
        available_fields={"dc_current_a", "poa_w_m2", "ac_power_kw", "dc_power_kw"},
        has_architecture=True,
        has_equipment_ratings=True,
        algorithm_ids=["clipping_current", "box_plot"],
    )
    by_id = {r["algorithm_id"]: r for r in rows}
    assert by_id["clipping_current"]["will_run"] is True
    assert by_id["box_plot"]["will_run"] is True


def test_missing_fields_for_orchestrator():
    missing = missing_fields_for_algorithm("clipping_power", {"ac_power_kw"})
    assert "poa_w_m2" in missing or "ghi_w_m2" in missing


def test_populated_columns_ignores_all_null_schema():
    """Empty schema columns must not count as available (Will run vs Needs input)."""
    import pandas as pd

    from analytics.core.context import CanonicalDataAccess

    df = pd.DataFrame(
        {
            "timestamp_utc": pd.to_datetime(["2024-01-01T00:00:00Z", "2024-01-01T00:01:00Z"]),
            "ac_power_kw": [100.0, 110.0],
            "poa_w_m2": [800.0, 820.0],
            "dc_power_kw": [None, None],
            "dc_current_a": [None, None],
            "device_type": ["inverter", "inverter"],
        }
    )
    access = CanonicalDataAccess.from_frame(df)
    present = access.populated_columns()
    assert "ac_power_kw" in present and "poa_w_m2" in present
    assert "dc_power_kw" not in present
    assert "dc_current_a" not in present

    rows = evaluate_prerequisites(
        available_fields=present,
        has_architecture=True,
        has_equipment_ratings=True,
    )
    by_id = {r["algorithm_id"]: r for r in rows}
    assert by_id["clipping_power"]["will_run"] is True
    assert by_id["inverter_efficiency"]["will_run"] is False
    assert by_id["disconnected_strings"]["will_run"] is False
