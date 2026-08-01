"""Reshape wide SCADA CSV exports into tidy long form for mapping / analysis.

Historian trend reports often ship one column per (device × metric), e.g.
``ESSP_20MW ICR1 Inverter 1 Active Power (kW)``. Upload intelligence previously
scored the full header against aliases and only matched Timestamp.

This module detects that layout, melts to Timestamp + Equipment ID (+ optional
ICR ID) + metrics, and rewrites the CSV in place when confidence is high.
"""
from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from analytics.common.equipment_ids import derive_level, extract_parent_inverter
from analytics.common.wide_headers import (
    leaf_to_metric,
    looks_like_timestamp_header,
    parse_wide_device_column,
)
from analytics.preprocessing.timestamps import normalise_timestamp

logger = logging.getLogger("pic_lite.wide_csv_reshape")

_DELIMS = (",", ";", "\t", "|")


@dataclass
class WideReshapeReport:
    reshaped: bool = False
    strategy: str = "none"
    confidence: float = 0.0
    inverters_found: list[str] = field(default_factory=list)
    """Unique equipment ids after melt (may be inverter- or SCB-level)."""
    icr_ids: list[str] = field(default_factory=list)
    scb_ids: list[str] = field(default_factory=list)
    columns_mapped: list[str] = field(default_factory=list)
    row_count: int = 0
    warnings: list[str] = field(default_factory=list)
    delimiter: str = ","
    inverter_count: int = 0
    scb_count: int = 0
    string_count: int = 0

    def to_dict(self) -> dict:
        return {
            "reshaped": self.reshaped,
            "strategy": self.strategy,
            "confidence": self.confidence,
            "inverters_found": self.inverters_found,
            "icr_ids": self.icr_ids,
            "scb_ids": self.scb_ids,
            "columns_mapped": self.columns_mapped,
            "row_count": self.row_count,
            "warnings": self.warnings,
            "delimiter": self.delimiter,
            "inverter_count": self.inverter_count,
            "scb_count": self.scb_count,
            "string_count": self.string_count,
        }


