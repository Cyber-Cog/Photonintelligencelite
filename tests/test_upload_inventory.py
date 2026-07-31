"""Tests for upload file inventory labels vs signal checklist."""
from __future__ import annotations

from analytics.common.complete_analysis_pack import SCADA_COLUMNS
from backend.app.services.upload_inventory import _detected_as_label, _present_fields


def test_complete_pack_label_not_string_current_only():
    present = _present_fields(list(SCADA_COLUMNS))
    label = _detected_as_label("inverter", present, 0, pack_like=True)
    assert label == "Complete Analysis Pack"
    assert label != "String current"


def test_inverter_plus_string_when_both_present():
    present = {"timestamp", "device_id", "ac_power_kw", "dc_current_a", "dc_voltage_v"}
    label = _detected_as_label("inverter", present, 0)
    assert label == "Inverter + string SCADA"


def test_string_only_export():
    present = {"timestamp", "string_id", "dc_current_a", "dc_voltage_v"}
    label = _detected_as_label("other", present, 0)
    assert label == "String current"
