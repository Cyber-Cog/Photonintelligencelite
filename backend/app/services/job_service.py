"""In-process multi-job worker pool.

Multiple analyses can run concurrently (default 4). Each job uses its own
``JOB_ROOT/{job_id}/`` directory, so disk work is isolated. Concurrency is capped
via ``MAX_CONCURRENT_JOBS`` to protect RAM on small hosts.

There is no global Postgres advisory lock / single-job mutex.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from analytics.core.job_states import JobState
from backend.app.config import Settings
from backend.app.database import SessionLocal
from backend.app.models import Job
from backend.app.services import pipeline
from backend.app.services.storage import JobPaths, delete_job_dir, job_paths

logger = logging.getLogger("pic_lite.job_service")

# Legacy single-job copy (pre worker-pool). Rewrite if found on queued jobs.
_STALE_SINGLE_JOB_MESSAGES = (
    "Another job is currently running. Waiting for it to finish.",
    "Another job is currently running",
)

_QUEUED_PROGRESS = (
    "Queued — other analyses may be running in parallel; yours starts when a worker is free."
)


def _set_state(db: Session, job: Job, state: JobState, message: str | None = None) -> None:
    job.state = state.value
    if message:
        job.progress_message = message
    db.add(job)
    db.commit()


def _is_stale_single_job_message(message: str | None) -> bool:
    if not message:
        return False
    return any(message.startswith(prefix) for prefix in _STALE_SINGLE_JOB_MESSAGES)


class JobRunner:
    """In-process worker pool. Up to ``max_concurrent_jobs`` analyses run at once."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._queued_ids: list[str] = []
        self._running_ids: set[str] = set()
        self._worker_tasks: list[asyncio.Task] = []
        self._recent_durations_sec: list[float] = []
        self._max_workers = max(1, int(settings.max_concurrent_jobs or 4))
        self._started = False

    @property
    def max_workers(self) -> int:
        return self._max_workers

    @property
    def running_count(self) -> int:
        return len(self._running_ids)

    @property
    def queued_count(self) -> int:
        return len(self._queued_ids)

    @property
    def pool_started(self) -> bool:
        return self._started and any(not t.done() for t in self._worker_tasks)

    async def start(self) -> None:
        if self._started and self._worker_tasks:
            # Ensure workers are still alive after a partial reload.
            alive = [t for t in self._worker_tasks if not t.done()]
            if len(alive) >= self._max_workers:
                return
            for t in self._worker_tasks:
                t.cancel()
            self._worker_tasks.clear()

        self._recover_queued_jobs()
        self._worker_tasks = [
            asyncio.create_task(self._worker_loop(worker_id=i)) for i in range(self._max_workers)
        ]
        self._started = True
        logger.info("job worker pool started workers=%s", self._max_workers)

    async def stop(self) -> None:
        for task in self._worker_tasks:
            task.cancel()
        self._worker_tasks.clear()
        self._started = False

    def _recover_queued_jobs(self) -> None:
        with SessionLocal() as db:
            # Re-queue jobs left QUEUED or interrupted mid-run (process restart).
            rows = (
                db.query(Job)
                .filter(
                    Job.state.in_(
                        [
                            JobState.QUEUED.value,
                            JobState.RUNNING.value,
                            JobState.GENERATING_CHARTS.value,
                            JobState.GENERATING_REPORT.value,
                        ]
                    )
                )
                .order_by(Job.created_at)
                .all()
            )
            for row in rows:
                if row.state != JobState.QUEUED.value:
                    row.state = JobState.QUEUED.value
                    row.progress_message = "Re-queued after server restart…"
                    db.add(row)
                elif _is_stale_single_job_message(row.progress_message):
                    row.progress_message = _QUEUED_PROGRESS
                    db.add(row)
                if row.id not in self._queued_ids and row.id not in self._running_ids:
                    self._queued_ids.append(row.id)
                    self._queue.put_nowait(row.id)
            db.commit()

    def submit(self, job_id: str) -> None:
        if job_id not in self._queued_ids and job_id not in self._running_ids:
            self._queued_ids.append(job_id)
            self._queue.put_nowait(job_id)

    def ensure_queued(self, job_id: str, *, progress_message: str | None = None) -> str | None:
        """Re-enqueue a DB-queued job missing from the in-memory pool (self-heal).

        Returns an updated progress_message when the stale single-job copy is rewritten.
        """
        updated_msg: str | None = None
        if _is_stale_single_job_message(progress_message):
            updated_msg = _QUEUED_PROGRESS
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                if job and job.state == JobState.QUEUED.value:
                    job.progress_message = _QUEUED_PROGRESS
                    db.add(job)
                    db.commit()
        self.submit(job_id)
        return updated_msg

    def queue_position(self, job_id: str) -> int | None:
        if job_id in self._running_ids:
            return 0
        try:
            return self._queued_ids.index(job_id) + 1
        except ValueError:
            return None

    def estimated_wait_seconds(self, job_id: str) -> float | None:
        pos = self.queue_position(job_id)
        if pos is None:
            return None
        if pos == 0:
            return 0.0
        avg = (
            sum(self._recent_durations_sec) / len(self._recent_durations_sec)
            if self._recent_durations_sec
            else self.settings.limits.job_timeout_sec / 3.0
        )
        slots = max(1, self._max_workers)
        ahead = max(0, pos - 1)
        return round((ahead / slots) * avg, 1)

    async def _worker_loop(self, worker_id: int) -> None:
        while True:
            job_id = await self._queue.get()
            if job_id in self._queued_ids:
                self._queued_ids.remove(job_id)
            if job_id in self._running_ids:
                self._queue.task_done()
                continue
            self._running_ids.add(job_id)
            start = time.perf_counter()
            try:
                logger.info("worker=%s starting job=%s", worker_id, job_id)
                # Thread offload so multiple CPU-heavy jobs run in parallel (GIL released in numpy/pandas/IO).
                await asyncio.to_thread(process_job, job_id, self.settings)
            except Exception:  # noqa: BLE001
                logger.exception("job=%s failed with an unhandled exception", job_id)
                _mark_failed(job_id, "An unexpected error stopped this job. Please try again.")
            finally:
                self._recent_durations_sec.append(time.perf_counter() - start)
                self._recent_durations_sec = self._recent_durations_sec[-20:]
                self._running_ids.discard(job_id)
                self._queue.task_done()


