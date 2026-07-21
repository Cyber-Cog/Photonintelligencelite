"""Unified ResultObject contract. Every algorithm returns exactly this shape.

See docs/architecture_decisions.md §3.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ResultStatus(str, Enum):
    OK = "ok"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class ResultTable(BaseModel):
    title: str
    columns: list[str]
    rows: list[list[Any]]


class ChartSpec(BaseModel):
    """A Plotly-compatible chart specification, serialized as plain JSON.

    `figure` holds the Plotly figure dict (`{"data": [...], "layout": {...}}`) so the
    frontend can render directly with react-plotly.js and export PNG/SVG client-side.
    """

    chart_id: str
    title: str
    chart_type: str
    figure: dict[str, Any]


class EvidenceRef(BaseModel):
    """Traceability contract: every loss/fault number must point back to its source.

    Required per the PRD's "deterministic and explainable analytics" principle.
    """

    equipment_ids: list[str] = Field(default_factory=list)
    time_range_start: Optional[str] = None
    time_range_end: Optional[str] = None
    source_fields: list[str] = Field(default_factory=list)
    affected_sample_count: int = 0
    total_sample_count: int = 0
    notes: Optional[str] = None


class ResultObject(BaseModel):
    algorithm_id: str
    algorithm_version: str
    status: ResultStatus

    title: str
    summary: str
    severity: Optional[str] = None  # "info" | "low" | "medium" | "high" | "critical"
    confidence: Optional[float] = None

    affected_equipment: list[str] = Field(default_factory=list)
    loss_energy_kwh: Optional[float] = None
    loss_revenue: Optional[float] = None

    metrics: dict[str, float] = Field(default_factory=dict)
    tables: list[ResultTable] = Field(default_factory=list)
    charts: list[ChartSpec] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    thresholds_used: dict[str, float] = Field(default_factory=dict)
    evidence: EvidenceRef = Field(default_factory=EvidenceRef)
    evidence_charts: list[ChartSpec] = Field(default_factory=list)
    """PIC-style diagnostic charts: reference vs actual, shaded fault windows — shown in Investigate."""
    execution_time_ms: float = 0.0
    error: Optional[str] = None

    @classmethod
    def unavailable(
        cls,
        algorithm_id: str,
        algorithm_version: str,
        reason: str,
        execution_time_ms: float = 0.0,
    ) -> "ResultObject":
        return cls(
            algorithm_id=algorithm_id,
            algorithm_version=algorithm_version,
            status=ResultStatus.UNAVAILABLE,
            title=algorithm_id.replace("_", " ").title(),
            summary=reason,
            execution_time_ms=execution_time_ms,
        )

    @classmethod
    def error_result(
        cls,
        algorithm_id: str,
        algorithm_version: str,
        error: str,
        execution_time_ms: float = 0.0,
    ) -> "ResultObject":
        return cls(
            algorithm_id=algorithm_id,
            algorithm_version=algorithm_version,
            status=ResultStatus.ERROR,
            title=algorithm_id.replace("_", " ").title(),
            summary="This module could not complete for this job. Other results are unaffected.",
            error=error,
            execution_time_ms=execution_time_ms,
        )
