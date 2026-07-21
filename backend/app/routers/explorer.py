"""Data preview, plant architecture view, and Analytics Lab timeseries for a job."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.app.auth.deps import enforce_csrf, get_optional_user
from backend.app.config import Settings, get_settings
from backend.app.database import get_db
from backend.app.models import Job, User
from backend.app.routers.intake import _get_job_or_404
from backend.app.routers.upload import ALLOWED_EXTENSIONS, EXCEL_EXTENSIONS, _is_allowed
from backend.app.services.excel_parser import ExcelConversionError, parse_excel_to_csv
from backend.app.services.explorer_service import (
    export_data_csv_bytes,
    get_architecture_view,
    list_equipment,
    list_signals,
    preview_data,
    query_timeseries,
)
from backend.app.services.merge_uploads import merge_csv_files
from backend.app.services.storage import UploadTooLargeError, job_paths, sanitize_filename, save_upload_stream

router = APIRouter(prefix="/api/jobs", tags=["explorer"])


@router.get("/{job_id}/data-preview")
def data_preview(
    job_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    start: str | None = Query(None, description="Inclusive start datetime (ISO / UTC)"),
    end: str | None = Query(None, description="Inclusive end datetime (ISO / UTC)"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
):
    job = _get_job_or_404(db, job_id, user)
    paths = job_paths(settings.job_root_path, job_id)
    try:
        body = preview_data(
            paths.canonical_dir,
            paths.raw_dir / "input.csv",
            offset=offset,
            limit=limit,
            start=start,
            end=end,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Could not load data preview: {exc}") from exc
    manifest = paths.raw_dir / "sources_manifest.json"
    if manifest.exists():
        body["upload_sources"] = json.loads(manifest.read_text(encoding="utf-8")).get("sources", [])
    body["original_filename"] = job.original_filename
    return body


@router.get("/{job_id}/data-export.csv")
def data_export_csv(
    job_id: str,
    start: str | None = Query(None),
    end: str | None = Query(None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
):
    """Download dataset as CSV (optional start/end window)."""
    _get_job_or_404(db, job_id, user)
    paths = job_paths(settings.job_root_path, job_id)
    try:
        content = export_data_csv_bytes(
            paths.canonical_dir,
            paths.raw_dir / "input.csv",
            start=start,
            end=end,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Could not export CSV: {exc}") from exc
    if not content:
        raise HTTPException(404, "No data available to export for this job.")
    suffix = "window" if (start or end) else "data"
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="pic-lite-{job_id[:8]}-{suffix}.csv"'},
    )


@router.get("/{job_id}/architecture-view")
def architecture_view(
    job_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
):
    job = _get_job_or_404(db, job_id, user)
    paths = job_paths(settings.job_root_path, job_id)
    try:
        return get_architecture_view(job.plant_config_json, canonical_dir=paths.canonical_dir)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Could not load architecture: {exc}") from exc


@router.get("/{job_id}/explorer/equipment")
def explorer_equipment(
    job_id: str,
    level: str = Query("inverter"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
):
    _get_job_or_404(db, job_id, user)
    paths = job_paths(settings.job_root_path, job_id)
    try:
        ids = list_equipment(paths.canonical_dir, paths.raw_dir / "input.csv", level)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Could not load equipment list: {exc}") from exc
    return {"level": level, "equipment_ids": ids}


@router.get("/{job_id}/explorer/signals")
def explorer_signals(
    job_id: str,
    level: str = Query("inverter"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
):
    _get_job_or_404(db, job_id, user)
    paths = job_paths(settings.job_root_path, job_id)
    try:
        signals = list_signals(paths.canonical_dir, paths.raw_dir / "input.csv", level)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Could not load signals: {exc}") from exc
    return {"level": level, "signals": signals}


@router.get("/{job_id}/explorer/timeseries")
def explorer_timeseries(
    job_id: str,
    equipment_ids: str = Query(..., description="Comma-separated equipment IDs"),
    signals: str = Query(..., description="Comma-separated canonical signal names"),
    max_points: int = Query(3000, ge=100, le=10000),
    start: str | None = Query(None, description="Inclusive start datetime (ISO / UTC)"),
    end: str | None = Query(None, description="Inclusive end datetime (ISO / UTC)"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
):
    _get_job_or_404(db, job_id, user)
    paths = job_paths(settings.job_root_path, job_id)
    eq = [x.strip() for x in equipment_ids.split(",") if x.strip()]
    sig = [x.strip() for x in signals.split(",") if x.strip()]
    if not eq or not sig:
        raise HTTPException(400, "Provide at least one equipment ID and one signal.")
    return query_timeseries(
        paths.canonical_dir,
        paths.raw_dir / "input.csv",
        eq,
        sig,
        max_points=max_points,
        start=start,
        end=end,
    )


@router.post("/{job_id}/append-upload")
async def append_upload(
    job_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
    _: None = Depends(enforce_csrf),
):
    """Add another SCADA report to an existing job (merged into raw/input.csv)."""
    job = _get_job_or_404(db, job_id, user)
    if job.state in ("processing", "completed", "failed"):
        raise HTTPException(400, "Cannot append files after analysis has started or finished. Start a new job.")
    filename = sanitize_filename(file.filename or "upload.csv")
    if not _is_allowed(filename):
        raise HTTPException(400, "Accepted formats: .csv, .csv.gz, .xlsx, .xlsm, .xls.")

    paths = job_paths(settings.job_root_path, job_id)
    raw_dir = paths.raw_dir
    lower = filename.lower()
    is_excel = any(lower.endswith(ext) for ext in EXCEL_EXTENSIONS)
    limits = settings.limits
    max_bytes = limits.max_compressed_upload_mb * 1024 * 1024

    extra_path = raw_dir / f"extra_{len(list(raw_dir.glob('extra_*')))}{Path(lower).suffix if is_excel else '.csv'}"
    csv_path = raw_dir / "input.csv"
    manifest_path = raw_dir / "sources_manifest.json"

    try:
        if is_excel:
            await save_upload_stream(file, extra_path, max_bytes)
            converted = raw_dir / f"{extra_path.stem}.csv"
            parse_excel_to_csv(
                extra_path,
                converted,
                max_decompressed_bytes=limits.max_decompressed_upload_mb * 1024 * 1024,
                max_rows=limits.max_rows,
            )
            extra_path.unlink(missing_ok=True)
            extra_path = converted
        else:
            await save_upload_stream(file, extra_path, max_bytes)
    except (UploadTooLargeError, ExcelConversionError) as exc:
        raise HTTPException(400, str(exc)) from exc

    sources = [csv_path] if csv_path.exists() else []
    sources.append(extra_path)
    row_count, names = merge_csv_files(sources, csv_path, manifest_path)

    job.progress_message = f"Merged {len(names)} report(s) — {row_count:,} total rows."
    db.add(job)
    db.commit()
    return {"job_id": job_id, "row_count": row_count, "sources": names, "state": job.state}
