"""FastAPI application entrypoint.

Startup sequence: init Postgres schema, seed superadmin, reclaim any stale jobs left over
from a previous process (crash/restart/free-tier sleep), start the in-process job worker
pool (MAX_CONCURRENT_JOBS), and start the periodic cleanup loop. See docs/architecture_decisions.md §7-8.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.auth.seed import seed_superadmin
from backend.app.config import get_settings
from backend.app.database import SessionLocal, init_db
from backend.app.routers import admin, auth, demo, explorer, intake, jobs, reports, results, templates, upload
from backend.app.services.cleanup_service import periodic_cleanup_loop, reclaim_stale_jobs
from backend.app.services.job_service import get_runner

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
logger = logging.getLogger("pic_lite.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db()
    with SessionLocal() as db:
        seed_superadmin(db, settings)
    reclaim_stale_jobs(settings)

    runner = get_runner(settings)
    await runner.start()
    cleanup_task = asyncio.create_task(periodic_cleanup_loop(settings))

    logger.info(
        "Photon Intelligence Center Lite API ready. free_tier=%s job_timeout_sec=%s max_concurrent_jobs=%s",
        settings.free_tier,
        settings.limits.job_timeout_sec,
        settings.max_concurrent_jobs,
    )
    yield

    cleanup_task.cancel()
    await runner.stop()


app = FastAPI(
    title="Photon Intelligence Center Lite API",
    version="0.2.0",
    lifespan=lifespan,
    description=(
        "Auth uses httpOnly session cookies + CSRF. "
        "When SMTP is not configured, signup returns `verification_link` for local DEV. "
        "See docs/AUTH.md."
    ),
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(upload.router)
app.include_router(explorer.router)
app.include_router(intake.router)
app.include_router(templates.router)
app.include_router(jobs.router)
app.include_router(results.router)
app.include_router(reports.router)
app.include_router(demo.router)


@app.get("/api/health")
def health():
    runner = get_runner(settings)
    return {
        "status": "ok",
        "free_tier": settings.free_tier,
        "max_concurrent_jobs": settings.max_concurrent_jobs,
        "workers": runner.max_workers,
        "running_jobs": runner.running_count,
        "queued_jobs": runner.queued_count,
        "worker_pool_started": runner.pool_started,
    }
