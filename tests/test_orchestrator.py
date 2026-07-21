"""Orchestrator contract tests: per-algorithm isolation, unavailable-vs-error handling,
and determinism (same input -> identical output). See docs/architecture_decisions.md §4.
"""
from __future__ import annotations

from analytics.core.registry import clear_registry, get_registry, register_algorithm
from analytics.core.orchestrator import AnalysisOrchestrator
from analytics.core.result import ResultObject, ResultStatus


def test_full_registry_runs_and_every_algorithm_returns_a_result(demo_context):
    import analytics.algorithms  # noqa: F401

    run = AnalysisOrchestrator().run(demo_context)
    algorithm_ids = {r.algorithm_id for r in run.results}
    expected = {
        "inverter_efficiency",
        "box_plot",
        "module_damage",
        "clipping_power",
        "clipping_current",
        "disconnected_strings",
        "string_outlier",
    }
    assert expected.issubset(algorithm_ids)
    for result in run.results:
        assert result.status in (ResultStatus.OK, ResultStatus.UNAVAILABLE, ResultStatus.ERROR)


def test_a_failing_algorithm_does_not_crash_the_job(demo_context):
    saved = get_registry()
    try:
        clear_registry()

        @register_algorithm("boom", "0.0.1", required_fields=())
        def _boom(context):  # noqa: ARG001
            raise ValueError("intentional test failure")

        @register_algorithm("fine", "1.0.0", required_fields=())
        def _fine(context):  # noqa: ARG001
            return ResultObject(algorithm_id="fine", algorithm_version="1.0.0", status=ResultStatus.OK, title="Fine", summary="ok")

        run = AnalysisOrchestrator().run(demo_context)
        by_id = {r.algorithm_id: r for r in run.results}
        assert by_id["boom"].status == ResultStatus.ERROR
        assert by_id["boom"].error is not None
        assert by_id["fine"].status == ResultStatus.OK
    finally:
        clear_registry()
        for spec in saved.values():
            register_algorithm(spec.algorithm_id, spec.version, tuple(spec.required_fields), spec.enabled, spec.description)(spec.fn)


def test_determinism_same_input_same_output(demo_context):
    import analytics.algorithms  # noqa: F401

    run_a = AnalysisOrchestrator().run(demo_context)
    run_b = AnalysisOrchestrator().run(demo_context)

    for a, b in zip(sorted(run_a.results, key=lambda r: r.algorithm_id), sorted(run_b.results, key=lambda r: r.algorithm_id)):
        assert a.status == b.status
        assert a.loss_energy_kwh == b.loss_energy_kwh
        assert a.metrics == b.metrics
