"""KPI assembly sanity checks — see docs/architecture_decisions.md §5 for formulas."""
from __future__ import annotations

from analytics.algorithms.kpis import compute_plant_kpis
from analytics.core.orchestrator import AnalysisOrchestrator


def test_kpis_are_computed_and_revenue_loss_available(demo_context):
    import analytics.algorithms  # noqa: F401 - registers algorithms

    run = AnalysisOrchestrator().run(demo_context)
    kpis = run.kpis

    assert kpis["revenue_loss_available"] is True  # demo plant supplies a tariff
    assert kpis["plant_availability_pct"] is not None
    assert 0.0 <= kpis["plant_availability_pct"] <= 100.0
    assert kpis["performance_ratio_pct"] is not None
    assert kpis["specific_yield_kwh_per_kwp"] is not None
    assert kpis["estimated_energy_loss_kwh"] >= 0
    assert kpis["fault_count"] >= 1


def test_compute_plant_kpis_matches_orchestrator(demo_context):
    import analytics.algorithms  # noqa: F401

    run = AnalysisOrchestrator().run(demo_context)
    recomputed = compute_plant_kpis(demo_context, run.results)
    assert recomputed["estimated_energy_loss_kwh"] == run.kpis["estimated_energy_loss_kwh"]
