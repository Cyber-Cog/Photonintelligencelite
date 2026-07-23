"""Upload endpoint: streamed save, Excel→CSV conversion, bounded gzip decompression,
header inspection, and confidence-scored mapping suggestions. See docs/PRD.md §7.2, §7.4.

Excel conversion runs off the request thread (like demo prep) so Vercel→Render proxies
do not 502 when a wide workbook takes longer than the edge timeout (~30s).
"""
from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from analytics.core.job_states import JobState
from backend.app.auth.audit import record_audit
from backend.app.auth.deps import enforce_csrf, require_verified_user
from backend.app.auth.job_access import load_job_authorized
from backend.app.auth.rate_limit import client_ip
from backend.app.config import Settings, get_settings
from backend.app.database import SessionLocal, get_db
from backend.app.models import Job, User
from backend.app.schemas import ExcelParseReportOut, UploadResponse
from backend.app.services.excel_parser import ExcelConversionError, parse_excel_to_csv
from backend.app.services.merge_uploads import merge_csv_files
from backend.app.services.mapping_service import (
    detect_pack_match,
    find_saved_template,
    overlay_prior_mapping,
    read_header,
    requires_manual_mapping,
    suggest_mapping,
)
from backend.app.services.storage import (
    DecompressionBombError,
    UploadTooLargeError,
    decompress_gzip_bounded,
    job_paths,
    sanitize_filename,
    save_upload_stream,
)

router = APIRouter(prefix="/api", tags=["upload"])
logger = logging.getLogger("pic_lite.upload")

ALLOWED_EXTENSIONS = (".csv", ".csv.gz", ".xlsx", ".xlsm", ".xls")
EXCEL_EXTENSIONS = (".xlsx", ".xlsm", ".xls")

_BLOCKED_WHILE_RUNNING = {
    JobState.QUEUED.value,
    JobState.RUNNING.value,
    JobState.GENERATING_CHARTS.value,
    JobState.GENERATING_REPORT.value,
    JobState.CLEANED_UP.value,
}

_REPLACEABLE_STATES = {
    JobState.UPLOADED.value,
    JobState.PARSING.value,
    JobState.MAPPING.value,
    JobState.VALIDATING.value,
    JobState.NORMALIZING.value,
    JobState.FAILED.value,
    JobState.COMPLETED.value,
}


def _is_allowed(filename: str) -> bool:
    lower = filename.lower()
    return any(lower.endswith(ext) for ext in ALLOWED_EXTENSIONS)


def _clear_derived_outputs(settings: Settings, job_id: str) -> None:
    paths = job_paths(settings.job_root_path, job_id)
    for d in (paths.canonical_dir, paths.results_dir, paths.reports_dir, paths.charts_dir):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)


def _clear_raw_dir(settings: Settings, job_id: str) -> None:
    paths = job_paths(settings.job_root_path, job_id)
    if paths.raw_dir.exists():
        shutil.rmtree(paths.raw_dir, ignore_errors=True)
    paths.raw_dir.mkdir(parents=True, exist_ok=True)


def _pending_upload_response(job: Job) -> UploadResponse:
    """Returned while Excel→CSV still runs in the background."""
    return UploadResponse(
        job_id=job.id,
        state=job.state,
        detected_columns=[],
        mapping_suggestions=[],
        requires_manual_mapping=True,
        parse_report=None,
        looks_like_complete_pack=False,
        pack_match_ratio=0.0,
    )


