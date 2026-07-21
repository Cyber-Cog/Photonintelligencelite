"""Shared report payload consumed by both the PDF and Excel builders.

Keeping one dataclass here (rather than each builder reaching into the orchestrator run
independently) guarantees the two output formats never drift in content — both are built
from exactly the same numbers. See docs/PRD.md §7.11, §20.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from analytics.core.context import PlantConfig
from analytics.core.orchestrator import OrchestratorRun
from analytics.preprocessing.interval_normalize import IntervalNormalizationResult
from analytics.preprocessing.validation import ValidationReport


@dataclass
class ReportContext:
    job_id: str
    generated_at: str
    plant: PlantConfig
    run: OrchestratorRun
    validation: ValidationReport
    interval_result: IntervalNormalizationResult
    mapping_confidence_by_column: dict[str, float] = field(default_factory=dict)
    external_irradiance_used: bool = False  # always False in MVP — feature deferred (see docs/PRD.md §0)
    title: Optional[str] = None

    @property
    def report_title(self) -> str:
        return self.title or f"{self.plant.plant_name} — Solar Performance Analysis"
