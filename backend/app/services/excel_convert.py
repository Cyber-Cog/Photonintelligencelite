"""Compatibility shim — prefer ``backend.app.services.excel_parser``.

Keeps existing imports (`from backend.app.services.excel_convert import …`) working.
"""
from backend.app.services.excel_parser import (  # noqa: F401
    ExcelConversionError,
    ParseReport,
    convert_excel_to_csv,
    parse_excel_to_csv,
    try_promote_header_row,
    try_reshape_wide_inverter_report,
)

__all__ = [
    "ExcelConversionError",
    "ParseReport",
    "convert_excel_to_csv",
    "parse_excel_to_csv",
    "try_promote_header_row",
    "try_reshape_wide_inverter_report",
]
