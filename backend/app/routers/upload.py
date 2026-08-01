"""Upload endpoint: streamed save, Excel→CSV conversion, bounded gzip decompression,
header inspection, and confidence-scored mapping suggestions. See docs/PRD.md §7.2, §7.4.

Excel conversion runs off the request thread (like demo prep) so Vercel→Render proxies
do not 502 when a wide workbook takes longer than the edge timeout (~30s).
"""
from __future__ import annotations

import json
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
from backend.app.schemas import (
    AiIntegrityCheck,
    ExcelParseReportOut,
    UploadArchitectureSummary,
    UploadFileInventoryItem,
    UploadHierarchyLevel,
    UploadModuleImpactPreview,
    UploadResponse,
    UploadSignalCheckItem,
)
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
from backend.app.services.pack_architecture_import import (
    merge_architecture_into_job_plant,
    plant_config_from_architecture_file,
)
from backend.app.services.ai_parse_assist import run_parse_assist
from backend.app.services.upload_ai_check import run_upload_integrity_check
from backend.app.services.upload_intelligence import build_upload_intelligence
from backend.app.services.upload_inventory import (
    build_inventory_from_parts,
    inventory_from_job,
    read_upload_manifest,
    signal_checklist,
    write_upload_manifest,
)
from backend.app.services.wide_csv_reshape import maybe_reshape_wide_csv
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
}

_REPLACEABLE_STATES = {
    JobState.UPLOADED.value,
    JobState.PARSING.value,
    JobState.MAPPING.value,
    JobState.VALIDATING.value,
    JobState.NORMALIZING.value,
    JobState.FAILED.value,
    JobState.COMPLETED.value,
    JobState.CLEANED_UP.value,
}


def _replace_upload_blocked_message(state: str) -> str:
    if state in _BLOCKED_WHILE_RUNNING:
        return "Analysis is running. Wait for it to finish, then replace files."
    return f"Job is in state '{state}' and cannot accept a file replace right now."


def _load_parse_report(raw_dir: Path, idx: int) -> dict | None:
    for name in (f"parse_report_{idx}.json", "parse_report.json"):
        p = raw_dir / name
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
    return None


def _persist_file_inventory(
    paths,
    parts: list[tuple[str, Path, dict | None]],
    *,
    row_count: int,
    source_names: list[str],
    merge_strategy: str = "timestamp_join",
) -> list[dict]:
    files = build_inventory_from_parts(parts)
    write_upload_manifest(
        paths.raw_dir / "sources_manifest.json",
        files=files,
        row_count=row_count,
        merge_strategy=merge_strategy,
        source_names=source_names,
    )
    return files


