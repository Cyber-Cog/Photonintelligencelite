"""API request/response schemas. Kept separate from analytics.core.result so the analytics
package stays framework-agnostic and importable without FastAPI installed.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ExcelParseReportOut(BaseModel):
    """Diagnostics from the multi-strategy Excel converter (absent for CSV uploads)."""

    layout: str
    strategy: str
    sheet_name: str
    confidence: float
    header_rows: list[int] = Field(default_factory=list)
    timestamp_column: Optional[str] = None
    inverters_found: list[str] = Field(default_factory=list)
    columns_mapped: list[str] = Field(default_factory=list)
    row_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    sheets_probed: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class UploadResponse(BaseModel):
    job_id: str
    state: str
    detected_columns: list[str]
    mapping_suggestions: list["ColumnMappingSuggestion"]
    requires_manual_mapping: bool
    parse_report: Optional[ExcelParseReportOut] = None
    looks_like_complete_pack: bool = False
    pack_match_ratio: float = 0.0
    """Fraction of official Complete Analysis Pack headers present (0..1)."""


class ColumnMappingSuggestion(BaseModel):
    column_name: str
    canonical_field: Optional[str]
    confidence: float
    band: str  # "auto" | "confirm" | "manual"


class MappingSubmission(BaseModel):
    job_id: str
    column_to_canonical: dict[str, str]
    """Final mapping (auto + confirmed + manually assigned). "ignore" is a valid target."""


class ArchitectureEntry(BaseModel):
    """Per-SCB layout consumed by clipping / disconnected-string / module-damage algorithms."""

    inverter_id: str
    strings_per_scb: Optional[int] = Field(default=None, ge=1)
    modules_per_string: Optional[int] = Field(default=None, ge=1)
    spare_flag: Optional[bool] = Field(default=None)
    """True when this SCB is a spare (no live strings) — excluded from disconnected-string checks."""


class PlantConfigSubmission(BaseModel):
    job_id: str
    plant_name: str
    ac_capacity_mw: float = Field(gt=0)
    dc_capacity_mwp: float = Field(gt=0)
    module_rating_wp: float = Field(gt=0)
    inverter_capacity_kw: float = Field(gt=0)
    """Plant-wide fallback rating (kW). Used when an inverter has no entry in equipment_ratings."""
    module_technology: str
    bifacial: bool
    timezone: str
    strings_per_scb: Optional[int] = None
    """Plant-wide fallback string count when a SCB is missing from architecture."""
    tariff_inr_per_kwh: Optional[float] = None
    pr_benchmark_pct: Optional[float] = None
    plant_type: str = "fixed_tilt"
    equipment_ratings: dict[str, float] = Field(default_factory=dict)
    """Per-inverter rated AC kW (inverter_id -> kW). Omit inverters whose rating is unknown."""
    architecture: dict[str, ArchitectureEntry] = Field(default_factory=dict)
    """Per-SCB architecture keyed by scb_id."""
    threshold_overrides: dict[str, dict[str, float]] = Field(default_factory=dict)


class DetectEquipmentRequest(BaseModel):
    job_id: str
    column_to_canonical: dict[str, str]


class ScbStructureOut(BaseModel):
    scb_id: str
    strings_per_scb: Optional[int] = None
    strings_detected: bool = False


class InverterStructureOut(BaseModel):
    inverter_id: str
    scbs: list[ScbStructureOut] = Field(default_factory=list)


class DetectEquipmentResponse(BaseModel):
    detected: bool
    source: Optional[str] = None
    unique_id_count: int = 0
    inverters: list[InverterStructureOut] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ValidationIssueOut(BaseModel):
    code: str
    severity: str
    message: str
    likely_cause: str
    blocks_analysis: bool
    affected_rows: int
    affected_columns: list[str]
    sample_values: list[str] = Field(default_factory=list)
    remediation: str = ""


class ModuleReadinessOut(BaseModel):
    algorithm_id: str
    title: str
    will_run: bool
    missing_fields: list[str] = Field(default_factory=list)
    missing_config: list[str] = Field(default_factory=list)
    message: str
    how_to_fix: str = ""


class ValidationResponse(BaseModel):
    job_id: str
    row_count: int
    column_count: int
    detected_interval_minutes: float
    is_irregular_interval: bool
    interval_notes: list[str]
    blockers: list[ValidationIssueOut]
    warnings: list[ValidationIssueOut]
    can_proceed: bool
    module_readiness: list[ModuleReadinessOut] = Field(default_factory=list)
    timestamp_column: Optional[str] = None
    timestamp_parse_ok: int = 0
    timestamp_parse_fail: int = 0
    can_proceed_with_row_drops: bool = False
    proceed_with_drops_min_ok_ratio: float = 0.80
    recovery_actions: list[str] = Field(default_factory=list)
    rows_that_would_be_dropped: int = 0
    rows_that_would_be_kept: int = 0
    state: Optional[str] = None


class SetupContextResponse(BaseModel):
    """Allows Setup to reload after validation recovery without forcing re-upload."""

    job_id: str
    state: str
    detected_columns: list[str]
    mapping_suggestions: list[ColumnMappingSuggestion]
    requires_manual_mapping: bool
    current_mapping: dict[str, str] = Field(default_factory=dict)
    plant_config: Optional[dict[str, Any]] = None
    looks_like_complete_pack: bool = False
    pack_match_ratio: float = 0.0


class ArchitectureUploadResponse(BaseModel):
    equipment_ratings: dict[str, float] = Field(default_factory=dict)
    architecture: dict[str, ArchitectureEntry] = Field(default_factory=dict)
    inverters: list[InverterStructureOut] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    row_count: int = 0
    # rated_kw is not on InverterStructureOut — frontend gets it via a parallel list
    inverter_ratings: dict[str, Optional[float]] = Field(default_factory=dict)


class PatternApplyRequest(BaseModel):
    inverter_ids: list[str]
    smbs_per_inverter: int = Field(ge=1, le=64)
    strings_per_smb: int = Field(ge=1, le=64)
    rated_kw: Optional[float] = Field(default=None, gt=0)
    existing_inverters: list[dict[str, Any]] = Field(default_factory=list)


class PatternApplyResponse(BaseModel):
    inverters: list[dict[str, Any]]
    notes: list[str] = Field(default_factory=list)


class AcknowledgeWarningsRequest(BaseModel):
    job_id: str
    acknowledged: bool = True
    drop_unparseable_timestamps: bool = False
    """When True and validation allows it (≥80% timestamps OK), re-run validation dropping bad rows."""


class RetryValidationRequest(BaseModel):
    job_id: str
    drop_unparseable_timestamps: bool = False


class JobStatusResponse(BaseModel):
    job_id: str
    state: str
    progress_message: Optional[str]
    error_summary: Optional[str]
    created_at: str
    updated_at: str
    queue_position: Optional[int] = None
    estimated_wait_seconds: Optional[float] = None
    is_active: bool

class KpiResponse(BaseModel):
    plant_availability_pct: Optional[float]
    performance_ratio_pct: Optional[float]
    specific_yield_kwh_per_kwp: Optional[float]
    estimated_energy_loss_kwh: Optional[float]
    revenue_loss_inr: Optional[float]
    revenue_loss_available: bool
    fault_count: int
    total_ac_energy_kwh: Optional[float]


class ResultsResponse(BaseModel):
    job_id: str
    kpis: KpiResponse
    results: list[dict[str, Any]]
    """Serialized ResultObject list (analytics.core.result.ResultObject.model_dump())."""


class DemoJobResponse(BaseModel):
    job_id: str
    state: str
