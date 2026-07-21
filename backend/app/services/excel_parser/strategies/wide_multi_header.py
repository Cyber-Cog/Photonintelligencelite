"""Wide multi-row header inverter reports (INVERTER N blocks).

Handles both:
  - Timestamp leaf on the metric row (older fixtures)
  - Timestamp label on the device/group row with blank leaf under it (real plant exports)
"""
from __future__ import annotations

from analytics.preprocessing.timestamps import normalise_timestamp, parse_timestamp
from backend.app.services.excel_parser.headers import (
    TIDY_FIELDS,
    ffill_row,
    has_metric_token,
    inverter_id_from_label,
    looks_like_timestamp_header,
    map_metric,
    normalize_header,
    pad_matrix,
)
from backend.app.services.excel_parser.types import LayoutKind, ParseReport, StrategyResult


def try_wide_multi_header(matrix: list[list[str]], *, sheet_name: str) -> StrategyResult | None:
    if not matrix:
        return None
    rows = pad_matrix(matrix)
    width = len(rows[0]) if rows else 0
    if width < 4:
        return None

    device_idx = _find_device_row(rows)
    if device_idx is None:
        return None

    leaf_idx = _find_leaf_row(rows, device_idx)
    if leaf_idx is None:
        return None

    category_idx: int | None = None
    if leaf_idx - device_idx >= 2:
        category_idx = leaf_idx - 1

    device_row = ffill_row(rows[device_idx])
    category_row = ffill_row(rows[category_idx]) if category_idx is not None else [""] * width
    leaf_row = [c.strip() for c in rows[leaf_idx]]

    ts_col = _find_timestamp_column(rows, device_idx, leaf_idx, leaf_row, device_row)
    if ts_col is None:
        return None

    col_map: dict[int, tuple[str, str]] = {}
    for j in range(width):
        if j == ts_col:
            continue
        device_id = inverter_id_from_label(device_row[j]) if device_row[j] else None
        if device_id is None:
            continue
        metric = map_metric(category_row[j], leaf_row[j])
        if metric is None:
            continue
        col_map[j] = (device_id, metric)

    if not col_map:
        return None

    devices = sorted({d for d, _ in col_map.values()})
    used_metrics = {m for _, m in col_map.values()}
    can_derive_dc = (
        "DC Power (kW)" not in used_metrics
        and "DC Voltage (V)" in used_metrics
        and "DC Current (A)" in used_metrics
    )
    if can_derive_dc:
        used_metrics.add("DC Power (kW)")

    header = [f for f in TIDY_FIELDS if f in {"Timestamp", "Equipment ID"} or f in used_metrics]
    out: list[list[str]] = [header]
    warnings: list[str] = []
    parse_ok = 0
    parse_fail = 0

    for row in rows[leaf_idx + 1 :]:
        raw_ts = row[ts_col].strip() if ts_col < len(row) else ""
        if not raw_ts:
            continue
        norm = normalise_timestamp(raw_ts)
        if norm is None:
            # Keep raw if unparseable — validation will flag; don't invent
            parse_fail += 1
            if parse_fail <= 3:
                warnings.append(f"Unparseable timestamp sample: {raw_ts[:60]}")
            ts = raw_ts
        else:
            parse_ok += 1
            ts = norm

        per_device: dict[str, dict[str, str]] = {d: {} for d in devices}
        for j, (device_id, metric) in col_map.items():
            val = row[j].strip() if j < len(row) else ""
            if val:
                per_device[device_id][metric] = val

        for device_id in devices:
            metrics = per_device.get(device_id, {})
            if not metrics:
                continue
            if can_derive_dc and "DC Power (kW)" not in metrics:
                try:
                    metrics["DC Power (kW)"] = str(
                        round(float(metrics["DC Voltage (V)"]) * float(metrics["DC Current (A)"]) / 1000.0, 6)
                    )
                except (ValueError, KeyError):
                    pass
            out.append(
                [
                    ts if f == "Timestamp" else device_id if f == "Equipment ID" else metrics.get(f, "")
                    for f in header
                ]
            )

    if len(out) <= 1:
        return None

    data_rows = len(out) - 1
    total_ts_attempts = parse_ok + parse_fail
    ts_ratio = parse_ok / total_ts_attempts if total_ts_attempts else 0.0
    has_ac = "AC Power (kW)" in header
    confidence = 0.45
    confidence += 0.25 if len(devices) >= 1 else 0.0
    confidence += 0.15 if has_ac else 0.0
    confidence += 0.15 * min(ts_ratio, 1.0)
    if can_derive_dc:
        warnings.append("DC Power (kW) derived from DC Voltage × DC Current / 1000.")

    header_rows = [device_idx]
    if category_idx is not None:
        header_rows.append(category_idx)
    header_rows.append(leaf_idx)

    report = ParseReport(
        layout=LayoutKind.WIDE_MULTI_HEADER.value,
        strategy="wide_multi_header",
        sheet_name=sheet_name,
        confidence=round(min(confidence, 0.99), 3),
        header_rows=header_rows,
        timestamp_column="Timestamp",
        inverters_found=devices,
        columns_mapped=header,
        row_count=data_rows,
        warnings=warnings,
    )
    if not has_ac:
        report.warnings.append("AC Power (kW) not found in mapped columns — check category/leaf headers.")
        report.confidence = min(report.confidence, 0.5)
    if ts_ratio < 0.5 and total_ts_attempts > 0:
        report.warnings.append(
            f"Only {parse_ok}/{total_ts_attempts} timestamps parsed cleanly. "
            "Confirm the Date/Time column format."
        )
        report.confidence = min(report.confidence, 0.5)

    if report.confidence < 0.55:
        report.error = (
            f"Low confidence ({report.confidence}) on sheet '{sheet_name}'. "
            f"Found devices={devices}, columns={header}. "
            "Remap columns in Setup or supply a clearer export."
        )
        return None

    return StrategyResult(rows=out, report=report)


