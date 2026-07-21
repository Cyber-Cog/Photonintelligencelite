"""Analytics orchestrator: the only thing the backend calls.

Runs every registered, enabled algorithm against the shared AnalysisContext, isolates
per-algorithm failures, and assembles the unified result set + plant KPIs.
See docs/architecture_decisions.md §4-5.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from analytics.common.prerequisites import (
    ALGORITHM_PREREQUISITES,
    actionable_unavailable_message,
    missing_fields_for_algorithm,
)
from analytics.core.context import AnalysisContext
from analytics.core.registry import AlgorithmSpec, get_registry
from analytics.core.result import ResultObject, ResultStatus

logger = logging.getLogger("pic_lite.analytics.orchestrator")


@dataclass
class OrchestratorRun:
    results: list[ResultObject] = field(default_factory=list)
    kpis: dict[str, float | None] = field(default_factory=dict)
    total_execution_time_ms: float = 0.0

    def by_status(self, status: ResultStatus) -> list[ResultObject]:
        return [r for r in self.results if r.status == status]

    def total_loss_kwh(self) -> float:
        return sum(r.loss_energy_kwh or 0.0 for r in self.results if r.status == ResultStatus.OK)


class AnalysisOrchestrator:
    def __init__(self, algorithms: dict[str, AlgorithmSpec] | None = None):
        self._algorithms = algorithms if algorithms is not None else get_registry()

    def _missing_fields(self, context: AnalysisContext, spec: AlgorithmSpec) -> set[str]:
        # Use non-null fields only — schema always lists telemetry columns even when
        # all-null for this upload (same rule as validation readiness).
        available = set(context.canonical.populated_columns())
        # Prefer the central prerequisite map (includes any-of irradiance groups, etc.).
        mapped = missing_fields_for_algorithm(spec.algorithm_id, available)
        if mapped or spec.algorithm_id in ALGORITHM_PREREQUISITES:
            return mapped
        if not spec.required_fields:
            return set()
        return {f for f in spec.required_fields if f not in available}

    def run(self, context: AnalysisContext) -> OrchestratorRun:
        run = OrchestratorRun()
        for algorithm_id in sorted(self._algorithms.keys()):
            spec = self._algorithms[algorithm_id]
            if not spec.enabled:
                continue

            missing = self._missing_fields(context, spec)
            if missing:
                logger.info("algorithm=%s unavailable missing_fields=%s", algorithm_id, sorted(missing))
                reason = actionable_unavailable_message(algorithm_id, missing)
                unavailable = ResultObject.unavailable(algorithm_id, spec.version, reason=reason)
                prereq = ALGORITHM_PREREQUISITES.get(algorithm_id)
                if prereq:
                    unavailable.title = prereq.title
                run.results.append(unavailable)
                continue

            start = time.perf_counter()
            try:
                result = spec.fn(context)
                result.execution_time_ms = (time.perf_counter() - start) * 1000.0
                logger.info(
                    "algorithm=%s status=%s duration_ms=%.1f",
                    algorithm_id,
                    result.status,
                    result.execution_time_ms,
                )
            except Exception as exc:  # noqa: BLE001 - isolate any algorithm failure
                duration_ms = (time.perf_counter() - start) * 1000.0
                logger.exception("algorithm=%s failed duration_ms=%.1f", algorithm_id, duration_ms)
                result = ResultObject.error_result(
                    algorithm_id, spec.version, error=str(exc)[:500], execution_time_ms=duration_ms
                )
            run.results.append(result)
            run.total_execution_time_ms += result.execution_time_ms

        from analytics.algorithms.kpis import compute_plant_kpis  # local import avoids cycle

        run.kpis = compute_plant_kpis(context, run.results)
        return run
