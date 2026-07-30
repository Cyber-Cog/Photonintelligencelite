"""Generic multi-row / merged-cell header detection and stitching.

Handles 1–3 header rows. Merged group labels are propagated across columns, then
each column is stitched as ``group + sub`` while keeping the leaf as the primary
mapping candidate. Synonym/confidence mapping runs *after* this step.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.app.services.excel_parser.channels import (
    ChannelMatch,
    classify_stitched_column,
    match_channel_label,
)
from backend.app.services.excel_parser.headers import (
    cell_to_str,
    ffill_row,
    has_metric_token,
    looks_like_timestamp_header,
    normalize_header,
    pad_matrix,
)


@dataclass
class StitchedColumn:
    """One logical column after merge propagation + header stitch."""

    index: int
    display_name: str
    """Full stitched label for CSV / UI (``Strings Current (A) I12``)."""

    primary_candidate: str
    """Leaf-preferred name for synonym mapping (``I12`` or ``Voltage (V)``)."""

    group_label: str = ""
    leaf_label: str = ""
    field_type: str | None = None
    channel_index: int | None = None
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HeaderBlock:
    start_row: int
    end_row: int  # inclusive
    n_header_rows: int
    columns: list[StitchedColumn] = field(default_factory=list)
    ambiguous: bool = False
    warnings: list[str] = field(default_factory=list)
    preview_rows: list[list[str]] = field(default_factory=list)

    @property
    def header_rows(self) -> list[int]:
        return list(range(self.start_row, self.end_row + 1))


def propagate_merged_values(
    matrix: list[list[str]],
    merged_ranges: list[tuple[int, int, int, int]],
) -> list[list[str]]:
    """Fill blank cells covered by merges with the top-left value.

    ``merged_ranges`` are 0-based ``(min_row, min_col, max_row, max_col)``.
    Single-cell merges are ignored. Only propagates into currently blank cells.
    """
    if not matrix or not merged_ranges:
        return pad_matrix(matrix)
    rows = pad_matrix([[cell_to_str(c) for c in r] for r in matrix])
    height = len(rows)
    width = len(rows[0]) if rows else 0
    for r0, c0, r1, c1 in merged_ranges:
        if r0 == r1 and c0 == c1:
            continue
        if r0 < 0 or c0 < 0 or r0 >= height or c0 >= width:
            continue
        value = rows[r0][c0].strip()
        if not value:
            continue
        for r in range(r0, min(r1, height - 1) + 1):
            for c in range(c0, min(c1, width - 1) + 1):
                if not rows[r][c].strip():
                    rows[r][c] = value
    return rows


def merged_ranges_from_worksheet(ws) -> list[tuple[int, int, int, int]]:
    """Extract 0-based merge tuples from an openpyxl worksheet."""
    out: list[tuple[int, int, int, int]] = []
    try:
        ranges = ws.merged_cells.ranges
    except Exception:  # noqa: BLE001
        return out
    for m in ranges:
        # Skip degenerate single-cell "merges" common in some OEM exports.
        if m.min_row == m.max_row and m.min_col == m.max_col:
            continue
        out.append((m.min_row - 1, m.min_col - 1, m.max_row - 1, m.max_col - 1))
    return out


def _row_string_ratio(row: list[str]) -> float:
    non_empty = [c for c in row if c.strip()]
    if not non_empty:
        return 0.0
    stringish = 0
    for c in non_empty:
        try:
            float(c.replace(",", ""))
        except ValueError:
            stringish += 1
    return stringish / len(non_empty)


def _row_numeric_ratio(row: list[str]) -> float:
    non_empty = [c for c in row if c.strip()]
    if not non_empty:
        return 0.0
    numeric = 0
    for c in non_empty:
        try:
            float(c.replace(",", ""))
            numeric += 1
        except ValueError:
            pass
    return numeric / len(non_empty)


def _looks_like_data_row(row: list[str]) -> bool:
    non_empty = [c for c in row if c.strip()]
    if len(non_empty) < 2:
        return False
    # Data rows are majority-numeric (or timestamp + numbers).
    return _row_numeric_ratio(row) >= 0.55


def _looks_like_header_row(row: list[str]) -> bool:
    non_empty = [c for c in row if c.strip()]
    if not non_empty:
        return False
    if _row_string_ratio(row) < 0.55:
        return False
    # Title banners: single filled cell spanning the sheet
    if len(non_empty) == 1 and len(row) > 4:
        return False
    return True


def detect_header_block(
    matrix: list[list[str]],
    *,
    scan_rows: int = 10,
) -> HeaderBlock | None:
    """Find a 1–3 row header block in the first ``scan_rows`` rows.

    Candidate header = majority strings, followed by data-looking rows.
    If a merged/group row has many blanks that a following row fills with
    metric/channel leaves, treat that following row as a sub-header.
    """
    if not matrix:
        return None
    rows = pad_matrix(matrix)
    limit = min(scan_rows, len(rows))

    # Find first data-looking row; header is immediately above it.
    data_idx: int | None = None
    for i in range(limit):
        if _looks_like_data_row(rows[i]) and not _looks_like_header_row(rows[i]):
            data_idx = i
            break
        # Timestamp + mostly numbers also counts as data even if one string header leaked
        if i > 0 and _row_numeric_ratio(rows[i]) >= 0.7 and len([c for c in rows[i] if c.strip()]) >= 3:
            data_idx = i
            break

    if data_idx is None:
        # Fallback: best single header row by string ratio + metric tokens
        best_i, best_s = 0, -1.0
        for i in range(limit):
            if not _looks_like_header_row(rows[i]):
                continue
            s = _row_string_ratio(rows[i]) + (0.3 if any(has_metric_token(c) for c in rows[i]) else 0.0)
            if any(looks_like_timestamp_header(c) for c in rows[i]):
                s += 0.5
            if s > best_s:
                best_s = s
                best_i = i
        if best_s < 0.5:
            return None
        cols = stitch_header_rows(rows[best_i : best_i + 1])
        return HeaderBlock(start_row=best_i, end_row=best_i, n_header_rows=1, columns=cols)

    # Walk upward from data_idx collecting 1–3 header rows
    header_indices: list[int] = []
    for i in range(data_idx - 1, max(-1, data_idx - 4), -1):
        if i < 0:
            break
        if _looks_like_header_row(rows[i]) or _row_has_group_or_leaf_signal(rows[i]):
            header_indices.append(i)
        elif header_indices:
            break
        if len(header_indices) >= 3:
            break
    header_indices.reverse()
    if not header_indices:
        return None

    # Prefer including a sub-header when the top row looks like sparse group labels
    # and the next row fills blanks with leaves.
    if len(header_indices) == 1 and header_indices[0] + 1 < data_idx:
        top = rows[header_indices[0]]
        nxt = rows[header_indices[0] + 1]
        if _is_group_row(top) and _is_leaf_row(nxt):
            header_indices.append(header_indices[0] + 1)

    # Defensive: allow a third category row between group and leaf
    if len(header_indices) == 2:
        mid = header_indices[0] + 1
        if mid not in header_indices and mid < header_indices[-1]:
            # already contiguous
            pass
        elif (
            header_indices[-1] - header_indices[0] == 1
            and header_indices[-1] + 1 < data_idx
            and _is_leaf_row(rows[header_indices[-1] + 1])
            and not _is_leaf_row(rows[header_indices[-1]])
        ):
            header_indices.append(header_indices[-1] + 1)

    start, end = header_indices[0], header_indices[-1]
    # Contiguous block only
    block_rows = rows[start : end + 1]
    cols = stitch_header_rows(block_rows)

    ambiguous = _is_ambiguous_stitch(cols, block_rows)
    warnings: list[str] = []
    if len(header_indices) >= 2:
        warnings.append(
            f"Multi-row header detected (rows {start + 1}–{end + 1}). "
            "Confirm stitched column names if mapping looks wrong."
        )
    if ambiguous:
        warnings.append("Multi-row header detected, please confirm — some columns remain ambiguous.")

    preview = [list(r) for r in block_rows]
    if data_idx < len(rows):
        preview.append(list(rows[data_idx]))

    return HeaderBlock(
        start_row=start,
        end_row=end,
        n_header_rows=end - start + 1,
        columns=cols,
        ambiguous=ambiguous,
        warnings=warnings,
        preview_rows=preview,
    )


def _row_has_group_or_leaf_signal(row: list[str]) -> bool:
    non_empty = [c for c in row if c.strip()]
    if not non_empty:
        return False
    if any(match_channel_label(c) for c in non_empty):
        return True
    if any(has_metric_token(c) for c in non_empty):
        return True
    if any(looks_like_timestamp_header(c) for c in non_empty):
        return True
    return _row_string_ratio(row) >= 0.5 and len(non_empty) >= 1


def _is_group_row(row: list[str]) -> bool:
    """Sparse row: few filled cells relative to width (merged group labels)."""
    non_empty = [c for c in row if c.strip()]
    if not non_empty:
        return False
    width = max(len(row), 1)
    fill = len(non_empty) / width
    # Group rows are sparse OR have long labels spanning concepts
    if fill <= 0.45 and _row_string_ratio(row) >= 0.8:
        return True
    # Also: majority blanks under a merge that wasn't propagated yet
    return fill <= 0.35 and len(non_empty) >= 1


def _is_leaf_row(row: list[str]) -> bool:
    non_empty = [c for c in row if c.strip()]
    if len(non_empty) < 2:
        return False
    if _row_string_ratio(row) < 0.55:
        return False
    channel_hits = sum(1 for c in non_empty if match_channel_label(c))
    metric_hits = sum(1 for c in non_empty if has_metric_token(c))
    return channel_hits >= 2 or metric_hits >= 2 or len(non_empty) >= max(4, int(len(row) * 0.25))


def stitch_header_rows(header_rows: list[list[str]]) -> list[StitchedColumn]:
    """Forward-fill group labels and combine with leaf sub-headers.

    - 1 row: leaf = that row; no group
    - 2 rows: row0 = group (ffill), row1 = leaf
    - 3 rows: row0 = group (ffill), row1 = category (ffill), row2 = leaf;
      primary candidate prefers leaf, then ``category leaf``, display uses all parts
    """
    if not header_rows:
        return []
    rows = pad_matrix([[cell_to_str(c) for c in r] for r in header_rows])
    width = len(rows[0])
    n = len(rows)

    if n == 1:
        leaf = [c.strip() for c in rows[0]]
        group = [""] * width
        mid = [""] * width
    elif n == 2:
        group = ffill_row([c.strip() for c in rows[0]])
        leaf = [c.strip() for c in rows[1]]
        mid = [""] * width
        # If top looks denser than bottom, swap (leaf on top is rare but defensive)
        if _is_leaf_row(rows[0]) and _is_group_row(rows[1]):
            group = ffill_row([c.strip() for c in rows[1]])
            leaf = [c.strip() for c in rows[0]]
    else:
        # Use first as group, last as leaf, middle as category
        group = ffill_row([c.strip() for c in rows[0]])
        mid = ffill_row([c.strip() for c in rows[-2]]) if n >= 3 else [""] * width
        leaf = [c.strip() for c in rows[-1]]

    sibling_leaves = [c for c in leaf if c]
    columns: list[StitchedColumn] = []
    for j in range(width):
        g = group[j].strip() if j < len(group) else ""
        m = mid[j].strip() if j < len(mid) else ""
        lf = leaf[j].strip() if j < len(leaf) else ""

        # Vertical merge: leaf blank but group present (e.g. Date & Time spanning 2 rows)
        if not lf and g and not m:
            lf = g
            g = ""
        if not lf and m:
            lf = m
            m = ""

        parts = [p for p in (g, m, lf) if p]
        # Avoid "Date & Time Date & Time" duplication
        deduped: list[str] = []
        for p in parts:
            if not deduped or normalize_header(p) != normalize_header(deduped[-1]):
                deduped.append(p)
        display = " ".join(deduped) if deduped else ""
        primary = lf or m or g or display

        ch: ChannelMatch | None = classify_stitched_column(
            group=g or m,
            leaf=lf or primary,
            sibling_leaves=sibling_leaves,
        )
        # Also try primary alone
        if ch is None and primary:
            ch = classify_stitched_column(group=g, leaf=primary, sibling_leaves=sibling_leaves)

        columns.append(
            StitchedColumn(
                index=j,
                display_name=display,
                primary_candidate=primary,
                group_label=g,
                leaf_label=lf,
                field_type=ch.field_type if ch else None,
                channel_index=ch.channel_index if ch else None,
                confidence=0.95 if ch else (0.85 if display else 0.3),
            )
        )
    return columns


def _is_ambiguous_stitch(cols: list[StitchedColumn], block_rows: list[list[str]]) -> bool:
    if not cols:
        return True
    blanks = sum(1 for c in cols if not (c.display_name or "").strip())
    if blanks > max(2, len(cols) // 4):
        return True
    # Many Column_N-like empties after stitch
    if len(block_rows) >= 2:
        channel_cols = [c for c in cols if c.field_type == "string_current_channel"]
        # Group says string currents but we found < 2 channels → ambiguous
        groups = {c.group_label for c in cols if c.group_label}
        if any(re.search(r"string", g, re.I) for g in groups) and len(channel_cols) < 2:
            return True
    return False


def apply_stitched_headers(
    matrix: list[list[str]],
    block: HeaderBlock,
    *,
    prefer_primary: bool = False,
) -> list[list[str]]:
    """Replace the header block with a single stitched header row + remaining data."""
    rows = pad_matrix(matrix)
    names = [
        (c.primary_candidate if prefer_primary else c.display_name) or c.primary_candidate or f"Column_{c.index + 1}"
        for c in block.columns
    ]
    body = rows[block.end_row + 1 :]
    return [names] + body