def _find_device_row(rows: list[list[str]]) -> int | None:
    best_idx: int | None = None
    best_hits = 0
    for i, row in enumerate(rows[:40]):
        hits = [inverter_id_from_label(c) for c in row if c.strip()]
        n = sum(1 for h in hits if h)
        if n > best_hits:
            best_hits = n
            best_idx = i
    return best_idx if best_hits >= 1 else None


def _find_leaf_row(rows: list[list[str]], device_idx: int) -> int | None:
    """Leaf metric row: voltage/current/power tokens; may or may not include timestamp label."""
    best_idx: int | None = None
    best_score = 0.0
    for i in range(device_idx, min(device_idx + 6, len(rows))):
        row = rows[i]
        # Skip pure device-label rows (unless they also carry many metrics — rare)
        inv_hits = sum(1 for c in row if c.strip() and inverter_id_from_label(c))
        metric_hits = sum(1 for c in row if c.strip() and has_metric_token(c))
        ts_hit = 1.0 if any(looks_like_timestamp_header(c) for c in row) else 0.0
        # Prefer rows that look like metric leaves, not the INVERTER N banner
        if inv_hits >= 1 and metric_hits < 2:
            continue
        score = metric_hits + ts_hit * 2
        if score > best_score and metric_hits >= 2:
            best_score = score
            best_idx = i
    return best_idx


def _find_timestamp_column(
    rows: list[list[str]],
    device_idx: int,
    leaf_idx: int,
    leaf_row: list[str],
    device_row: list[str],
) -> int | None:
    # 1) Explicit timestamp header on leaf row
    for j, leaf in enumerate(leaf_row):
        if looks_like_timestamp_header(leaf):
            return j
    # 2) Timestamp header on device/group row (real InverterReport layout)
    for j, cell in enumerate(device_row):
        if looks_like_timestamp_header(cell):
            return j
    # 3) Any header row between device and leaf
    for i in range(device_idx, leaf_idx + 1):
        for j, cell in enumerate(rows[i]):
            if looks_like_timestamp_header(cell):
                return j
    # 4) First column whose data values parse as timestamps
    if leaf_idx + 1 >= len(rows):
        return None
    width = len(leaf_row)
    for j in range(min(width, 5)):
        samples = []
        for row in rows[leaf_idx + 1 : leaf_idx + 16]:
            if j < len(row) and row[j].strip():
                samples.append(row[j].strip())
        if len(samples) < 2:
            continue
        ok = sum(1 for s in samples if parse_timestamp(s) is not None)
        if ok / len(samples) >= 0.7:
            return j
    return None
