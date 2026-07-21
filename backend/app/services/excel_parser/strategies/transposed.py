"""Transposed layout: metrics as rows, timestamps / devices as columns."""
from __future__ import annotations

from analytics.preprocessing.timestamps import normalise_timestamp, parse_timestamp
from backend.app.services.excel_parser.headers import (
    TIDY_FIELDS,
    has_metric_token,
    normalize_header,
    pad_matrix,
)
from backend.app.services.excel_parser.types import LayoutKind, ParseReport, StrategyResult

_METRIC_ROW_MAP = {
    "ac power": "AC Power (kW)",
    "ac power (kw)": "AC Power (kW)",
    "power (kw)": "AC Power (kW)",
    "pac": "AC Power (kW)",
    "dc power": "DC Power (kW)",
    "dc power (kw)": "DC Power (kW)",
    "dc voltage": "DC Voltage (V)",
    "dc voltage (v)": "DC Voltage (V)",
    "voltage (v)": "DC Voltage (V)",
    "dc current": "DC Current (A)",
    "dc current (a)": "DC Current (A)",
    "current (a)": "DC Current (A)",
}


def try_transposed(matrix: list[list[str]], *, sheet_name: str) -> StrategyResult | None:
    """Detect when first column is metric names and a header row holds timestamps or device ids."""
    if not matrix or len(matrix) < 4:
        return None
    rows = pad_matrix(matrix)
    # Heuristic: many rows in col0 look like metric labels; few look like timestamps
    metric_row_hits = 0
    for row in rows[1:25]:
        label = row[0].strip() if row else ""
        if not label:
            continue
        n = normalize_header(label)
        if n in _METRIC_ROW_MAP or has_metric_token(label):
            metric_row_hits += 1
    if metric_row_hits < 3:
        return None

    # Header row 0: skip label, rest are timestamps or device ids
    header = rows[0]
    value_cols = [j for j in range(1, len(header)) if header[j].strip()]
    if len(value_cols) < 2:
        return None

    # Decide: timestamps across columns vs devices across columns
    ts_like = sum(1 for j in value_cols[:20] if parse_timestamp(header[j]) is not None)
    if ts_like >= max(2, len(value_cols[:20]) // 2):
        return _melt_timestamps_across(rows, value_cols, sheet_name)
    # Device-across: less common; skip unless labels look like INV
    return None


def _melt_timestamps_across(
    rows: list[list[str]], value_cols: list[int], sheet_name: str
) -> StrategyResult | None:
    # Map metric rows
    metric_rows: list[tuple[int, str]] = []
    for i, row in enumerate(rows[1:], start=1):
        label = normalize_header(row[0]) if row else ""
        mapped = _METRIC_ROW_MAP.get(label)
        if mapped is None and has_metric_token(row[0] if row else ""):
            for k, v in _METRIC_ROW_MAP.items():
                if k in label:
                    mapped = v
                    break
        if mapped:
            metric_rows.append((i, mapped))
    if not metric_rows:
        return None

    used = {m for _, m in metric_rows}
    out_header = [f for f in TIDY_FIELDS if f in {"Timestamp", "Equipment ID"} or f in used]
    # Single synthetic equipment when transposed plant-level
    device = "INV-01"
    out: list[list[str]] = [out_header]
    for j in value_cols:
        raw_ts = rows[0][j].strip()
        ts = normalise_timestamp(raw_ts) or raw_ts
        metrics: dict[str, str] = {}
        for i, metric in metric_rows:
            val = rows[i][j].strip() if j < len(rows[i]) else ""
            if val:
                metrics[metric] = val
        if not metrics:
            continue
        out.append(
            [
                ts if f == "Timestamp" else device if f == "Equipment ID" else metrics.get(f, "")
                for f in out_header
            ]
        )
    if len(out) <= 1:
        return None

    report = ParseReport(
        layout=LayoutKind.TRANSPOSED.value,
        strategy="transposed",
        sheet_name=sheet_name,
        confidence=0.7,
        header_rows=[0],
        timestamp_column="Timestamp",
        inverters_found=[device],
        columns_mapped=out_header,
        row_count=len(out) - 1,
        warnings=["Transposed layout detected; assigned Equipment ID INV-01."],
    )
    return StrategyResult(rows=out, report=report)