async def _ingest_uploads(
    all_files: list[UploadFile],
    *,
    paths,
    limits,
    defer_excel: bool = False,
) -> tuple[list[Path], ExcelParseReportOut | None, str | None, bool]:
    """Save/convert uploads into raw_dir.

    Returns (converted_paths, parse_report, progress, excel_deferred).
    When defer_excel=True, Excel files are saved raw and conversion is skipped.
    """
    parse_report_out: ExcelParseReportOut | None = None
    converted_paths: list[Path] = []
    progress: str | None = None
    excel_deferred = False

    async def _ingest_one(upload: UploadFile, idx: int) -> Path:
        nonlocal parse_report_out, excel_deferred
        filename = sanitize_filename(upload.filename or f"upload_{idx}.csv")
        lower = filename.lower()
        is_gz = lower.endswith(".gz")
        is_excel = any(lower.endswith(ext) for ext in EXCEL_EXTENSIONS)
        max_bytes = limits.max_compressed_upload_mb * 1024 * 1024
        out_csv = paths.raw_dir / (f"part_{idx}.csv" if len(all_files) > 1 else "input.csv")
        if is_excel:
            excel_target = paths.raw_dir / f"upload_{idx}{Path(lower).suffix}"
            await save_upload_stream(upload, excel_target, max_bytes)
            if defer_excel:
                excel_deferred = True
                # Placeholder path — background worker writes the real CSV.
                return out_csv
            report_path = paths.raw_dir / f"parse_report_{idx}.json"
            _n, report = parse_excel_to_csv(
                excel_target,
                out_csv,
                max_decompressed_bytes=limits.max_decompressed_upload_mb * 1024 * 1024,
                max_rows=limits.max_rows,
                report_path=report_path,
            )
            if parse_report_out is None:
                parse_report_out = ExcelParseReportOut(**report.to_dict())
            excel_target.unlink(missing_ok=True)
        elif is_gz:
            raw_target = paths.raw_dir / f"input_{idx}.csv.gz"
            await save_upload_stream(upload, raw_target, max_bytes)
            decompress_gzip_bounded(
                raw_target,
                out_csv,
                max_decompressed_bytes=limits.max_decompressed_upload_mb * 1024 * 1024,
                max_ratio=limits.max_decompression_ratio,
            )
            raw_target.unlink(missing_ok=True)
        else:
            await save_upload_stream(upload, out_csv, max_bytes)
        return out_csv

    for i, uf in enumerate(all_files):
        converted_paths.append(await _ingest_one(uf, i))

    if excel_deferred:
        return converted_paths, None, "Saving Excel — parsing will continue in the background…", True

    csv_path = paths.raw_dir / "input.csv"
    manifest_path = paths.raw_dir / "sources_manifest.json"
    if len(converted_paths) > 1:
        row_count, names = merge_csv_files(converted_paths, csv_path, manifest_path)
        for p in converted_paths:
            if p != csv_path:
                p.unlink(missing_ok=True)
        progress = f"Merged {len(names)} report(s) — {row_count:,} rows."
    elif parse_report_out:
        inv_n = len(parse_report_out.inverters_found)
        progress = (
            f"Parsed {parse_report_out.layout} ({parse_report_out.strategy}): "
            f"{parse_report_out.row_count:,} rows, {inv_n} inverter(s), "
            f"confidence {parse_report_out.confidence:.0%}."
        )
    return converted_paths, parse_report_out, progress, False


