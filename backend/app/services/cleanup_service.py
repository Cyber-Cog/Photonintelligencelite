"""Deterministic cleanup: stale-job reclaim, report TTL expiry, and download-triggered
deletion. See docs/architecture_decisions.md §7 and docs/PRD.md §7.12, §11.

No self-ping/keepalive is used to trigger this (docs/PRD.md §0) — it runs at process
startup and on a periodic in-process timer while the app is awake, which is sufficient
because the UI's own status polling keeps the instance warm during any active job.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from analytics.core.job_states import JobState
from backend.app.config import Settings
from backend.app.database import SessionLocal
from backend.app.models import Job
from backend.app.services.storage import delete_job_dir

logger = logging.getLogger("pic_lite.cleanup")

PERIODIC_INTERVAL_SEC = 300


def reclaim_stale_jobs(settings: Settings) -> int:
    timeout = settings.limits.job_timeout_sec
    cutoff = datetime.now(timezone.utc).timestamp() - timeout
    reclaimed = 0
    with SessionLocal() as db:
        active_states = [s.value for s in JobState if s.is_active]
        rows = db.query(Job).filter(Job.state.in_(active_states)).all()
        for row in rows:
            reference = row.started_at or row.created_at
            if reference and reference.timestamp() < cutoff:
                row.error_summary = "This job exceeded the maximum processing time and was stopped automatically."
                row.state = JobState.FAILED.value
                db.add(row)
                delete_job_dir(settings.job_root_path, row.id)
                row.state = JobState.CLEANED_UP.value
                row.cleaned_up_at = datetime.now(timezone.utc)
                reclaimed += 1
        db.commit()
    if reclaimed:
        logger.info("reclaimed %d stale job(s)", reclaimed)
    return reclaimed


def expire_completed_reports(settings: Settings) -> int:
    now = datetime.now(timezone.utc)
    expired = 0
    with SessionLocal() as db:
        rows = db.query(Job).filter(Job.state == JobState.COMPLETED.value, Job.report_expires_at.isnot(None), Job.report_expires_at < now).all()
        for row in rows:
            delete_job_dir(settings.job_root_path, row.id)
            row.state = JobState.CLEANED_UP.value
            row.cleaned_up_at = now
            db.add(row)
            expired += 1
        db.commit()
    if expired:
        logger.info("expired %d completed job report(s)", expired)
    return expired


def cleanup_after_download(settings: Settings, job_id: str) -> None:
    with SessionLocal() as db:
        row = db.get(Job, job_id)
        if row is None:
            return
        delete_job_dir(settings.job_root_path, job_id)
        row.state = JobState.CLEANED_UP.value
        row.cleaned_up_at = datetime.now(timezone.utc)
        db.add(row)
        db.commit()


def mark_abandoned_jobs(settings: Settings, *, hours: float = 24.0) -> int:
    """Flag incomplete funnels (job created but never finished) for superadmin intel."""
    from datetime import timedelta

    from backend.app.auth.audit import record_audit

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    setup_states = {
        JobState.UPLOADED.value,
        JobState.PARSING.value,
        JobState.MAPPING.value,
        JobState.VALIDATING.value,
        JobState.NORMALIZING.value,
    }
    marked = 0
    with SessionLocal() as db:
        rows = (
            db.query(Job)
            .filter(
                Job.state.in_(list(setup_states)),
                Job.abandoned_at.is_(None),
                Job.is_demo.is_(False),
                Job.created_at < cutoff,
            )
            .limit(200)
            .all()
        )
        for row in rows:
            row.abandoned_at = datetime.now(timezone.utc)
            db.add(row)
            record_audit(
                db,
                action="job.abandoned",
                user_id=row.user_id,
                job_id=row.id,
                detail={"state": row.state},
                commit=False,
            )
            marked += 1
        if marked:
            db.commit()
    if marked:
        logger.info("marked %d abandoned job funnel(s)", marked)
    return marked


async def periodic_cleanup_loop(settings: Settings) -> None:
    while True:
        try:
            reclaim_stale_jobs(settings)
            expire_completed_reports(settings)
            mark_abandoned_jobs(settings)
        except Exception:  # noqa: BLE001
            logger.exception("periodic cleanup pass failed")
        await asyncio.sleep(PERIODIC_INTERVAL_SEC)
