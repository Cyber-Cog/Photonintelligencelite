"""Excel onboard phased pipeline tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services.excel_onboard.header_recon import reconstruct_headers
from backend.app.services.excel_onboard.pipeline import run_excel_onboard
from backend.app.services.excel_parser.headers import map_metric


def test_map_metric_ntpc_leaves():
    assert map_metric("", "AC_ACTIVE_POWER_kW") == "AC Power (kW)"
    assert map_metric("", "DC_POWER") == "DC Power (kW)"


def test_header_recon_builds_unique_names():
    matrix = [
        ["DATE AND TIME", "ICR01", "ICR01", "ICR02", "ICR02"],
        ["", "INV1", "INV1", "INV1", "INV1"],
        ["", "AC_ACTIVE_POWER_kW", "DC_POWER", "AC_ACTIVE_POWER_kW", "DC_POWER"],
        ["2026-03-01 07:01:00", "1", "2", "3", "4"],
    ]
    # ffill-like for test
    matrix[0] = ["DATE AND TIME", "ICR01", "ICR01", "ICR02", "ICR02"]
    matrix[1] = ["DATE AND TIME", "INV1", "INV1", "INV1", "INV1"]
    h = reconstruct_headers(matrix)
    names = [c.reconstructed_name for c in h.columns]
    assert len(names) == len(set(names))
    assert h.first_data_row >= 2


@pytest.mark.skipif(
    not Path(
        r"c:\Users\ayush.r\Downloads\INV AC DC PWR (1)\INV AC DC PWR\INV AC DC PWR 01-03-2026.xlsx"
    ).exists(),
    reason="local INV AC DC sample not present",
)
def test_onboard_real_ntpc_file(tmp_path: Path):
    src = Path(
        r"c:\Users\ayush.r\Downloads\INV AC DC PWR (1)\INV AC DC PWR\INV AC DC PWR 01-03-2026.xlsx"
    )
    out = tmp_path / "out.csv"
    result = run_excel_onboard(src, out, max_rows=2_000_000, run_ai=False)
    assert result.rows_written > 1000
    assert result.report.confidence >= 0.75
    assert "AC Power (kW)" in (result.report.columns_mapped or [])
    assert "DC Power (kW)" in (result.report.columns_mapped or [])
    assert result.elapsed_ms < 60_000
    assert "analyze" in result.phase_timings_ms
    assert result.ai_meta.get("skipped") is True or result.ai_meta.get("attempted") is False