def _convert_deferred_excels(paths, limits) -> tuple[ExcelParseReportOut | None, str | None]:
    """Convert any raw upload_*.xlsx left on disk, then merge into input.csv."""
    excel_files = sorted(
        p
        for p in paths.raw_dir.iterdir()
        if p.is_file() and p.suffix.lower() in EXCEL_EXTENSIONS and p.name.startswith("upload_")
    )
    if not excel_files:
        return None, None

    parse_report_out: ExcelParseReportOut | None = None
    converted: list[Path] = []
    # Also keep any CSV parts already written (mixed excel+csv uploads).
    existing_csvs = sorted(
        p for p in paths.raw_dir.iterdir() if p.is_file() and p.suffix.lower() == ".csv" and p.name.startswith("part_")
    )
    converted.extend(existing_csvs)

    multi = len(excel_files) + len(existing_csvs) > 1
    for excel_target in excel_files:
        # upload_0.xlsx → part_0.csv or input.csv
        stem = excel_target.stem  # upload_0
        idx_s = stem.split("_", 1)[-1]
        out_csv = paths.raw_dir / (f"part_{idx_s}.csv" if multi else "input.csv")
        report_path = paths.raw_dir / f"parse_report_{idx_s}.json"
        _n, report = parse_excel_to_csv(
            excel_target,
            out_csv,
            max_decompressed_bytes=limits.max_decompressed_upload_mb * 1024 * 1024,
            max_rows=limits.max_rows,
            report_path=report_path,
        )
        if parse_report_out is None:
            parse_report_out = ExcelParseReportOut(**report.to_dict())
        excel_target.unlink(missing_ok=True)
        converted.append(out_csv)

    csv_path = paths.raw_dir / "input.csv"
    manifest_path = paths.raw_dir / "sources_manifest.json"
    progress: str | None = None
    unique = list(dict.fromkeys(converted))
    if len(unique) > 1:
        row_count, names = merge_csv_files(unique, csv_path, manifest_path)
        for p in unique:
            if p != csv_path:
                p.unlink(missing_ok=True)
        progress = f"Merged {len(names)} report(s) — {row_count:,} rows."
    elif parse_report_out:
        inv_n = len(parse_report_out.inverters_found)
        progress = (
            f"Parsed {parse_report_out.layout} ({parse_report_out.strategy}): "
            f"{parse_report_out.row_count:,} rows, {inv_n} inverter(s), "
            f"confidence {parse_report_out.confidence:.0%}."
        )
    return parse_report_out, progress


def _finish_excel_parse(
    job_id: str,
    settings: Settings,
    *,
    prior_mapping: dict[str, str] | None = None,
    progress_fallback: str = "Reviewing detected columns…",
) -> None:
    """Heavy Excel→CSV off the request thread so proxies do not time out."""
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return
        paths = job_paths(settings.job_root_path, job_id)
        limits = settings.limits
        job.progress_message = "Parsing Excel workbook…"
        db.add(job)
        db.commit()

        parse_report_out, progress = _convert_deferred_excels(paths, limits)
        csv_path = paths.raw_dir / "input.csv"
        if not csv_path.exists():
            raise ExcelConversionError("Excel conversion finished but no CSV was produced.")

        # Touch mapping helpers so we fail early if the CSV is unreadable.
        _ = _build_upload_response(
            db,
            job,
            csv_path=csv_path,
            parse_report_out=parse_report_out,
            prior_mapping=prior_mapping,
        )

        job.state = JobState.MAPPING.value
        job.progress_message = progress or progress_fallback
        job.error_summary = None
        db.add(job)
        db.commit()
    except (UploadTooLargeError, DecompressionBombError) as exc:
        logger.warning("excel parse size limit job=%s: %s", job_id, exc)
        try:
            job = db.get(Job, job_id)
            if job is not None:
                job.state = JobState.FAILED.value
                job.error_summary = str(exc)
                job.progress_message = str(exc)
                db.add(job)
                db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("could not mark upload job failed job=%s", job_id)
    except ExcelConversionError as exc:
        logger.warning("excel parse failed job=%s: %s", job_id, exc)
        try:
            job = db.get(Job, job_id)
            if job is not None:
                job.state = JobState.FAILED.value
                job.error_summary = str(exc)
                job.progress_message = str(exc)
                db.add(job)
                db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("could not mark upload job failed job=%s", job_id)
    except Exception:  # noqa: BLE001
        logger.exception("excel background parse failed job=%s", job_id)
        try:
            job = db.get(Job, job_id)
            if job is not None:
                job.state = JobState.FAILED.value
                job.error_summary = (
                    "Could not parse this Excel file. Try exporting as CSV, or use a smaller date range."
                )
                job.progress_message = job.error_summary
                db.add(job)
                db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("could not mark upload job failed job=%s", job_id)
    finally:
        db.close()