def _inventory_parts_from_converted(
    converted_paths: list[Path],
    source_names: list[str],
    raw_dir: Path,
) -> list[tuple[str, Path, dict | None]]:
    parts: list[tuple[str, Path, dict | None]] = []
    for i, path in enumerate(converted_paths):
        if not path.exists():
            continue
        label = source_names[i] if i < len(source_names) else path.name
        parts.append((label, path, _load_parse_report(raw_dir, i)))
    return parts


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
) -> tuple[list[Path], ExcelParseReportOut | None, str | None, bool, dict | None]:
    """Save/convert uploads into raw_dir.

    Returns (converted_paths, parse_report, progress, excel_deferred, architecture_draft).
    When defer_excel=True, Excel files are saved raw and conversion is skipped;
    architecture is extracted later in the background worker.
    """
    parse_report_out: ExcelParseReportOut | None = None
    converted_paths: list[Path] = []
    progress: str | None = None
    excel_deferred = False
    architecture_draft: dict | None = None

    async def _ingest_one(upload: UploadFile, idx: int) -> Path:
        nonlocal parse_report_out, excel_deferred, architecture_draft
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
            if architecture_draft is None:
                architecture_draft = plant_config_from_architecture_file(excel_target)
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

    source_names = [
        sanitize_filename(uf.filename or f"upload_{i}.csv") for i, uf in enumerate(all_files)
    ]

    if excel_deferred:
        return converted_paths, None, "Saving Excel — parsing will continue in the background…", True, None

    csv_path = paths.raw_dir / "input.csv"
    manifest_path = paths.raw_dir / "sources_manifest.json"
    inventory_parts = _inventory_parts_from_converted(converted_paths, source_names, paths.raw_dir)
    if len(converted_paths) > 1:
        file_inventory = build_inventory_from_parts(inventory_parts)
        row_count, names = merge_csv_files(
            converted_paths,
            csv_path,
            manifest_path,
            source_labels=source_names,
            file_inventory=file_inventory,
        )
        for p in converted_paths:
            if p != csv_path:
                p.unlink(missing_ok=True)
        progress = f"Merged {len(names)} report(s) — {row_count:,} rows."
    else:
        row_count = 0
        if converted_paths and converted_paths[0].exists():
            import pandas as pd

            row_count = max(0, len(pd.read_csv(converted_paths[0], usecols=[0])))
            if parse_report_out and parse_report_out.row_count:
                row_count = parse_report_out.row_count
            _persist_file_inventory(
                paths,
                inventory_parts,
                row_count=row_count,
                source_names=source_names,
                merge_strategy="single_file",
            )
        if parse_report_out:
            inv_n = len(parse_report_out.inverters_found)
            progress = (
                f"Parsed {parse_report_out.layout} ({parse_report_out.strategy}): "
                f"{parse_report_out.row_count:,} rows, {inv_n} inverter(s), "
                f"confidence {parse_report_out.confidence:.0%}."
            )

    # Wide historian CSVs (plant/ICR/INV×metric columns) → tidy long form before mapping.
    if csv_path.exists():
        reshape = maybe_reshape_wide_csv(csv_path, max_rows=limits.max_rows)
        if reshape.reshaped:
            report_path = paths.raw_dir / "wide_reshape_report.json"
            report_path.write_text(json.dumps(reshape.to_dict(), indent=2), encoding="utf-8")
            progress = (
                f"Reshaped wide SCADA ({reshape.strategy}): {reshape.row_count:,} rows, "
                f"{len(reshape.inverters_found)} inverter(s)"
                + (f", {len(reshape.icr_ids)} ICR(s)" if reshape.icr_ids else "")
                + "."
            )
            if parse_report_out is None:
                parse_report_out = ExcelParseReportOut(
                    layout="wide_single_header",
                    strategy=reshape.strategy,
                    sheet_name="csv",
                    confidence=reshape.confidence,
                    header_rows=[0],
                    timestamp_column="Timestamp",
                    inverters_found=reshape.inverters_found,
                    columns_mapped=reshape.columns_mapped,
                    row_count=reshape.row_count,
                    warnings=reshape.warnings,
                )

    return converted_paths, parse_report_out, progress, False, architecture_draft


def _progress_commit(db: Session, job_id: str, message: str) -> None:
    job = db.get(Job, job_id)
    if job is None:
        return
    job.progress_message = message
    db.add(job)
    db.commit()


