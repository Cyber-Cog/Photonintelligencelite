"""Shared pytest fixtures. Builds one AnalysisContext from the synthetic dataset
(tests/fixtures/synthetic_generator.py) that every algorithm test asserts against, so
fault-injection tolerances are checked against a known, deterministic ground truth.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.common.complete_analysis_pack import OFFICIAL_COLUMN_TO_CANONICAL, SCADA_COLUMNS  # noqa: E402
from analytics.core.context import AnalysisContext, CanonicalDataAccess, JobMeta, PlantConfig, ResolvedMapping  # noqa: E402
from analytics.preprocessing.interval_normalize import normalize_interval  # noqa: E402
from analytics.preprocessing.standardize import standardize  # noqa: E402
from analytics.preprocessing.timezone_normalize import normalize_timezone  # noqa: E402
from tests.fixtures.synthetic_generator import GroundTruth, generate  # noqa: E402

# Exclude timestamp — standardize receives it via timestamp_column, not column_to_canonical.
DEMO_COLUMN_MAPPING = {
    col: field
    for col, field in OFFICIAL_COLUMN_TO_CANONICAL.items()
    if field != "timestamp"
}
assert list(DEMO_COLUMN_MAPPING.keys()) == [c for c in SCADA_COLUMNS if c != "Timestamp"]


def _build_architecture() -> dict[str, dict]:
    arch: dict[str, dict] = {}
    for inv in ("INV-01", "INV-02"):
        for scb_idx in range(1, 5):
            scb_id = f"{inv}-SCB-{scb_idx:02d}"
            arch[scb_id] = {"inverter_id": inv, "strings_per_scb": 4, "modules_per_string": 11}
    return arch


@pytest.fixture(scope="session")
def synthetic_data() -> tuple:
    raw_df, truth = generate()
    return raw_df, truth


@pytest.fixture(scope="session")
def demo_context(synthetic_data) -> AnalysisContext:
    raw_df, _truth = synthetic_data
    import pandas as pd

    mapping = ResolvedMapping(column_to_canonical=DEMO_COLUMN_MAPPING, confidence_by_column={c: 1.0 for c in DEMO_COLUMN_MAPPING})

    df = raw_df.copy()
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
    canonical = standardize(df, mapping, timestamp_column="Timestamp")
    canonical = normalize_timezone(canonical, "Asia/Kolkata")
    canonical, interval_result = normalize_interval(canonical)

    plant = PlantConfig(
        plant_name="Test Plant",
        ac_capacity_mw=0.18,
        dc_capacity_mwp=0.198,
        module_rating_wp=545.0,
        inverter_capacity_kw=90.0,
        module_technology="Mono PERC",
        bifacial=False,
        timezone="Asia/Kolkata",
        strings_per_scb=4,
        tariff_inr_per_kwh=3.5,
        pr_benchmark_pct=80.0,
        plant_type="fixed_tilt",
        equipment_ratings={"INV-01": 90.0, "INV-02": 90.0},
        architecture=_build_architecture(),
    )

    from analytics.common.config_loader import resolve_thresholds

    thresholds = resolve_thresholds(plant.plant_type, plant.bifacial)

    return AnalysisContext(
        canonical=CanonicalDataAccess.from_frame(canonical),
        plant=plant,
        mapping=mapping,
        timezone="Asia/Kolkata",
        sample_interval_minutes=interval_result.detected_interval_minutes,
        thresholds=thresholds,
        job_meta=JobMeta(job_id="test-job", created_at="2026-01-01T00:00:00Z", trace_id="test-job"),
    )


@pytest.fixture(scope="session")
def ground_truth(synthetic_data) -> GroundTruth:
    return synthetic_data[1]
