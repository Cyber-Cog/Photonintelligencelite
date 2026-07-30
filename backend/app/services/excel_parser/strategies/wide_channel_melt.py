"""Wide SMB/SCB exports with multi-row headers and repeating string-current channels.

Detects stitched headers (e.g. ``Strings Current (A)`` over ``I1``..``I24``), melts
channel columns into long tidy rows (Timestamp + Equipment ID + DC Current), and
carries shared metrics (voltage, SMB total current, temps) onto each string row.
"""
from __future__ import annotations

import re

from analytics.preprocessing.timestamps import normalise_timestamp
from backend.app.services.excel_parser.channels import equipment_id_for_channel
from backend.app.services.excel_parser.headers import (
    TIDY_FIELDS,
    looks_like_timestamp_header,
    map_metric,
    normalize_header,
    pad_matrix,
    sanitize_headers,
)
from backend.app.services.excel_parser.multi_header import HeaderBlock, detect_header_block
from backend.app.services.excel_parser.types import LayoutKind, ParseReport, StrategyResult

_PARENT_FROM_SHEET = re.compile(
    r"^(smb|scb|inv|inverter)[_\-\s]*(\d+)$",
    re.IGNORECASE,
)


def try_wide_channel_melt(matrix: list[list[str]], *, sheet_name: str) -> StrategyResult | None:
    if not matrix:
        return None
    rows = pad_matrix(matrix)
    block = detect_header_block(rows)
    if block is None or block.n_header_rows < 1:
        return None

    channel_cols = [
        c
        for c in block.columns
        if c.field_type == "string_current_channel" and c.channel_index is not None
    ]
    # Need a clear repeating channel band — otherwise leave to tidy / other strategies.
    if len(channel_cols) < 2:
        return None

    ts_col = _find_timestamp_col(block)
    if ts_col is None:
        return None

    parent_id = _parent_from_sheet(sheet_name)
    shared = _map_shared_metrics(block, channel_indexes={c.index for c in channel_cols}, ts_col=ts_col)

    # Build tidy long output
    used_metrics = {"DC Current (A)"}
    used_metrics.update(shared.values())
    header = [f for f in TIDY_FIELDS if f in {"Timestamp", "Equipment ID"} or f in used_metrics]
    # Ensure irradiance aliases survive even if not in TIDY order edge cases
    for extra in ("Irradiance (W/m2)", "GHI (W/m2)"):
        if extra in used_metrics and extra not in header:
            header.append(extra)

    out: list[list[str]] = [header]
    warnings = list(block.warnings)
    parse_ok = 0
    parse_fail = 0
    data_start = block.end_row + 1

    for row in rows[data_start:]:
        if not any(c.strip() for c in row):
            continue
        raw_ts = row[ts_col].strip() if ts_col < len(row) else ""
        if not raw_ts:
            continue
        norm = normalise_timestamp(raw_ts)
        if norm is None:
            parse_fail += 1
            ts = raw_ts
        else:
            parse_ok += 1
            ts = norm

        shared_vals: dict[str, str] = {}
        for j, metric in shared.items():
            val = row[j].strip() if j < len(row) else ""
            if val:
                shared_vals[metric] = val

        for ch in channel_cols:
            val = row[ch.index].strip() if ch.index < len(row) else ""
            # Emit row even when current is 0 — disconnected-string needs zeros.
            if val == "" and "DC Current (A)" not in shared_vals:
                continue
            eid = equipment_id_for_channel(
                parent_id,
                int(ch.channel_index),
                field_type=ch.field_type or "string_current_channel",
            )
            metrics = dict(shared_vals)
            if val != "":
                metrics["DC Current (A)"] = val
            elif "DC Current (A)" not in metrics:
                metrics["DC Current (A)"] = "0"
            out.append(
                [
                    ts
                    if f == "Timestamp"
                    else eid
                    if f == "Equipment ID"
                    else metrics.get(f, "")
                    for f in header
                ]
            )

    if len(out) <= 1:
        return None

    data_rows = len(out) - 1
    total_ts = parse_ok + parse_fail
    ts_ratio = parse_ok / total_ts if total_ts else 0.0
    confidence = 0.55 + 0.2 * min(1.0, len(channel_cols) / 12.0) + 0.2 * ts_ratio
    if block.n_header_rows >= 2:
        confidence += 0.05
    if block.ambiguous:
        confidence = min(confidence, 0.72)
        warnings.append("Multi-row header detected, please confirm")

    warnings.append(
        f"Melted {len(channel_cols)} string-current channels (I/Str/CH) into long format "
        f"under parent '{parent_id}'."
    )

    report = ParseReport(
        layout=LayoutKind.WIDE_CHANNEL_MELT.value,
        strategy="wide_channel_melt",
        sheet_name=sheet_name,
        confidence=round(min(confidence, 0.96), 3),
        header_rows=block.header_rows,
        timestamp_column="Timestamp",
        inverters_found=[],
        columns_mapped=header,
        row_count=data_rows,
        warnings=warnings,
        multi_row_header=block.n_header_rows >= 2,
        header_preview=block.preview_rows[:4],
        channel_columns=[
            {
                "index": c.index,
                "display_name": c.display_name,
                "primary_candidate": c.primary_candidate,
                "channel_index": c.channel_index,
                "field_type": c.field_type,
            }
            for c in channel_cols
        ],
        needs_header_confirm=block.ambiguous,
    )
    if ts_ratio < 0.5 and total_ts > 5:
        report.confidence = min(report.confidence, 0.5)
        report.warnings.append(f"Weak timestamp parse rate ({parse_ok}/{total_ts}).")
        return None
    if report.confidence < 0.55:
        return None
    return StrategyResult(rows=out, report=report)


