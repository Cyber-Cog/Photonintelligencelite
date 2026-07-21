"""The "Try Demo" flow: reuses tests/fixtures/synthetic_generator.py so the demo is a real
product tour that exercises every algorithm, not a canned screenshot (docs/PRD.md §7.1).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.app.auth.audit import record_audit
from backend.app.auth.deps import get_optional_user
from backend.app.auth.rate_limit import client_ip
from backend.app.config import Settings, get_settings
from backend.app.database import get_db
from backend.app.models import Job, User
from backend.app.schemas import DemoJobResponse
from backend.app.services import validation_service
from backend.app.services.job_service import get_runner
from analytics.common.complete_analysis_pack import OFFICIAL_COLUMN_TO_CANONICAL
from backend.app.services.mapping_service import save_template
from backend.app.services.storage import job_paths

router = APIRouter(prefix="/api", tags=["demo"])

# Same headers as Complete Analysis Pack / demo CSV (single source of truth).
DEMO_MAPPING = dict(OFFICIAL_COLUMN_TO_CANONICAL)

def _demo_architecture() -> dict[str, dict]:
    arch: dict[str, dict] = {}
    for inv in ("INV-01", "INV-02"):
        for scb_idx in range(1, 5):
            scb_id = f"{inv}-SCB-{scb_idx:02d}"
            arch[scb_id] = {"inverter_id": inv, "strings_per_scb": 4, "modules_per_string": 11}
    return arch


# Capacities match the synthetic telemetry scale (2 × 90 kW inverters, ~0.2 MWp DC) so the
# demo dashboard shows realistic KPIs and INV-01 clips naturally at its AC rating.
DEMO_PLANT = {
    "plant_name": "Demo Solar Plant (Synthetic)",
    "ac_capacity_mw": 0.18,
    "dc_capacity_mwp": 0.198,
    "module_rating_wp": 545.0,
    "inverter_capacity_kw": 90.0,
    "module_technology": "Mono PERC",
    "bifacial": False,
    "timezone": "Asia/Kolkata",
    "strings_per_scb": 4,
    "tariff_inr_per_kwh": 3.5,
    "pr_benchmark_pct": 80.0,
    "plant_type": "fixed_tilt",
    "equipment_ratings": {"INV-01": 90.0, "INV-02": 90.0},
    "architecture": _demo_architecture(),
}


def _demo_csv_path() -> Path:
    return Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "demo_plant_scada.csv"


@router.post("/demo", response_model=DemoJobResponse)
def start_demo(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(get_optional_user),
):
    """Public — no authentication required."""
    demo_csv = _demo_csv_path()
    if not demo_csv.exists():
        from tests.fixtures.synthetic_generator import write_demo_files

        write_demo_files(demo_csv, demo_csv.with_name("demo_plant_ground_truth.json"))

    job = Job(
        state="uploaded",
        original_filename="demo_plant_scada.csv",
        plant_name=DEMO_PLANT["plant_name"],
        user_id=user.id if user else None,
        is_demo=True,
    )
    db.add(job)
    db.commit()
    record_audit(
        db,
        action="demo.start",
        user_id=user.id if user else None,
        job_id=job.id,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    paths = job_paths(settings.job_root_path, job.id)
    shutil.copyfile(demo_csv, paths.raw_dir / "input.csv")

    save_template(db, list(DEMO_MAPPING.keys()), DEMO_MAPPING)
    job.mapping_json = {
        "column_to_canonical": {c: f for c, f in DEMO_MAPPING.items() if f != "timestamp"},
        "confidence_by_column": {c: 1.0 for c in DEMO_MAPPING},
        "timestamp_column": "Timestamp",
        "detected_oem_signature": "demo",
    }
    job.plant_config_json = {"plant": DEMO_PLANT, "threshold_overrides": {}}
    db.add(job)
    db.commit()

    validation_service.run_validation_stage(db, job, settings)
    db.refresh(job)

    if job.state == "normalizing":
        job.state = "queued"
        job.progress_message = (
            "Queued — other analyses may be running in parallel; yours starts when a worker is free."
        )
        db.add(job)
        db.commit()
        get_runner(settings).submit(job.id)

    return DemoJobResponse(job_id=job.id, state=job.state)
