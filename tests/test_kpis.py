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
    assert kpis["total_ac_energy_kwh"] is not None and kpis["total_ac_energy_kwh"] > 0
    # CUF/PLF need capacity + period; demo plant has both.
    assert kpis["cuf_pct"] is not None and kpis["cuf_pct"] > 0
    assert kpis["plf_pct"] is not None and kpis["plf_pct"] > 0
    # GTI falls back to PR insolation; GHI may be absent on some demos.
    assert kpis["gti_kwh_m2"] is not None and kpis["gti_kwh_m2"] > 0
    inv_pr = kpis["inverter_pr"]
    assert isinstance(inv_pr, list) and len(inv_pr) >= 2
    assert all("inverter_id" in r and "pr_pct" in r for r in inv_pr)
    assert inv_pr[0]["pr_pct"] >= inv_pr[-1]["pr_pct"]


def test_compute_plant_kpis_matches_orchestrator(demo_context):
    import analytics.algorithms  # noqa: F401

    run = AnalysisOrchestrator().run(demo_context)
    recomputed = compute_plant_kpis(demo_context, run.results)
    assert recomputed["estimated_energy_loss_kwh"] == run.kpis["estimated_energy_loss_kwh"]
    assert recomputed["cuf_pct"] == run.kpis["cuf_pct"]
    assert recomputed["gti_kwh_m2"] == run.kpis["gti_kwh_m2"]
