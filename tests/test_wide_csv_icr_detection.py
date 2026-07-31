"""Wide CSV / ICR detection: trendreport-style exports and permutations."""
from __future__ import annotations

import gzip
import io
from pathlib import Path

import pandas as pd
import pytest

from analytics.common.aliasing import score_column
from analytics.common.config_loader import load_aliases
from analytics.common.equipment_ids import derive_level, extract_parent_icr
from analytics.common.wide_headers import parse_wide_device_column
from backend.app.config import get_settings
from backend.app.services.mapping_service import read_header, suggest_mapping
from backend.app.services.upload_ai_check import run_upload_integrity_check
from backend.app.services.upload_intelligence import build_hierarchy_levels, build_upload_intelligence
from backend.app.services.wide_csv_reshape import maybe_reshape_wide_csv, sniff_delimiter

FIXTURE = Path(__file__).parent / "fixtures" / "trendreport_essp_icr_wide.csv"
REAL_DOWNLOAD = Path(r"c:\Users\ayush.r\Downloads\trendreport_1784812439579_8684.csv")


@pytest.fixture(autouse=True)
def _reload_aliases():
    load_aliases.cache_clear()
    yield
    load_aliases.cache_clear()


def _write_csv(path: Path, header: str, rows: list[str], *, delim: str = ",") -> None:
    path.write_text(delim.join(header.split(",")) + "\n" + "\n".join(rows) + "\n", encoding="utf-8")


@pytest.mark.parametrize(
    "header,equip,metric,icr",
    [
        ("ESSP_20MW ICR1 Inverter 1 Active Power (kW)", "ICR1-INV-01", "AC Power (kW)", "ICR1"),
        ("ESSP_20MW ICR3 Inverter 4 DC Bus Voltage (V)", "ICR3-INV-04", "DC Voltage (V)", "ICR3"),
        ("INV1_Pac", "INV-01", "AC Power (kW)", None),
        ("Inverter_02_DC Current (A)", "INV-02", "DC Current (A)", None),
        ("ICR-2 INV3 Active Power (kW)", "ICR2-INV-03", "AC Power (kW)", "ICR2"),
        ("PlantA ICR1 Inverter 1 DC Power (kW)", "ICR1-INV-01", "DC Power (kW)", "ICR1"),
    ],
)
def test_parse_wide_device_column_variants(header, equip, metric, icr):
    p = parse_wide_device_column(header)
    assert p is not None
    assert p.equipment_id == equip
    assert p.metric == metric
    assert p.icr_id == icr


def test_wide_prefix_alias_scores_before_melt():
    c = score_column("ESSP_20MW ICR1 Inverter 2 Active Power (kW)")
    assert c.canonical_field == "ac_power_kw"
    assert c.confidence >= 0.9


def test_icr_id_alias_exact():
    c = score_column("ICR ID")
    assert c.canonical_field == "icr_id"
    assert c.confidence == 1.0


def test_hierarchy_omits_empty_icr():
    levels = build_hierarchy_levels({"timestamp", "device_id", "ac_power_kw"})
    ids = [lv["level_id"] for lv in levels]
    assert "icr" not in ids
    assert "inverter" in ids


def test_hierarchy_includes_icr_when_present():
    levels = build_hierarchy_levels({"timestamp", "icr_id", "device_id", "ac_power_kw"})
    icr = next(lv for lv in levels if lv["level_id"] == "icr")
    assert icr["optional"] is True
    assert icr["detected_count"] == 1


def test_derive_level_icr_prefixed_inverter():
    assert derive_level("ICR1-INV-01") == "inverter"
    assert extract_parent_icr("ICR1-INV-01") == "ICR1"
    assert derive_level("ICR2") == "icr"


def test_reshape_fixture_maps_signals(tmp_path: Path):
    assert FIXTURE.exists(), "missing trendreport fixture"
    dst = tmp_path / "wide.csv"
    dst.write_bytes(FIXTURE.read_bytes())
    rep = maybe_reshape_wide_csv(dst)
    assert rep.reshaped
    assert len(rep.inverters_found) == 12
    assert set(rep.icr_ids) == {"ICR1", "ICR2", "ICR3"}
    cols = read_header(dst)
    assert "Equipment ID" in cols
    assert "ICR ID" in cols
    assert "AC Power (kW)" in cols
    sug = suggest_mapping(cols)
    fields = {s.canonical_field for s in sug if s.canonical_field}
    assert {"timestamp", "device_id", "icr_id", "ac_power_kw", "dc_power_kw"} <= fields
    intel = build_upload_intelligence(suggestions=sug, plant_config=None, csv_path=dst)
    level_ids = {h["level_id"] for h in intel["hierarchy_overview"]}
    assert "icr" in level_ids
    inv = next(h for h in intel["hierarchy_overview"] if h["level_id"] == "inverter")
    scb = next(h for h in intel["hierarchy_overview"] if h["level_id"] == "scb")
    inv_by_id = {s["id"]: s for s in inv["signals"]}
    scb_by_id = {s["id"]: s for s in scb["signals"]}
    # Wide inverter melt: DC power / current / voltage credited at inverter (and valid at SCB)
    assert inv_by_id["dc_power_kw"]["present"] is True
    if "dc_current_a" in fields:
        assert inv_by_id["dc_current_a"]["present"] is True
        assert scb_by_id["dc_current_a"]["present"] is True
    if "dc_voltage_v" in fields:
        assert inv_by_id["dc_voltage_v"]["present"] is True
    assert scb_by_id["dc_power_kw"]["present"] is True  # multi-level, not inverter-only
    assert intel["architecture_summary"]["inverter_count"] == 12
    check = run_upload_integrity_check(
        get_settings(),
        columns=cols,
        suggestions=sug,
        hierarchy=intel["hierarchy_overview"],
        architecture_summary=intel["architecture_summary"],
        original_filename="trendreport_inverter_acdc.csv",
        reshape_report=rep.to_dict(),
        use_ai=False,
    )
    assert check["status"] == "pass"
    assert check["source"] == "rules"
    assert check["phase"] == "upload"


