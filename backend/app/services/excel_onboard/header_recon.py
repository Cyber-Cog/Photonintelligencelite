"""Phase 3 — Header reconstruction: multi-row hierarchy → unique column names."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from backend.app.services.excel_parser.headers import (
    has_metric_token,
    inverter_id_from_label,
    looks_like_timestamp_header,
)

logger = logging.getLogger(__name__)

_ICR_RE = re.compile(r"^\s*ICR\s*[-_]?\s*(\d+)\s*$", re.I)


@dataclass
class ColumnMeta:
    index: int
    reconstructed_name: str
    hierarchy_parts: list[str] = field(default_factory=list)
    unit: str | None = None
    equipment_hint: str | None = None
    level_hint: str | None = None  # plant|icr|inverter|scb|string
    is_timestamp: bool = False


@dataclass
class HeaderReconstruction:
    header_row_indexes: list[int]  # 0-based
    first_data_row: int
    columns: list[ColumnMeta]
    timestamp_column_index: int | None = None


def reconstruct_headers(matrix: list[list[str]], *, header_depth_hint: int = 3) -> HeaderReconstruction:
    """Build unique hierarchical column names from multi-row headers."""
    if not matrix:
        return HeaderReconstruction([], 0, [])

    width = len(matrix[0])
    device_idx = _find_inv_row(matrix)
    leaf_idx = _find_metric_row(matrix, device_idx if device_idx is not None else 0)
    icr_idx = _find_icr_row(matrix, device_idx) if device_idx is not None else None

    if device_idx is not None and leaf_idx is not None:
        header_idxs = [i for i in (icr_idx, device_idx, leaf_idx) if i is not None]
        first_data = leaf_idx + 1
    else:
        # Generic: use top N non-empty rows as header
        header_idxs = list(range(min(max(header_depth_hint, 1), min(8, len(matrix)))))
        first_data = header_idxs[-1] + 1 if header_idxs else 0

    # Stack parts per column
    parts_per_col: list[list[str]] = [[] for _ in range(width)]
    for hi in header_idxs:
        row = matrix[hi] if hi < len(matrix) else [""] * width
        for j in range(width):
            cell = row[j].strip() if j < len(row) else ""
            if not cell:
                continue
            # Skip repeating timestamp banner on metric cols
            if looks_like_timestamp_header(cell) and j > 0:
                continue
            if not parts_per_col[j] or parts_per_col[j][-1] != cell:
                parts_per_col[j].append(cell)

    columns: list[ColumnMeta] = []
    seen: dict[str, int] = {}
    ts_col: int | None = None

    for j in range(width):
        parts = parts_per_col[j]
        is_ts = False
        if parts and looks_like_timestamp_header(parts[0]):
            is_ts = True
            ts_col = j if ts_col is None else ts_col
        elif j == 0 and first_data < len(matrix):
            # First col often datetime without header text after ffill noise
            sample = matrix[first_data][j] if j < len(matrix[first_data]) else ""
            if _looks_datetime(sample):
                is_ts = True
                ts_col = j if ts_col is None else ts_col
                parts = ["Timestamp"]

        name = _join_parts(parts) if parts else f"Column_{j + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0

        unit = _extract_unit(" ".join(parts))
        level, equip = _infer_level_equipment(parts)
        columns.append(
            ColumnMeta(
                index=j,
                reconstructed_name=name,
                hierarchy_parts=parts,
                unit=unit,
                equipment_hint=equip,
                level_hint=level,
                is_timestamp=is_ts,
            )
        )

    logger.info(
        "excel_onboard.headers cols=%s header_rows=%s first_data=%s ts_col=%s",
        len(columns),
        header_idxs,
        first_data,
        ts_col,
    )
    return HeaderReconstruction(
        header_row_indexes=header_idxs,
        first_data_row=first_data,
        columns=columns,
        timestamp_column_index=ts_col,
    )


def _join_parts(parts: list[str]) -> str:
    cleaned: list[str] = []
    for p in parts:
        tok = re.sub(r"[^\w]+", "_", p.strip()).strip("_")
        if tok and (not cleaned or cleaned[-1].lower() != tok.lower()):
            cleaned.append(tok)
    return "_".join(cleaned) if cleaned else "Column"


def _extract_unit(text: str) -> str | None:
    m = re.search(r"\(([^)]+)\)|(?:_|^)(kW|kWh|V|A|W/m2|C|°C)\b", text, re.I)
    if not m:
        return None
    return (m.group(1) or m.group(2) or "").strip() or None


def _infer_level_equipment(parts: list[str]) -> tuple[str | None, str | None]:
    icr = None
    inv = None
    scb = None
    for p in parts:
        m = _ICR_RE.match(p)
        if m:
            icr = f"ICR{int(m.group(1))}"
        iid = inverter_id_from_label(p)
        if iid:
            inv = iid
        sm = re.match(r"^\s*(?:SCB|SMB)\s*[-_]?\s*(\d+)\s*$", p, re.I)
        if sm:
            scb = f"SCB-{int(sm.group(1)):02d}"
    if scb and inv:
        return "scb", f"{icr + '-' if icr else ''}{inv}-{scb}"
    if inv:
        return "inverter", f"{icr + '-' if icr else ''}{inv}"
    if icr:
        return "icr", icr
    return None, None


def _find_inv_row(matrix: list[list[str]]) -> int | None:
    best_i, best_n = None, 0
    for i, row in enumerate(matrix[:40]):
        n = sum(1 for c in row if c.strip() and inverter_id_from_label(c))
        if n > best_n:
            best_n, best_i = n, i
    return best_i if best_n >= 1 else None


def _find_icr_row(matrix: list[list[str]], device_idx: int | None) -> int | None:
    if device_idx is None:
        return None
    best_i, best_n = None, 0
    for i in range(max(0, device_idx - 3), device_idx):
        n = sum(1 for c in matrix[i] if c.strip() and _ICR_RE.match(c))
        if n > best_n:
            best_n, best_i = n, i
    return best_i if best_n >= 1 else None


def _find_metric_row(matrix: list[list[str]], start: int) -> int | None:
    best_i, best_s = None, 0
    for i in range(start, min(start + 8, len(matrix))):
        row = matrix[i]
        inv_hits = sum(1 for c in row if c.strip() and inverter_id_from_label(c))
        metric_hits = sum(1 for c in row if c.strip() and has_metric_token(c))
        if inv_hits >= 1 and metric_hits < 2:
            continue
        if metric_hits >= 2 and metric_hits > best_s:
            best_s, best_i = metric_hits, i
    return best_i


def _looks_datetime(value: str) -> bool:
    if not value:
        return False
    if re.match(r"\d{4}-\d{2}-\d{2}", value):
        return True
    if re.match(r"\d{1,2}/\d{1,2}/\d{2,4}", value):
        return True
    return False
