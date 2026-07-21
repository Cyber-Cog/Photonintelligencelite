"""Tidy / long layout: Timestamp + Equipment ID + metrics already present."""
from __future__ import annotations

from analytics.preprocessing.timestamps import normalise_timestamp, parse_timestamp
from backend.app.services.excel_parser.headers import (
    looks_like_timestamp_header,
    normalize_header,
    pad_matrix,
    sanitize_headers,
    score_header_row,
)
from backend.app.services.excel_parser.types import LayoutKind, ParseReport, StrategyResult

_EQUIP_TOKENS = (
    "equipment id",
    "equipment_id",
    "device id",
    "device_id",
    "inverter id",
    "inverter_id",
    "inv id",
    "inv",
    "inverter",
)


def try_tidy_long(matrix: list[list[str]], *, sheet_name: str) -> StrategyResult | None:
    if not matrix:
        return None
    rows = pad_matrix(matrix)
    header_idx = _best_header_idx(rows)
    if header_idx is None:
        return None

    header = sanitize_headers([c.strip() for c in rows[header_idx]])
    ts_col = _find_ts_col(header)
    eq_col = _find_equip_col(header)
    if ts_col is None:
        return None

    # Require at least one power-like column for tidy confidence
    powerish = any(
        any(tok in normalize_header(h) for tok in ("power", "pac", "p_ac", "kw"))
        for h in header
        if h
    )
    if not powerish and eq_col is None:
        return None

    out = [header]
    parse_ok = 0
    parse_fail = 0
    devices: set[str] = set()
    for row in rows[header_idx + 1 :]:
        if not any(c.strip() for c in row):
            continue
        raw_ts = row[ts_col].strip() if ts_col < len(row) else ""
        if not raw_ts:
            continue
        norm = normalise_timestamp(raw_ts)
        if norm:
            parse_ok += 1
            row = list(row) + [""] * max(0, len(header) - len(row))
            row[ts_col] = norm
        else:
            parse_fail += 1
            row = list(row) + [""] * max(0, len(header) - len(row))
        if eq_col is not None and eq_col < len(row) and row[eq_col].strip():
            devices.add(row[eq_col].strip())
        out.append(row[: len(header)])

    if len(out) <= 1:
        return None

    # Detect wide mistaken as tidy: many INV*_P style columns, no equipment col
    wide_like = sum(1 for h in header if _looks_wide_metric(h))
    if wide_like >= 3 and eq_col is None:
        return None

    data_rows = len(out) - 1
    total = parse_ok + parse_fail
    ts_ratio = parse_ok / total if total else 0.0
    confidence = 0.5 + (0.25 if eq_col is not None else 0.05) + 0.2 * ts_ratio

    # Rename timestamp column to Timestamp for downstream aliasing if needed
    if header[ts_col] != "Timestamp" and looks_like_timestamp_header(header[ts_col]):
        # Keep original name — aliaser maps "Date And Time" etc.
        pass

    report = ParseReport(
        layout=LayoutKind.TIDY_LONG.value,
        strategy="tidy_long",
        sheet_name=sheet_name,
        confidence=round(min(confidence, 0.97), 3),
        header_rows=[header_idx],
        timestamp_column=header[ts_col],
        inverters_found=sorted(devices)[:50],
        columns_mapped=header,
        row_count=data_rows,
        warnings=[],
    )
    if ts_ratio < 0.5 and total > 5:
        report.confidence = min(report.confidence, 0.5)
        report.warnings.append(f"Weak timestamp parse rate ({parse_ok}/{total}).")
        return None
    if report.confidence < 0.55:
        return None
    return StrategyResult(rows=out, report=report)


def _best_header_idx(rows: list[list[str]]) -> int | None:
    best_i: int | None = None
    best_s = 0.0
    for i, row in enumerate(rows[:40]):
        s = score_header_row(row)
        if s > best_s:
            best_s = s
            best_i = i
    return best_i if best_s >= 2.5 else None


def _find_ts_col(header: list[str]) -> int | None:
    for j, h in enumerate(header):
        if looks_like_timestamp_header(h):
            return j
    return None


def _find_equip_col(header: list[str]) -> int | None:
    for j, h in enumerate(header):
        n = normalize_header(h)
        if n in _EQUIP_TOKENS or n in {"equipment id", "device id", "inverter id"}:
            return j
        if n.endswith(" id") and any(tok in n for tok in ("equip", "device", "inverter", "inv")):
            return j
    return None


def _looks_wide_metric(name: str) -> bool:
    n = normalize_header(name)
    return bool(
        n.startswith("inv") and any(tok in n for tok in ("power", "pac", "p ", "_p", "voltage", "current"))
    )