def _build_upload_response(
    db: Session,
    job: Job,
    *,
    csv_path: Path,
    parse_report_out: ExcelParseReportOut | None,
    prior_mapping: dict[str, str] | None = None,
) -> UploadResponse:
    columns = read_header(csv_path)
    pack_match, pack_ratio = detect_pack_match(columns)
    suggestions = suggest_mapping(columns, pack_match=pack_match)

    saved_template = find_saved_template(db, columns)
    if saved_template:
        for s in suggestions:
            if s.column_name in saved_template:
                s.canonical_field = saved_template[s.column_name]
                s.confidence = 1.0
                s.band = "auto"

    if prior_mapping:
        suggestions = overlay_prior_mapping(suggestions, prior_mapping)

    needs_manual = requires_manual_mapping(suggestions)
    # Non-pack files always surface Setup mapping (map-later), even if every column scored.
    if not pack_match:
        needs_manual = True

    return UploadResponse(
        job_id=job.id,
        state=job.state,
        detected_columns=columns,
        mapping_suggestions=suggestions,
        requires_manual_mapping=needs_manual,
        parse_report=parse_report_out,
        looks_like_complete_pack=pack_match,
        pack_match_ratio=pack_ratio,
    )


def _has_excel(files: list[UploadFile]) -> bool:
    for f in files:
        name = (f.filename or "").lower()
        if any(name.endswith(ext) for ext in EXCEL_EXTENSIONS):
            return True
    return False


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    additional_files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(require_verified_user),
    _: None = Depends(enforce_csrf),
) -> UploadResponse:
    all_files = [file] + list(additional_files or [])
    primary = sanitize_filename(file.filename or "upload.csv")
    if not _is_allowed(primary):
        raise HTTPException(400, "Accepted formats: .csv, .csv.gz, .xlsx, .xlsm, .xls.")
    for extra in additional_files or []:
        fn = sanitize_filename(extra.filename or "upload.csv")
        if not _is_allowed(fn):
            raise HTTPException(400, f"Additional file not accepted: {fn}")

    label = primary if len(all_files) == 1 else f"{primary} (+{len(all_files) - 1} more)"
    job = Job(state="uploaded", original_filename=label, user_id=user.id, is_demo=False)
    db.add(job)
    db.commit()
    record_audit(
        db,
        action="job.upload",
        user_id=user.id,
        job_id=job.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail={"filename": label},
    )

    paths = job_paths(settings.job_root_path, job.id)
    limits = settings.limits
    csv_path = paths.raw_dir / "input.csv"
    parse_report_out: ExcelParseReportOut | None = None
    defer_excel = _has_excel(all_files)

    try:
        _, parse_report_out, progress, excel_deferred = await _ingest_uploads(
            all_files, paths=paths, limits=limits, defer_excel=defer_excel
        )
        if progress:
            job.progress_message = progress
    except (UploadTooLargeError, DecompressionBombError) as exc:
        job.state = "failed"
        job.error_summary = str(exc)
        db.add(job)
        db.commit()
        raise HTTPException(413, str(exc)) from exc
    except ExcelConversionError as exc:
        job.state = "failed"
        job.error_summary = str(exc)
        db.add(job)
        db.commit()
        raise HTTPException(400, str(exc)) from exc

    if excel_deferred:
        job.state = JobState.PARSING.value
        job.progress_message = "Parsing Excel workbook… this can take a minute for wide reports."
        db.add(job)
        db.commit()
        threading.Thread(
            target=_finish_excel_parse,
            args=(job.id, settings),
            kwargs={"progress_fallback": "Reviewing detected columns…"},
            daemon=True,
            name=f"excel-parse-{job.id[:8]}",
        ).start()
        return _pending_upload_response(job)

    job.state = "mapping"
    if not job.progress_message:
        job.progress_message = "Reviewing detected columns…"
    db.add(job)
    db.commit()

    return _build_upload_response(db, job, csv_path=csv_path, parse_report_out=parse_report_out)