def _convert_deferred_excels(
    paths,
    limits,
    *,
    job_id: str | None = None,
    db: Session | None = None,
) -> tuple[ExcelParseReportOut | None, str | None, dict | None]:
    """Convert any raw upload_*.xlsx left on disk, then merge into input.csv.

    Parses each workbook independently so one bad file does not silently kill
    the batch with a vague error — failures name the file and successful parts
    still merge when at least one CSV was produced.

    Also extracts Complete Analysis Pack ``architecture`` sheets into a plant draft.
    """
    excel_files = sorted(
        p
        for p in paths.raw_dir.iterdir()
        if p.is_file() and p.suffix.lower() in EXCEL_EXTENSIONS and p.name.startswith("upload_")
    )
    if not excel_files:
        return None, None, None

    parse_report_out: ExcelParseReportOut | None = None
    converted: list[Path] = []
    source_labels: list[str] = []
    failures: list[str] = []
    architecture_draft: dict | None = None
    # Also keep any CSV parts already written (mixed excel+csv uploads).
    existing_csvs = sorted(
        p for p in paths.raw_dir.iterdir() if p.is_file() and p.suffix.lower() == ".csv" and p.name.startswith("part_")
    )
    converted.extend(existing_csvs)

    multi = len(excel_files) + len(existing_csvs) > 1
    total = len(excel_files)
    for i, excel_target in enumerate(excel_files):
        # upload_0.xlsx → part_0.csv or input.csv
        stem = excel_target.stem  # upload_0
        idx_s = stem.split("_", 1)[-1]
        out_csv = paths.raw_dir / (f"part_{idx_s}.csv" if multi else "input.csv")
        report_path = paths.raw_dir / f"parse_report_{idx_s}.json"
        label = excel_target.name
        source_labels.append(sanitize_filename(label))
        if job_id and db is not None:
            _progress_commit(
                db,
                job_id,
                f"Parsing Excel {i + 1}/{total}: {label}…",
            )
        try:
            if architecture_draft is None:
                architecture_draft = plant_config_from_architecture_file(excel_target)
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
        except (UploadTooLargeError, DecompressionBombError) as exc:
            failures.append(f"{label}: {exc}")
            out_csv.unlink(missing_ok=True)
            logger.warning("excel size limit file=%s: %s", label, exc)
        except ExcelConversionError as exc:
            failures.append(f"{label}: {exc}")
            out_csv.unlink(missing_ok=True)
            logger.warning("excel parse failed file=%s: %s", label, exc)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{label}: {type(exc).__name__}: {exc}")
            out_csv.unlink(missing_ok=True)
            logger.exception("excel parse unexpected file=%s", label)

    if not converted:
        detail = "; ".join(failures) if failures else "no readable workbooks"
        raise ExcelConversionError(
            f"Could not parse any of the {total} Excel file(s). {detail}"
        )

    csv_path = paths.raw_dir / "input.csv"
    manifest_path = paths.raw_dir / "sources_manifest.json"
    progress: str | None = None
    unique = list(dict.fromkeys(converted))
    inventory_parts = _inventory_parts_from_converted(unique, source_labels, paths.raw_dir)
    if len(unique) > 1:
        if job_id and db is not None:
            _progress_commit(db, job_id, f"Merging {len(unique)} parsed report(s)…")
        try:
            file_inventory = build_inventory_from_parts(inventory_parts)
            row_count, names = merge_csv_files(
                unique,
                csv_path,
                manifest_path,
                source_labels=source_labels,
                file_inventory=file_inventory,
            )
        except Exception as exc:  # noqa: BLE001
            raise ExcelConversionError(
                f"Parsed {len(unique)} file(s) but could not merge them: {exc}"
            ) from exc
        for p in unique:
            if p != csv_path:
                p.unlink(missing_ok=True)
        progress = f"Merged {len(names)} report(s) — {row_count:,} rows."
        if failures:
            progress += f" Skipped {len(failures)} file(s)."
            logger.warning("partial excel batch job failures: %s", failures)
    elif parse_report_out:
        # Single successful part may still be named part_N.csv
        if unique and unique[0] != csv_path:
            unique[0].replace(csv_path)
        row_count = parse_report_out.row_count or 0
        if inventory_parts:
            _persist_file_inventory(
                paths,
                inventory_parts,
                row_count=row_count,
                source_names=source_labels or [unique[0].name if unique else "upload.csv"],
                merge_strategy="single_file",
            )
        inv_n = len(parse_report_out.inverters_found)
        progress = (
            f"Parsed {parse_report_out.layout} ({parse_report_out.strategy}): "
            f"{parse_report_out.row_count:,} rows, {inv_n} inverter(s), "
            f"confidence {parse_report_out.confidence:.0%}."
        )
        if failures:
            progress += f" Skipped {len(failures)} file(s)."
    if failures and unique:
        # Surface partial success in progress; do not fail the job.
        warn_path = paths.raw_dir / "parse_failures.json"
        warn_path.write_text(json.dumps({"failures": failures}, indent=2), encoding="utf-8")
    if architecture_draft:
        n_scb = len(architecture_draft.get("architecture") or {})
        arch_note = f" Architecture imported ({n_scb} SCB(s))."
        progress = (progress or "Excel parsed.") + arch_note

    if csv_path.exists():
        reshape = maybe_reshape_wide_csv(csv_path, max_rows=limits.max_rows)
        if reshape.reshaped:
            (paths.raw_dir / "wide_reshape_report.json").write_text(
                json.dumps(reshape.to_dict(), indent=2), encoding="utf-8"
            )
            progress = (
                f"Reshaped wide SCADA ({reshape.strategy}): {reshape.row_count:,} rows, "
                f"{len(reshape.inverters_found)} inverter(s)."
            )
            if parse_report_out is None:
                parse_report_out = ExcelParseReportOut(
                    layout="wide_single_header",
                    strategy=reshape.strategy,
                    sheet_name="csv",
                    confidence=reshape.confidence,
                    header_rows=[0],
                    timestamp_column="Timestamp",
                    inverters_found=reshape.inverters_found,
                    columns_mapped=reshape.columns_mapped,
                    row_count=reshape.row_count,
                    warnings=reshape.warnings,
                )

    return parse_report_out, progress, architecture_draft


