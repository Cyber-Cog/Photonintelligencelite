"""Algorithm registry.

Algorithms register themselves via the ``@register_algorithm`` decorator instead of the
orchestrator importing and calling them by name. Adding a new algorithm later means adding
a new module + decorator, never editing orchestration code. See docs/architecture_decisions.md §4.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from analytics.core.context import AnalysisContext
from analytics.core.result import ResultObject


class AlgorithmFn(Protocol):
    def __call__(self, context: AnalysisContext) -> ResultObject: ...


@dataclass(frozen=True)
class AlgorithmSpec:
    algorithm_id: str
    version: str
    required_fields: frozenset[str]
    """Canonical fields that must be present (non-null somewhere) for this algorithm to run."""
    fn: AlgorithmFn
    enabled: bool = True
    description: str = ""


_REGISTRY: dict[str, AlgorithmSpec] = {}


def register_algorithm(
    algorithm_id: str,
    version: str,
    required_fields: tuple[str, ...] = (),
    enabled: bool = True,
    description: str = "",
) -> Callable[[AlgorithmFn], AlgorithmFn]:
    def decorator(fn: AlgorithmFn) -> AlgorithmFn:
        _REGISTRY[algorithm_id] = AlgorithmSpec(
            algorithm_id=algorithm_id,
            version=version,
            required_fields=frozenset(required_fields),
            fn=fn,
            enabled=enabled,
            description=description,
        )
        return fn

    return decorator


def get_registry() -> dict[str, AlgorithmSpec]:
    return dict(_REGISTRY)


def clear_registry() -> None:
    """Test-only helper."""
    _REGISTRY.clear()
