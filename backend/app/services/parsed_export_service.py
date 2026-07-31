"""Build parsed-Excel downloads for a job (Setup / Validate offline verification)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from analytics.common.parsed_export import (
    build_parsed_workbook_bytes,
    canonical_frame_to_scada_rows,
    parsed_export_filename,
    plant_name_from_config,
    read_raw_csv_headers,
    remap_csv_to_scada_rows,
    resolve_source_columns_for_official,
)
from backend.app.services.explorer_service import _has_canonical, _iter_partition_frames


def _rows_have_substance(rows: list[list[Any]]) -> bool:
    """True when at least one row has a timestamp or metric value worth exporting."""
    for row in rows:
        for val in row:
            if val is None:
                continue
            if isinstance(val, float) and val != val:
                continue
            if str(val).strip():
                return True
    return False


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
    raw_headers = read_raw_csv_headers(raw_csv)
    if not raw_headers:
        return []
    source_for_official = resolve_source_columns_for_official(
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
    # Do not pass a fixed column list — string/scb partitions may omit device_id etc.
    for part in _iter_partition_frames(canonical_dir, columns=None):
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
    canonical_rows = _scada_rows_from_canonical(canonical_dir, max_rows)
    # Raw CSV can be wide/OEM-shaped while Explorer reads normalized parquet — prefer
    # canonical when raw remap is empty or all blank cells (headers-only download).
    if _rows_have_substance(canonical_rows) and not _rows_have_substance(scada_rows):
        scada_rows = canonical_rows
    elif not _rows_have_substance(scada_rows):
        scada_rows = canonical_rows or scada_rows

    content = build_parsed_workbook_bytes(
        scada_rows=scada_rows,
        column_to_canonical=column_to_canonical,
        timestamp_column=timestamp_column,
        plant=_plant_dict(plant_config_json),
    )
    filename = parsed_export_filename(job_id, plant_name_from_config(plant_config_json))
    return content, filename
