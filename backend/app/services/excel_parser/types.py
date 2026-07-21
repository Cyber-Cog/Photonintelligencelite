"""Shared types for the multi-strategy Excel/SCADA parser."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class LayoutKind(str, Enum):
    TIDY_LONG = "tidy_long"
    WIDE_SINGLE_HEADER = "wide_single_header"
    WIDE_MULTI_HEADER = "wide_multi_header"
    TRANSPOSED = "transposed"
    UNKNOWN = "unknown"


@dataclass
class SheetProbe:
    sheet_name: str
    n_rows: int
    n_cols: int
    sample_rows: list[list[str]] = field(default_factory=list)
    merged_cell_count: int = 0
    dtype_guesses: list[str] = field(default_factory=list)


@dataclass
class ParseReport:
    """Confidence / diagnostics returned to API and UI after Excel conversion."""

    layout: str
    strategy: str
    sheet_name: str
    confidence: float
    header_rows: list[int] = field(default_factory=list)
    timestamp_column: str | None = None
    inverters_found: list[str] = field(default_factory=list)
    columns_mapped: list[str] = field(default_factory=list)
    row_count: int = 0
    warnings: list[str] = field(default_factory=list)
    sheets_probed: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_usable(self) -> bool:
        return self.confidence >= 0.55 and self.error is None and self.row_count > 0


@dataclass
class StrategyResult:
    rows: list[list[str]]  # header + data
    report: ParseReport


MIN_USABLE_CONFIDENCE = 0.55
