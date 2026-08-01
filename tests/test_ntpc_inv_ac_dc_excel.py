"""NTPC-style ICR/INV AC+DC power multi-row Excel headers."""
from __future__ import annotations

from backend.app.services.excel_parser.headers import map_metric
from backend.app.services.excel_parser.orchestrator import _run_strategies
from backend.app.services.excel_parser.strategies.wide_multi_header import try_wide_multi_header


def _ntpc_matrix() -> list[list[str]]:
    # Title rows + ICR / INV / metric header + 2 data rows
    rows: list[list[str]] = [[""] * 12 for _ in range(11)]
    rows[6] = ["DATE AND TIME", "", "", "ICR01", "ICR01", "ICR01", "ICR01", "ICR02", "ICR02", "ICR02", "ICR02", ""]
    rows[7] = ["", "", "", "INV1", "INV1", "INV2", "INV2", "INV1", "INV1", "INV2", "INV2", ""]
    rows[8] = [
        "",
        "",
        "",
        "AC_ACTIVE_POWER_kW",
        "DC_POWER",
        "AC_ACTIVE_POWER_kW",
        "DC_POWER",
        "AC_ACTIVE_POWER_kW",
        "DC_POWER",
        "AC_ACTIVE_POWER_kW",
        "DC_POWER",
        "",
    ]
    rows[9] = ["2026-03-01 07:01:00", "", "", "3.9", "0.0", "3.3", "3.0", "3.4", "3.0", "4.0", "4.0", ""]
    rows[10] = ["2026-03-01 07:02:00", "", "", "3.6", "3.0", "3.4", "3.0", "0.8", "0.0", "3.4", "3.0", ""]
    return rows


def test_map_metric_ac_active_and_dc_power_leaf():
    assert map_metric("", "AC_ACTIVE_POWER_kW") == "AC Power (kW)"
    assert map_metric("", "DC_POWER") == "DC Power (kW)"


def test_wide_multi_header_ntpc_icr_inv_ac_dc():
    matrix = _ntpc_matrix()
    result = try_wide_multi_header(matrix, sheet_name="REPORT")
    assert result is not None
    assert "AC Power (kW)" in result.report.columns_mapped
    assert "DC Power (kW)" in result.report.columns_mapped
    assert "ICR ID" in result.report.columns_mapped
    assert any(d.startswith("ICR1-INV-") for d in (result.report.inverters_found or []))
    assert result.report.confidence >= 0.75
    # First data row: ICR1 INV1 AC/DC
    header = result.rows[0]
    row = result.rows[1]
    by = dict(zip(header, row))
    assert by["Equipment ID"].startswith("ICR")
    assert by["AC Power (kW)"] == "3.9"
    assert by["DC Power (kW)"] == "0.0"


def test_orchestrator_prefers_multi_header_over_single_for_ntpc():
    best = _run_strategies(_ntpc_matrix(), sheet_name="REPORT")
    assert best is not None
    assert best.report.strategy == "wide_multi_header"