def _apply_architecture_draft(job: Job, draft: dict | None, *, overwrite_architecture: bool) -> None:
    """Persist pack-imported architecture onto the job when present."""
    if not draft:
        return
    job.plant_config_json = merge_architecture_into_job_plant(
        job.plant_config_json,
        draft,
        overwrite_architecture=overwrite_architecture,
    )


def _mark_job_failed(db: Session, job_id: str, message: str) -> None:
    job = db.get(Job, job_id)
    if job is None:
        return
    job.state = JobState.FAILED.value
    job.error_summary = message
    job.progress_message = message
    db.add(job)
    db.commit()


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

        parse_report_out, progress, architecture_draft = _convert_deferred_excels(
            paths, limits, job_id=job_id, db=db
        )
        csv_path = paths.raw_dir / "input.csv"
        if not csv_path.exists():
            raise ExcelConversionError("Excel conversion finished but no CSV was produced.")

        # Fresh upload: always import. Replace-upload keeps existing plant unless no architecture yet.
        overwrite = prior_mapping is None or not (
            (job.plant_config_json or {}).get("plant") or {}
        ).get("architecture")
        _apply_architecture_draft(job, architecture_draft, overwrite_architecture=overwrite)

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
            _mark_job_failed(db, job_id, str(exc))
        except Exception:  # noqa: BLE001
            logger.exception("could not mark upload job failed job=%s", job_id)
    except ExcelConversionError as exc:
        logger.warning("excel parse failed job=%s: %s", job_id, exc)
        try:
            _mark_job_failed(db, job_id, str(exc))
        except Exception:  # noqa: BLE001
            logger.exception("could not mark upload job failed job=%s", job_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("excel background parse failed job=%s", job_id)
        try:
            # Prefer actionable detail over a generic CSV tip — only when truly unrecoverable.
            detail = f"{type(exc).__name__}: {exc}".strip()
            if len(detail) > 400:
                detail = detail[:397] + "…"
            _mark_job_failed(
                db,
                job_id,
                f"Excel processing failed unexpectedly ({detail}). "
                "Re-upload the files, or export as CSV if the workbook is corrupted.",
            )
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

    settings = get_settings()
    # After heuristics / templates: Gemini may propose mappings for thin/ambiguous headers.
    suggestions, parse_assist_meta = run_parse_assist(
        settings,
        suggestions=suggestions,
        columns=columns,
        original_filename=job.original_filename,
    )

    needs_manual = requires_manual_mapping(suggestions)
    # Non-pack files always surface Setup mapping (map-later), even if every column scored.
    if not pack_match:
        needs_manual = True

    paths = job_paths(settings.job_root_path, job.id)
    file_inv, total_rows = inventory_from_job(paths, job.original_filename)
    if not total_rows and csv_path.exists():
        try:
            import pandas as pd

            total_rows = max(0, len(pd.read_csv(csv_path, usecols=[0])))
        except Exception:  # noqa: BLE001
            total_rows = 0

    plant = (job.plant_config_json or {}).get("plant") if job.plant_config_json else None
    checklist = signal_checklist(suggestions, plant_config=plant or {})

    reshape_report = None
    reshape_path = paths.raw_dir / "wide_reshape_report.json"
    if reshape_path.exists():
        try:
            reshape_report = json.loads(reshape_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            reshape_report = None

    # Prefer live inventory from post-reshape input.csv when manifest was snapshotted pre-melt.
    if reshape_report and reshape_report.get("reshaped") and csv_path.exists():
        try:
            from backend.app.services.upload_inventory import inventory_item_from_csv

            live = inventory_item_from_csv(
                csv_path, display_name=job.original_filename or csv_path.name
            )
            if file_inv:
                live["filename"] = file_inv[0].get("filename") or live["filename"]
            file_inv = [live]
            if reshape_report.get("row_count"):
                total_rows = int(reshape_report["row_count"]) or total_rows
        except Exception:  # noqa: BLE001
            logger.exception("post-reshape inventory refresh failed job=%s", job.id)

    intelligence = build_upload_intelligence(
        suggestions=suggestions,
        plant_config=plant,
        csv_path=csv_path,
        file_inventory=file_inv,
        reshape_report=reshape_report,
        column_names=columns,
    )
    file_inv = intelligence["file_inventory"]

    assist_hints = [
        {
            "column_name": p["column_name"],
            "canonical_field": p["canonical_field"],
            "confidence": p.get("confidence"),
        }
        for p in (parse_assist_meta.get("proposals") or [])
        if p.get("column_name") and p.get("canonical_field")
    ]
    upload_check = run_upload_integrity_check(
        settings,
        columns=columns,
        suggestions=suggestions,
        hierarchy=intelligence["hierarchy_overview"],
        architecture_summary=intelligence["architecture_summary"],
        original_filename=job.original_filename,
        parse_report=parse_report_out.model_dump() if parse_report_out else None,
        reshape_report=reshape_report,
        use_ai=True,
        extra_mapping_hints=assist_hints,
        parse_assist_meta={
            k: parse_assist_meta.get(k)
            for k in ("attempted", "applied", "model", "error", "provider", "status")
        },
    )
    job.upload_integrity_json = upload_check
    db.add(job)
    db.commit()

    return UploadResponse(
        job_id=job.id,
        state=job.state,
        detected_columns=columns,
        mapping_suggestions=suggestions,
        requires_manual_mapping=needs_manual,
        parse_report=parse_report_out,
        looks_like_complete_pack=pack_match,
        pack_match_ratio=pack_ratio,
        file_inventory=[UploadFileInventoryItem(**f) for f in file_inv],
        total_rows=total_rows,
        signal_checklist=[UploadSignalCheckItem(**c) for c in checklist],
        hierarchy_overview=[UploadHierarchyLevel(**h) for h in intelligence["hierarchy_overview"]],
        architecture_summary=UploadArchitectureSummary(**intelligence["architecture_summary"]),
        module_impact_preview=UploadModuleImpactPreview(**intelligence["module_impact_preview"]),
        original_filename=job.original_filename,
        upload_integrity=AiIntegrityCheck(**upload_check),
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
        _, parse_report_out, progress, excel_deferred, architecture_draft = await _ingest_uploads(
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

    _apply_architecture_draft(job, architecture_draft, overwrite_architecture=True)
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
        raise HTTPException(409, _replace_upload_blocked_message(job.state))
    if job.state not in _REPLACEABLE_STATES:
        raise HTTPException(409, _replace_upload_blocked_message(job.state))

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
        _, parse_report_out, progress, excel_deferred, architecture_draft = await _ingest_uploads(
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
    job.ai_integrity_json = None
    job.upload_integrity_json = None
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

    # Keep existing architecture on replace unless pack provides one and job had none.
    has_arch = bool(((job.plant_config_json or {}).get("plant") or {}).get("architecture"))
    _apply_architecture_draft(job, architecture_draft, overwrite_architecture=not has_arch)

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
