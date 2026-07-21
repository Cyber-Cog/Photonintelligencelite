"""Wide single-header: Timestamp + INV1_P / INV2_Pac / etc. → long tidy."""
from __future__ import annotations

import re

from analytics.preprocessing.timestamps import normalise_timestamp
from backend.app.services.excel_parser.headers import (
    TIDY_FIELDS,
    looks_like_timestamp_header,
    normalize_header,
    pad_matrix,
    score_header_row,
)
from backend.app.services.excel_parser.types import LayoutKind, ParseReport, StrategyResult

_WIDE_COL_RE = re.compile(
    r"^(?:inv(?:erter)?[\s_\-]*)(\d+)[\s_\-]*(.*)$",
    re.IGNORECASE,
)


def try_wide_single_header(matrix: list[list[str]], *, sheet_name: str) -> StrategyResult | None:
    if not matrix:
        return None
    rows = pad_matrix(matrix)
    header_idx = None
    best = 0.0
    for i, row in enumerate(rows[:30]):
        s = score_header_row(row)
        wide_hits = sum(1 for c in row if c.strip() and _WIDE_COL_RE.match(c.strip()))
        s += wide_hits * 0.4
        if s > best:
            best = s
            header_idx = i
    if header_idx is None or best < 3.0:
        return None

    header = [c.strip() for c in rows[header_idx]]
    ts_col = next((j for j, h in enumerate(header) if looks_like_timestamp_header(h)), None)
    if ts_col is None:
        return None

    col_map: dict[int, tuple[str, str]] = {}
    for j, h in enumerate(header):
        if j == ts_col or not h:
            continue
        m = _WIDE_COL_RE.match(h)
        if not m:
            continue
        device = f"INV-{int(m.group(1)):02d}"
        metric = _leaf_to_metric(m.group(2) or h)
        if metric:
            col_map[j] = (device, metric)

    if len(col_map) < 2:
        return None

    devices = sorted({d for d, _ in col_map.values()})
    used = {m for _, m in col_map.values()}
    can_derive = (
        "DC Power (kW)" not in used and "DC Voltage (V)" in used and "DC Current (A)" in used
    )
    if can_derive:
        used.add("DC Power (kW)")
    out_header = [f for f in TIDY_FIELDS if f in {"Timestamp", "Equipment ID"} or f in used]
    out: list[list[str]] = [out_header]

    for row in rows[header_idx + 1 :]:
        raw_ts = row[ts_col].strip() if ts_col < len(row) else ""
        if not raw_ts:
            continue
        ts = normalise_timestamp(raw_ts) or raw_ts
        per: dict[str, dict[str, str]] = {d: {} for d in devices}
        for j, (dev, metric) in col_map.items():
            val = row[j].strip() if j < len(row) else ""
            if val:
                per[dev][metric] = val
        for dev in devices:
            metrics = per[dev]
            if not metrics:
                continue
            if can_derive and "DC Power (kW)" not in metrics:
                try:
                    metrics["DC Power (kW)"] = str(
                        round(float(metrics["DC Voltage (V)"]) * float(metrics["DC Current (A)"]) / 1000.0, 6)
                    )
                except (ValueError, KeyError):
                    pass
            out.append(
                [
                    ts if f == "Timestamp" else dev if f == "Equipment ID" else metrics.get(f, "")
                    for f in out_header
                ]
            )

    if len(out) <= 1:
        return None

    report = ParseReport(
        layout=LayoutKind.WIDE_SINGLE_HEADER.value,
        strategy="wide_single_header",
        sheet_name=sheet_name,
        confidence=0.85,
        header_rows=[header_idx],
        timestamp_column="Timestamp",
        inverters_found=devices,
        columns_mapped=out_header,
        row_count=len(out) - 1,
        warnings=["DC Power derived from V×I."] if can_derive else [],
    )
    return StrategyResult(rows=out, report=report)


def _leaf_to_metric(leaf: str) -> str | None:
    n = normalize_header(leaf)
    n = n.strip(" _-")
    if not n:
        return "AC Power (kW)"
    if any(tok in n for tok in ("ac power", "pac", "p_ac", "active power", "power kw", "power (kw)")):
        return "AC Power (kW)"
    if n in {"p", "power", "kw", "pac"}:
        return "AC Power (kW)"
    if "dc power" in n or n in {"pdc", "p_dc"}:
        return "DC Power (kW)"
    if "dc voltage" in n or n in {"vdc", "v_dc", "voltage"}:
        return "DC Voltage (V)"
    if "dc current" in n or n in {"idc", "i_dc", "current"}:
        return "DC Current (A)"
    if "temp" in n:
        return "Ambient Temp (C)"
    if "power" in n and "dc" not in n:
        return "AC Power (kW)"
    return None