_RUNNER: JobRunner | None = None


def get_runner(settings: Settings) -> JobRunner:
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = JobRunner(settings)
    return _RUNNER


def reset_runner_for_tests() -> None:
    """Test helper — drop the process-global runner between cases."""
    global _RUNNER
    _RUNNER = None


def _mark_failed(job_id: str, reason: str) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job:
            job.error_summary = reason
            _set_state(db, job, JobState.FAILED, reason)
            try:
                from backend.app.auth.audit import record_audit

                record_audit(
                    db,
                    action="analysis.fail",
                    user_id=job.user_id,
                    job_id=job_id,
                    detail={"reason": reason[:200]},
                )
            except Exception:  # noqa: BLE001
                logger.exception("audit fail for job=%s", job_id)


def process_job(job_id: str, settings: Settings) -> None:
    """Runs synchronously inside a worker thread (called via asyncio.to_thread)."""
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return

        try:
            job.started_at = datetime.now(timezone.utc)
            _set_state(db, job, JobState.RUNNING, "Running analysis algorithms…")

            paths = job_paths(settings.job_root_path, job_id)
            plant_cfg = job.plant_config_json
            mapping_cfg = job.mapping_json
            if not plant_cfg or not mapping_cfg:
                raise RuntimeError("Missing plant configuration or mapping before analysis could start.")

            from analytics.core.context import PlantConfig, ResolvedMapping

            plant = PlantConfig(**{k: v for k, v in plant_cfg["plant"].items() if k in PlantConfig.__dataclass_fields__})
            mapping_cfg = mapping_cfg or {}
            mapping = ResolvedMapping(
                column_to_canonical=mapping_cfg.get("column_to_canonical", {}),
                confidence_by_column=mapping_cfg.get("confidence_by_column", {}),
                detected_oem_signature=mapping_cfg.get("detected_oem_signature"),
            )

            interval_result = _load_interval_result(paths)
            context = pipeline.build_context(
                pipeline.PipelineInputs(
                    csv_path=paths.raw_dir / "input.csv",
                    job_paths=paths,
                    job_id=job_id,
                    mapping=mapping,
                    timestamp_column=mapping_cfg.get("timestamp_column", "timestamp"),
                    plant=plant,
                    threshold_overrides=plant_cfg.get("threshold_overrides", {}),
                ),
                interval_result,
            )
            run = pipeline.run_orchestrator(context)

            _set_state(db, job, JobState.GENERATING_CHARTS, "Building dashboard charts…")
            results_payload = {
                "kpis": run.kpis,
                "results": [r.model_dump(mode="json") for r in run.results],
            }
            (paths.results_dir / "results.json").write_text(json.dumps(results_payload, indent=2), encoding="utf-8")

            _set_state(db, job, JobState.GENERATING_REPORT, "Generating PDF and Excel reports…")
            _generate_reports(paths, job, plant, run, interval_result)

            job.results_summary_json = {
                "kpis": run.kpis,
                "modules": [
                    {"id": r.algorithm_id, "status": r.status.value, "loss_kwh": r.loss_energy_kwh} for r in run.results
                ],
            }
            job.total_execution_time_ms = run.total_execution_time_ms
            job.completed_at = datetime.now(timezone.utc)
            job.report_expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.limits.report_ttl_minutes)
            _set_state(db, job, JobState.COMPLETED, "Analysis complete.")
            try:
                from backend.app.auth.audit import record_audit

                record_audit(
                    db,
                    action="analysis.complete",
                    user_id=job.user_id,
                    job_id=job_id,
                    detail={"is_demo": bool(job.is_demo)},
                )
            except Exception:  # noqa: BLE001
                logger.exception("audit complete for job=%s", job_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("job=%s processing failed", job_id)
            job = db.get(Job, job_id)
            if job:
                job.error_summary = str(exc)[:500]
                _set_state(db, job, JobState.FAILED, "This job could not be completed. See error details.")
                try:
                    from backend.app.auth.audit import record_audit

                    record_audit(
                        db,
                        action="analysis.fail",
                        user_id=job.user_id,
                        job_id=job_id,
                        detail={"error": str(exc)[:200]},
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("audit fail for job=%s", job_id)
    finally:
        db.close()


def _load_interval_result(paths: JobPaths):
    from analytics.preprocessing.interval_normalize import IntervalNormalizationResult

    meta_path = paths.canonical_dir / "_interval_meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return IntervalNormalizationResult(
            detected_interval_minutes=meta.get("detected_interval_minutes"),
            resampled=bool(meta.get("resampled")),
            is_irregular=bool(meta.get("is_irregular")),
            per_device_intervals_minutes=meta.get("per_device_intervals_minutes") or {},
            notes=meta.get("notes") or [],
        )
    return IntervalNormalizationResult(
        detected_interval_minutes=None,
        resampled=False,
        is_irregular=False,
        per_device_intervals_minutes={},
        notes=[],
    )


def _validation_from_summary(summary: dict | None):
    """Rebuild a ValidationReport from the JSON stored on the job row."""
    from analytics.preprocessing.validation import ValidationIssue, ValidationReport

    summary = summary or {}
    issues: list[ValidationIssue] = []
    for bucket in ("blockers", "warnings"):
        for raw in summary.get(bucket) or []:
            issues.append(
                ValidationIssue(
                    code=raw.get("code", "unknown"),
                    severity=raw.get("severity", "warning"),
                    message=raw.get("message", ""),
                    likely_cause=raw.get("likely_cause", ""),
                    blocks_analysis=bool(raw.get("blocks_analysis", bucket == "blockers")),
                    affected_rows=int(raw.get("affected_rows") or 0),
                    affected_columns=list(raw.get("affected_columns") or []),
                    sample_values=list(raw.get("sample_values") or []),
                    remediation=raw.get("remediation") or "",
                )
            )
    return ValidationReport(
        issues=issues,
        row_count=int(summary.get("row_count") or 0),
        column_count=int(summary.get("column_count") or 0),
        timestamp_column=summary.get("timestamp_column"),
        timestamp_parse_ok=int(summary.get("timestamp_parse_ok") or 0),
        timestamp_parse_fail=int(summary.get("timestamp_parse_fail") or 0),
    )


def _generate_reports(paths: JobPaths, job: Job, plant, run, interval_result) -> None:
    from analytics.reports.excel_builder import build_excel_report
    from analytics.reports.pdf_builder import build_pdf_report
    from analytics.reports.report_data import ReportContext

    mapping_cfg = job.mapping_json or {}
    ctx = ReportContext(
        job_id=job.id,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        plant=plant,
        run=run,
        validation=_validation_from_summary(job.validation_summary_json),
        interval_result=interval_result,
        mapping_confidence_by_column=mapping_cfg.get("confidence_by_column") or {},
    )
    paths.reports_dir.mkdir(parents=True, exist_ok=True)
    (paths.reports_dir / "report.pdf").write_bytes(build_pdf_report(ctx))
    (paths.reports_dir / "report.xlsx").write_bytes(build_excel_report(ctx))


def cleanup_expired_jobs(settings: Settings) -> int:
    """Delete expired job directories (report TTL). Returns count removed."""
    now = datetime.now(timezone.utc)
    removed = 0
    with SessionLocal() as db:
        rows = (
            db.query(Job)
            .filter(Job.report_expires_at.isnot(None), Job.report_expires_at < now)
            .filter(Job.state.in_([JobState.COMPLETED.value, JobState.FAILED.value, JobState.CLEANED_UP.value]))
            .all()
        )
        for job in rows:
            delete_job_dir(settings.job_root_path, job.id)
            job.state = JobState.CLEANED_UP.value
            db.add(job)
            removed += 1
        db.commit()
    return removed