@router.post("/jobs/{job_id}/replace-upload", response_model=UploadResponse)
async def replace_upload(
    job_id: str,
    request: Request,
    file: UploadFile = File(...),
    additional_files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(require_verified_user),
    _: None = Depends(enforce_csrf),
) -> UploadResponse:
    """Replace SCADA files on an existing job. Keeps plant config; remaps prior columns by name."""
    job = load_job_authorized(db, job_id, user)
    if job.state in _BLOCKED_WHILE_RUNNING:
        raise HTTPException(
            409,
            f"Analysis is still running (state '{job.state}'). Wait for it to finish, then replace files.",
        )
    if job.state not in _REPLACEABLE_STATES:
        raise HTTPException(409, f"Job is in state '{job.state}' and cannot accept a file replace right now.")

    all_files = [file] + list(additional_files or [])
    primary = sanitize_filename(file.filename or "upload.csv")
    if not _is_allowed(primary):
        raise HTTPException(400, "Accepted formats: .csv, .csv.gz, .xlsx, .xlsm, .xls.")
    for extra in additional_files or []:
        fn = sanitize_filename(extra.filename or "upload.csv")
        if not _is_allowed(fn):
            raise HTTPException(400, f"Additional file not accepted: {fn}")

    prior_mapping = dict((job.mapping_json or {}).get("column_to_canonical") or {})
    label = primary if len(all_files) == 1 else f"{primary} (+{len(all_files) - 1} more)"

    _clear_derived_outputs(settings, job.id)
    _clear_raw_dir(settings, job.id)

    paths = job_paths(settings.job_root_path, job.id)
    limits = settings.limits
    csv_path = paths.raw_dir / "input.csv"
    parse_report_out: ExcelParseReportOut | None = None
    defer_excel = _has_excel(all_files)

    try:
        _, parse_report_out, progress, excel_deferred = await _ingest_uploads(
            all_files, paths=paths, limits=limits, defer_excel=defer_excel
        )
        if progress:
            job.progress_message = progress
    except (UploadTooLargeError, DecompressionBombError) as exc:
        job.state = "failed"
        job.error_summary = str(exc)
        db.add(job)
        db.commit()
        raise HTTPException(413, str(exc)) from exc
    except ExcelConversionError as exc:
        job.state = "failed"
        job.error_summary = str(exc)
        db.add(job)
        db.commit()
        raise HTTPException(400, str(exc)) from exc

    job.original_filename = label
    job.error_summary = None
    job.validation_summary_json = None
    job.results_summary_json = None
    job.completed_at = None
    job.report_expires_at = None
    job.total_execution_time_ms = None
    job.downloaded_pdf = False
    job.downloaded_excel = False
    # Drop stale mapping — Setup rebuilds from suggestions + prior overlay by column name.
    job.mapping_json = None

    if excel_deferred:
        job.state = JobState.PARSING.value
        job.progress_message = "Parsing Excel workbook… this can take a minute for wide reports."
        db.add(job)
        db.commit()
        record_audit(
            db,
            action="job.replace_upload",
            user_id=user.id,
            job_id=job.id,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail={"filename": label, "preserved_mapping_cols": len(prior_mapping), "async_excel": True},
        )
        threading.Thread(
            target=_finish_excel_parse,
            args=(job.id, settings),
            kwargs={
                "prior_mapping": prior_mapping or None,
                "progress_fallback": "Files replaced — review column mapping.",
            },
            daemon=True,
            name=f"excel-replace-{job.id[:8]}",
        ).start()
        return _pending_upload_response(job)

    job.state = JobState.MAPPING.value
    if not job.progress_message:
        job.progress_message = "Files replaced — review column mapping."
    db.add(job)
    db.commit()

    record_audit(
        db,
        action="job.replace_upload",
        user_id=user.id,
        job_id=job.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        detail={"filename": label, "preserved_mapping_cols": len(prior_mapping)},
    )

    return _build_upload_response(
        db,
        job,
        csv_path=csv_path,
        parse_report_out=parse_report_out,
        prior_mapping=prior_mapping or None,
    )