def try_stitch_only(matrix: list[list[str]], *, sheet_name: str) -> StrategyResult | None:
    """Fallback: stitch multi-row headers into one row without melting channels.

    Used when channel count is low but multi-row headers would otherwise become Column_N.
    """
    rows = pad_matrix(matrix)
    block = detect_header_block(rows)
    if block is None or block.n_header_rows < 2:
        return None

    # Prefer primary (leaf) names for mapping — group retained in display via warning.
    names = []
    for c in block.columns:
        # For mapping quality: use leaf when present; else display
        name = c.primary_candidate or c.display_name or f"Column_{c.index + 1}"
        # Enrich short channel leaves with group for uniqueness in wide (non-melt) path
        if c.field_type and c.group_label and name.upper() in {c.leaf_label.upper(), c.primary_candidate.upper()}:
            # Keep leaf as-is — aliasing/channel tagging handles it; sanitize_headers dedupes
            pass
        names.append(name)
    names = sanitize_headers(names)

    out = [names]
    for row in rows[block.end_row + 1 :]:
        if not any(c.strip() for c in row):
            continue
        out.append(list(row) + [""] * max(0, len(names) - len(row)))
        out[-1] = out[-1][: len(names)]

    if len(out) <= 1:
        return None

    ts_name = next((n for n in names if looks_like_timestamp_header(n)), None)
    confidence = 0.7 if not block.ambiguous else 0.6
    report = ParseReport(
        layout=LayoutKind.WIDE_MULTI_HEADER.value,
        strategy="multi_row_stitch",
        sheet_name=sheet_name,
        confidence=confidence,
        header_rows=block.header_rows,
        timestamp_column=ts_name,
        columns_mapped=names,
        row_count=len(out) - 1,
        warnings=list(block.warnings)
        + (["Multi-row header detected, please confirm"] if block.ambiguous else []),
        multi_row_header=True,
        header_preview=block.preview_rows[:4],
        channel_columns=[
            {
                "index": c.index,
                "display_name": c.display_name,
                "primary_candidate": c.primary_candidate,
                "channel_index": c.channel_index,
                "field_type": c.field_type,
            }
            for c in block.columns
            if c.field_type
        ],
        needs_header_confirm=block.ambiguous,
    )
    return StrategyResult(rows=out, report=report)


def _find_timestamp_col(block: HeaderBlock) -> int | None:
    for c in block.columns:
        for label in (c.primary_candidate, c.display_name, c.leaf_label, c.group_label):
            if label and looks_like_timestamp_header(label):
                return c.index
    return None


def _parent_from_sheet(sheet_name: str) -> str:
    s = (sheet_name or "").strip()
    m = _PARENT_FROM_SHEET.match(s)
    if m:
        prefix = m.group(1).upper()
        if prefix == "INVERTER":
            prefix = "INV"
        return f"{prefix}-{int(m.group(2)):02d}"
    # SMB_1 style already handled; bare names
    if s:
        return s.replace(" ", "-")
    return "SMB-01"


def _map_shared_metrics(
    block: HeaderBlock,
    *,
    channel_indexes: set[int],
    ts_col: int,
) -> dict[int, str]:
    """Map non-channel columns to tidy metric names (Voltage, Current, Temps, Irradiance)."""
    mapped: dict[int, str] = {}
    for c in block.columns:
        if c.index in channel_indexes or c.index == ts_col:
            continue
        leaf = c.leaf_label or c.primary_candidate
        group = c.group_label
        metric = map_metric(group, leaf)
        if metric is None:
            # Direct leaf mapping for common SMB parameter names
            metric = map_metric("", leaf) or _leaf_metric(leaf)
        if metric and metric not in {"Timestamp"}:
            # Prefer first column for each metric (SMB Current before string melt)
            if metric not in mapped.values():
                mapped[c.index] = metric
            elif metric == "DC Current (A)":
                # Keep SMB aggregate current as shared — string melt overwrites per row
                mapped[c.index] = metric
    return mapped


def _leaf_metric(leaf: str) -> str | None:
    n = normalize_header(leaf)
    if not n:
        return None
    if "voltage" in n or n in {"v", "vdc"}:
        return "DC Voltage (V)"
    if n in {"current (a)", "current", "idc"} or (n.startswith("current") and "string" not in n):
        return "DC Current (A)"
    if "power" in n and "kw" in n:
        return "DC Power (kW)"
    if "irr" in n or "poa" in n or "gti" in n:
        return "Irradiance (W/m2)"
    if "ghi" in n:
        return "GHI (W/m2)"
    if "temp" in n:
        if "module" in n or "panel" in n or "ext" in n:
            return "Module Temp (C)" if "module" in n or "panel" in n else "Ambient Temp (C)"
        if "int" in n or "internal" in n or "cabinet" in n:
            return "Ambient Temp (C)"
        return "Ambient Temp (C)"
    return None
