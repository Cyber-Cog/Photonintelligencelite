"""Build parsed-Excel downloads for a job (Setup / Validate offline verification)."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Mapping

from analytics.common.parsed_export import (
    build_parsed_workbook_bytes,
    canonical_frame_to_scada_rows,
    parsed_export_filename,
    plant_name_from_config,
    remap_csv_to_scada_rows,
    source_columns_for_official,
)
from backend.app.services.explorer_service import _has_canonical, _iter_partition_frames

_CANONICAL_EXPORT_COLS = [
    "timestamp_utc",
    "device_id",
    "ac_power_kw",
    "dc_power_kw",
    "dc_current_a",
    "dc_voltage_v",
    "poa_w_m2",
    "ghi_w_m2",
    "module_temp_c",
    "ambient_temp_c",
]


def _plant_dict(plant_config_json: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not plant_config_json:
        return None
    plant = plant_config_json.get("plant") if isinstance(plant_config_json.get("plant"), dict) else plant_config_json
    return plant if isinstance(plant, dict) else None


def _scada_rows_from_raw(
    raw_csv: Path,
    column_to_canonical: Mapping[str, str] | None,
    timestamp_column: str | None,
    max_rows: int,
) -> list[list[Any]]:
    if not raw_csv.exists():
        return []
    with raw_csv.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        try:
            raw_headers = next(reader)
        except StopIteration:
            return []
    raw_headers = [str(h) for h in raw_headers]
    source_for_official = source_columns_for_official(
        column_to_canonical, timestamp_column, raw_headers
    )
    if not any(source_for_official.values()):
        return []
    return remap_csv_to_scada_rows(raw_csv, source_for_official, max_rows)


def _scada_rows_from_canonical(canonical_dir: Path, max_rows: int) -> list[list[Any]]:
    if not _has_canonical(canonical_dir):
        return []
    records: list[dict] = []
    remaining = max_rows
    for part in _iter_partition_frames(canonical_dir, columns=_CANONICAL_EXPORT_COLS):
        if remaining <= 0:
            break
        take = part.iloc[:remaining]
        records.extend(take.to_dict(orient="records"))
        remaining -= len(take)
    return canonical_frame_to_scada_rows(records, max_rows=max_rows)


def export_parsed_excel(
    *,
    job_id: str,
    raw_csv: Path,
    canonical_dir: Path,
    mapping_json: Mapping[str, Any] | None,
    plant_config_json: Mapping[str, Any] | None,
    max_rows: int = 200_000,
) -> tuple[bytes, str]:
    """Return (xlsx_bytes, download_filename).

    Prefers remapped ``raw/input.csv`` (faithful post-parse tidy). Falls back to
    canonical parquet when raw is missing/empty but validation has standardized.
    """
    mapping = dict(mapping_json or {})
    column_to_canonical = mapping.get("column_to_canonical") or {}
    timestamp_column = mapping.get("timestamp_column")

    scada_rows = _scada_rows_from_raw(
        raw_csv, column_to_canonical, timestamp_column, max_rows
    )
    if not scada_rows:
        scada_rows = _scada_rows_from_canonical(canonical_dir, max_rows)

    content = build_parsed_workbook_bytes(
        scada_rows=scada_rows,
        column_to_canonical=column_to_canonical,
        timestamp_column=timestamp_column,
        plant=_plant_dict(plant_config_json),
    )
    filename = parsed_export_filename(job_id, plant_name_from_config(plant_config_json))
    return content, filename