def _parent_inverter_id(equipment_id: str) -> str | None:
    """ICR1-INV-01-SCB-01 → ICR1-INV-01 (keeps ICR prefix; avoids collapsing INV-01 across ICRs)."""
    eid = (equipment_id or "").strip()
    if not eid:
        return None
    parts = re.split(r"-(?:SCB|SMB|MPPT)-", eid, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2 and parts[0]:
        return parts[0]
    return extract_parent_inverter(eid)


def _classify_melted_devices(devices: list[str]) -> tuple[list[str], list[str], list[str], list[str]]:
    """Split melted equipment ids into (inverters, scbs, strings, parent_inverters)."""
    invs: set[str] = set()
    scbs: set[str] = set()
    strings: set[str] = set()
    parent_invs: set[str] = set()
    for eid in devices:
        level = derive_level(eid)
        if level == "string":
            strings.add(eid)
            parent = _parent_inverter_id(eid)
            if parent:
                parent_invs.add(parent)
        elif level == "scb":
            scbs.add(eid)
            parent = _parent_inverter_id(eid)
            if parent:
                parent_invs.add(parent)
        elif level == "inverter":
            invs.add(eid)
        else:
            invs.add(eid)
    if not invs and parent_invs:
        invs = parent_invs
    return sorted(invs), sorted(scbs), sorted(strings), sorted(parent_invs)


def sniff_delimiter(sample: str) -> str:
    counts = {d: sample.count(d) for d in _DELIMS}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def _find_header_line(text_lines: list[str], delim: str) -> int:
    """Skip junk/title rows; prefer a row with timestamp + wide metric hits."""
    best_i, best_score = 0, -1.0
    for i, line in enumerate(text_lines[:40]):
        if not line.strip():
            continue
        cells = [c.strip().strip('"') for c in line.split(delim)]
        if len(cells) < 2:
            continue
        score = 0.0
        if any(looks_like_timestamp_header(c) for c in cells):
            score += 3.0
        wide = sum(1 for c in cells if parse_wide_device_column(c) is not None)
        score += min(wide, 12) * 0.5
        # Prefer rows that look like headers (non-numeric majority)
        numericish = sum(1 for c in cells[1:6] if re.fullmatch(r"[-+]?\d+(\.\d+)?", c or ""))
        if numericish >= 3:
            score -= 2.0
        if score > best_score:
            best_score = score
            best_i = i
    return best_i if best_score >= 3.0 else 0


def _shared_plant_metric(header: str) -> str | None:
    """Plant/WMS columns without an inverter number (irradiance, temps)."""
    if parse_wide_device_column(header) is not None:
        return None
    if looks_like_timestamp_header(header):
        return None
    n = header.strip().lower()
    if "planttimestamp" in n.replace(" ", "") or n.replace(" ", "") == "planttimestamp":
        return None
    return leaf_to_metric(header)


def reshape_wide_csv(csv_path: Path, *, max_rows: int | None = None) -> WideReshapeReport:
    """If ``csv_path`` is a wide device×metric export, melt and overwrite it.

    Returns a report; ``reshaped=False`` leaves the file untouched.
    """
    report = WideReshapeReport()
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return report

    raw = csv_path.read_bytes()
    # Strip UTF-8 BOM
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    lines = text.splitlines()
    if not lines:
        return report

    delim = sniff_delimiter("\n".join(lines[:5]))
    report.delimiter = delim
    header_idx = _find_header_line(lines, delim)
    header = [c.strip().strip('"') for c in lines[header_idx].split(delim)]
    if len(header) < 3:
        return report

    ts_cols = [i for i, h in enumerate(header) if looks_like_timestamp_header(h)]
    # Prefer exact "timestamp" over planttimestamp
    ts_col = None
    for i in ts_cols:
        if normalize_simple(header[i]) in {"timestamp", "date time", "datetime", "date"}:
            ts_col = i
            break
    if ts_col is None and ts_cols:
        ts_col = ts_cols[0]
    if ts_col is None:
        return report

    col_map: dict[int, tuple[str, str, str | None]] = {}  # idx -> (equip, metric, icr)
    shared: dict[int, str] = {}
    for j, h in enumerate(header):
        if j == ts_col or not h:
            continue
        # Skip secondary plant timestamps
        if looks_like_timestamp_header(h) and j != ts_col:
            continue
        parsed = parse_wide_device_column(h)
        if parsed is not None:
            col_map[j] = (parsed.equipment_id, parsed.metric, parsed.icr_id)
            continue
        shared_metric = _shared_plant_metric(h)
        if shared_metric:
            shared[j] = shared_metric

    devices = sorted({eq for eq, _, _ in col_map.values()})
    if len(col_map) < 2 or len(devices) < 1:
        return report
    # Need a real wide layout: at least 2 metric columns (or 1 device with 2 metrics)
    if len(col_map) < 2:
        return report

    icr_ids = sorted({icr for _, _, icr in col_map.values() if icr})
    used_metrics = {m for _, m, _ in col_map.values()} | set(shared.values())
    can_derive = (
        "DC Power (kW)" not in used_metrics
        and "DC Voltage (V)" in used_metrics
        and "DC Current (A)" in used_metrics
    )
    if can_derive:
        used_metrics.add("DC Power (kW)")
        report.warnings.append("DC Power derived from V*I.")

    out_header = ["Timestamp", "Equipment ID"]
    if icr_ids:
        out_header.append("ICR ID")
    for name in (
        "AC Power (kW)",
        "DC Power (kW)",
        "DC Current (A)",
        "DC Voltage (V)",
        "Irradiance (W/m2)",
        "GHI (W/m2)",
        "Module Temp (C)",
        "Ambient Temp (C)",
    ):
        if name in used_metrics:
            out_header.append(name)

    # Stream data rows
    data_lines = lines[header_idx + 1 :]
    if max_rows is not None:
        data_lines = data_lines[:max_rows]

    out_rows: list[list[str]] = [out_header]
    for line in data_lines:
        if not line.strip():
            continue
        cells = next(csv.reader([line], delimiter=delim))
        # Pad
        if len(cells) < len(header):
            cells = cells + [""] * (len(header) - len(cells))
        raw_ts = cells[ts_col].strip() if ts_col < len(cells) else ""
        if not raw_ts:
            continue
        ts = normalise_timestamp(raw_ts) or raw_ts

        shared_vals = {shared[j]: cells[j].strip() for j in shared if j < len(cells) and cells[j].strip()}

        per: dict[str, dict[str, str]] = {d: {} for d in devices}
        icr_for: dict[str, str | None] = {d: None for d in devices}
        for j, (dev, metric, icr) in col_map.items():
            val = cells[j].strip() if j < len(cells) else ""
            if val:
                per[dev][metric] = val
            if icr:
                icr_for[dev] = icr

        for dev in devices:
            metrics = dict(per[dev])
            if not metrics and not shared_vals:
                continue
            metrics.update({k: v for k, v in shared_vals.items() if k not in metrics})
            if not metrics:
                continue
            if can_derive and "DC Power (kW)" not in metrics:
                try:
                    metrics["DC Power (kW)"] = str(
                        round(
                            float(metrics["DC Voltage (V)"])
                            * float(metrics["DC Current (A)"])
                            / 1000.0,
                            6,
                        )
                    )
                except (ValueError, KeyError):
                    pass
            row = []
            for f in out_header:
                if f == "Timestamp":
                    row.append(ts)
                elif f == "Equipment ID":
                    row.append(dev)
                elif f == "ICR ID":
                    row.append(icr_for.get(dev) or "")
                else:
                    row.append(metrics.get(f, ""))
            out_rows.append(row)

    if len(out_rows) <= 1:
        return report

    # Write tidy CSV (comma)
    tmp = csv_path.with_suffix(".tidy.tmp.csv")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerows(out_rows)
    tmp.replace(csv_path)

    invs, scbs, strings, _parents = _classify_melted_devices(devices)
    report.reshaped = True
    report.strategy = "wide_prefixed_device_melt"
    report.confidence = 0.92
    # Keep equipment ids for downstream; prefer parent inverters when melt was SCB-only.
    report.inverters_found = invs or devices
    report.icr_ids = icr_ids
    report.scb_ids = scbs
    report.inverter_count = len(invs)
    report.scb_count = len(scbs)
    report.string_count = len(strings)
    report.columns_mapped = out_header
    report.row_count = len(out_rows) - 1
    if scbs and not any(derive_level(d) == "inverter" for d in devices):
        report.warnings.append(
            f"Melted {len(scbs)} SCB-level column(s) (e.g. O/P Current) into Equipment ID + metrics."
        )
    logger.info(
        "Reshaped wide CSV %s → %d rows, %d equipment, %d inv, %d scb, icrs=%s",
        csv_path.name,
        report.row_count,
        len(devices),
        report.inverter_count,
        report.scb_count,
        icr_ids,
    )
    return report


def normalize_simple(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def maybe_reshape_wide_csv(csv_path: Path, *, max_rows: int | None = None) -> WideReshapeReport:
    """Safe entrypoint: never raise; leave file unchanged on failure."""
    try:
        # Already tidy? Equipment ID + few metric cols — skip
        peek = pd.read_csv(csv_path, nrows=0)
        cols = [str(c) for c in peek.columns]
        if any(c.lower().replace(" ", "") in {"equipmentid", "equipment_id", "device_id"} for c in cols):
            # Still allow reshape only if many leftover wide columns remain
            from analytics.common.wide_headers import count_wide_device_columns

            wide_n, _ = count_wide_device_columns(cols)
            if wide_n < 2:
                return WideReshapeReport(strategy="already_tidy")
        return reshape_wide_csv(csv_path, max_rows=max_rows)
    except Exception as exc:  # noqa: BLE001
        logger.exception("wide CSV reshape failed: %s", exc)
        return WideReshapeReport(warnings=[f"reshape_failed: {exc}"])