def test_semicolon_delimiter_reshape(tmp_path: Path):
    header = (
        "timestamp;ESSP_20MW ICR1 Inverter 1 Active Power (kW);"
        "ESSP_20MW ICR1 Inverter 1 DC Current (A);"
        "ESSP_20MW ICR1 Inverter 2 Active Power (kW);"
        "ESSP_20MW ICR1 Inverter 2 DC Current (A)"
    )
    rows = ["01-07-2026 00:00;10;1;20;2", "01-07-2026 00:05;11;1.1;21;2.1"]
    path = tmp_path / "semi.csv"
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    assert sniff_delimiter(path.read_text(encoding="utf-8").splitlines()[0]) == ";"
    rep = maybe_reshape_wide_csv(path)
    assert rep.reshaped
    assert "AC Power (kW)" in read_header(path)


def test_gzip_roundtrip_reshape(tmp_path: Path):
    raw = FIXTURE.read_bytes()
    gz_path = tmp_path / "wide.csv.gz"
    with gzip.open(gz_path, "wb") as fh:
        fh.write(raw)
    # Decompress like upload path then reshape
    out = tmp_path / "input.csv"
    with gzip.open(gz_path, "rb") as fh:
        out.write_bytes(fh.read())
    rep = maybe_reshape_wide_csv(out)
    assert rep.reshaped
    fields = {s.canonical_field for s in suggest_mapping(read_header(out)) if s.canonical_field}
    assert "ac_power_kw" in fields


def test_header_case_and_units_variant(tmp_path: Path):
    header = (
        "TIMESTAMP,plant A icr1 inverter 1 ACTIVE POWER (KW),"
        "plant A icr1 inverter 1 dc current (a),"
        "plant A icr1 inverter 2 active power (kw),"
        "plant A icr1 inverter 2 dc current (a)"
    )
    rows = ["2026-07-01 00:00:00,1,2,3,4"]
    path = tmp_path / "case.csv"
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    rep = maybe_reshape_wide_csv(path)
    assert rep.reshaped
    assert suggest_mapping(read_header(path))


def test_junk_title_row_before_header(tmp_path: Path):
    text = (
        "Trend Report Export\n"
        "timestamp,ESSP_20MW ICR1 Inverter 1 Active Power (kW),"
        "ESSP_20MW ICR1 Inverter 2 Active Power (kW)\n"
        "01-07-2026 00:00,5,6\n"
    )
    path = tmp_path / "junk.csv"
    path.write_text(text, encoding="utf-8")
    rep = maybe_reshape_wide_csv(path)
    assert rep.reshaped
    assert "Equipment ID" in read_header(path)


def test_tidy_demo_not_forced_reshape(tmp_path: Path):
    demo = Path(__file__).parent / "fixtures" / "demo_plant_scada.csv"
    if not demo.exists():
        pytest.skip("demo fixture missing")
    dst = tmp_path / "demo.csv"
    dst.write_bytes(demo.read_bytes())
    before = read_header(dst)
    rep = maybe_reshape_wide_csv(dst)
    assert rep.reshaped is False
    assert read_header(dst) == before


def test_upload_integrity_flags_only_timestamp(tmp_path: Path):
    path = tmp_path / "ts_only.csv"
    path.write_text("timestamp,mystery_col\n2026-01-01,1\n", encoding="utf-8")
    cols = read_header(path)
    sug = suggest_mapping(cols)
    check = run_upload_integrity_check(
        get_settings(),
        columns=cols,
        suggestions=sug,
        hierarchy=build_hierarchy_levels({"timestamp"}),
        original_filename="mystery.csv",
        use_ai=False,
    )
    codes = {f["code"] for f in check["findings"]}
    assert "only_timestamp_mapped" in codes
    assert check["status"] == "fail"


@pytest.mark.skipif(not REAL_DOWNLOAD.exists(), reason="local Downloads trendreport not present")
def test_real_trendreport_download_uat(tmp_path: Path):
    dst = tmp_path / "real.csv"
    dst.write_bytes(REAL_DOWNLOAD.read_bytes())
    rep = maybe_reshape_wide_csv(dst)
    assert rep.reshaped
    assert len(rep.inverters_found) == 12
    sug = suggest_mapping(read_header(dst))
    fields = {s.canonical_field for s in sug if s.canonical_field}
    assert {"timestamp", "device_id", "icr_id", "ac_power_kw", "dc_current_a", "dc_voltage_v"} <= fields
