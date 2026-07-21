"""Multi-strategy Excel/SCADA parser.

Public API (also re-exported from ``backend.app.services.excel_convert`` for
backward compatibility):

- ``convert_excel_to_csv`` / ``parse_excel_to_csv``
- ``ExcelConversionError``
- ``try_reshape_wide_inverter_report``
- ``ParseReport``
"""
from backend.app.services.excel_parser.orchestrator import (
    ExcelConversionError,
    convert_excel_to_csv,
    parse_excel_to_csv,
    try_promote_header_row,
    try_reshape_wide_inverter_report,
)
from backend.app.services.excel_parser.types import ParseReport

__all__ = [
    "ExcelConversionError",
    "ParseReport",
    "convert_excel_to_csv",
    "parse_excel_to_csv",
    "try_promote_header_row",
    "try_reshape_wide_inverter_report",
]
