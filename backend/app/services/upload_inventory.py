"""Per-file upload inventory for the Upload review screen."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import pandas as pd

from analytics.common.aliasing import score_columns
from backend.app.services.mapping_service import suggest_mapping
from backend.app.services.merge_uploads import _classify, _timestamp_col

# Canonical fields surfaced on the Upload “required signals” checklist.
CHECKLIST_FIELDS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("timestamp", "Timestamp", ()),
    ("device_id", "Equipment ID", ("inverter_id", "scb_id", "string_id")),
    ("ac_power_kw", "AC power (kW)", ()),
    ("dc_power_kw", "DC power (kW)", ()),
    ("dc_current_a", "String / DC current (A)", ()),
    ("dc_voltage_v", "DC voltage (V)", ()),
    ("poa_w_m2", "Irradiance (POA or GHI)", ("ghi_w_m2",)),
)

_SETUP_ONLY_CHECKS: tuple[tuple[str, str], ...] = (
    ("inverter_nameplate_kw", "Inverter nameplate kW"),
)


def _present_fields(columns: Iterable[str], suggestions: Iterable[Any] | None = None) -> set[str]:
    """Canonical fields detected in a file's headers."""
    cols = [str(c) for c in columns if str(c).strip() and str(c) != "_source_file"]
    present: set[str] = set()
    for cand in score_columns(cols):
        if cand.canonical_field and cand.confidence >= 0.6:
            present.add(cand.canonical_field)
    if suggestions:
        for s in suggestions:
            field = getattr(s, "canonical_field", None) or (s.get("canonical_field") if isinstance(s, dict) else None)
            if field and field != "ignore":
                present.add(str(field))
    return present


def _detected_as_label(kind: str, present: set[str], unmapped: int) -> str:
    if unmapped >= 3 and kind == "other":
        return f"Registry — {unmapped} cols unmapped"
    if "dc_current_a" in present and ("string_id" in present or "scb_id" in present):
        return "String current"
    if "dc_current_a" in present and unmapped <= 2:
        return "String current"
    if "ac_power_kw" in present and ("dc_power_kw" in present or "dc_current_a" in present):
        return "Inverter AC/DC"
    if any(f in present for f in ("poa_w_m2", "ghi_w_m2", "module_temp_c", "ambient_temp_c")):
        return "Irradiance / temp"
    if kind == "weather":
        return "Irradiance / temp"
    if kind == "inverter":
        return "Inverter AC/DC"
    if unmapped > 0:
        return f"Other — {unmapped} cols unmapped"
    return "SCADA data"


def _date_range(df: pd.DataFrame) -> tuple[str | None, str | None]:
    ts = _timestamp_col(df)
    if not ts:
        return None, None
    series = pd.to_datetime(df[ts], errors="coerce").dropna()
    if series.empty:
        return None, None
    start = series.min()
    end = series.max()
    fmt = lambda t: t.strftime("%Y-%m-%d %H:%M") if pd.notna(t) else None  # noqa: E731
    return fmt(start), fmt(end)


def inventory_item_from_csv(
    csv_path: Path,
    *,
    display_name: str,
    sheet_name: str | None = None,
    parse_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarise one converted CSV part for the Upload review table."""
    df = pd.read_csv(csv_path, nrows=500_000, low_memory=False)
    columns = [c for c in df.columns if c != "_source_file"]
    present = _present_fields(columns)
    suggestions = suggest_mapping(columns)
    mapped_cols = sum(1 for s in suggestions if s.canonical_field and s.canonical_field != "ignore")
    unmapped = max(0, len(columns) - mapped_cols)
    kind = _classify(df)
    start, end = _date_range(df)
    if parse_report:
        sheet_name = sheet_name or parse_report.get("sheet_name")
    return {
        "filename": display_name,
        "sheet_name": sheet_name,
        "row_count": int(len(df)),
        "detected_as": _detected_as_label(kind, present, unmapped),
        "signals_present": sorted(present),
        "unmapped_column_count": unmapped,
        "date_range_start": start,
        "date_range_end": end,
    }


def build_inventory_from_parts(
    parts: list[tuple[str, Path, Mapping[str, Any] | None]],
) -> list[dict[str, Any]]:
    """Build inventory from (display_filename, csv_path, optional parse_report dict)."""
    out: list[dict[str, Any]] = []
    for display_name, path, report in parts:
        if not path.exists():
            continue
        try:
            out.append(inventory_item_from_csv(path, display_name=display_name, parse_report=report))
        except Exception:  # noqa: BLE001
            out.append(
                {
                    "filename": display_name,
                    "sheet_name": (report or {}).get("sheet_name"),
                    "row_count": 0,
                    "detected_as": "Could not read",
                    "signals_present": [],
                    "unmapped_column_count": 0,
                    "date_range_start": None,
                    "date_range_end": None,
                }
            )
    return out


def write_upload_manifest(
    manifest_path: Path,
    *,
    files: list[dict[str, Any]],
    row_count: int,
    merge_strategy: str,
    source_names: list[str],
) -> None:
    manifest_path.write_text(
        json.dumps(
            {
                "sources": source_names,
                "row_count": row_count,
                "merge_strategy": merge_strategy,
                "files": files,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def read_upload_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def signal_checklist(
    suggestions: Iterable[Any],
    *,
    plant_config: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Job-level required-signal checklist for the Upload sidebar."""
    present: set[str] = set()
    for s in suggestions:
        field = getattr(s, "canonical_field", None) or (s.get("canonical_field") if isinstance(s, dict) else None)
        if field and field != "ignore":
            present.add(str(field))

    plant = plant_config or {}
    has_nameplate = bool(
        plant.get("inverter_capacity_kw")
        or plant.get("equipment_ratings")
        or plant.get("imported_inverter_capacity_kw")
    )

    items: list[dict[str, Any]] = []
    for field, label, alts in CHECKLIST_FIELDS:
        ok = field in present or any(a in present for a in alts)
        items.append({"id": field, "label": label, "present": ok, "setup_only": False})

    for field, label in _SETUP_ONLY_CHECKS:
        ok = has_nameplate if field == "inverter_nameplate_kw" else False
        items.append(
            {
                "id": field,
                "label": label,
                "present": ok,
                "setup_only": True,
                "hint": "Map in Setup" if not ok else None,
            }
        )
    return items


def inventory_from_job(paths, original_label: str | None = None) -> tuple[list[dict[str, Any]], int]:
    """Load stored inventory or rebuild a single-file summary from input.csv."""
    manifest = read_upload_manifest(paths.raw_dir / "sources_manifest.json")
    files = manifest.get("files") or []
    row_count = int(manifest.get("row_count") or 0)
    if files:
        return files, row_count

    csv_path = paths.raw_dir / "input.csv"
    if not csv_path.exists():
        return [], 0

    parse_report = None
    for p in sorted(paths.raw_dir.glob("parse_report*.json")):
        try:
            parse_report = json.loads(p.read_text(encoding="utf-8"))
            break
        except Exception:  # noqa: BLE001
            continue

    name = original_label or csv_path.name
    item = inventory_item_from_csv(csv_path, display_name=name, parse_report=parse_report)
    if not row_count:
        row_count = item.get("row_count") or 0
    return [item], row_count
