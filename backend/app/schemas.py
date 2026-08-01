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
    multi_row_header: bool = False
    header_preview: list[list[str]] = Field(default_factory=list)
    channel_columns: list[dict[str, Any]] = Field(default_factory=list)
    needs_header_confirm: bool = False


class UploadHierarchySignalItem(BaseModel):
    id: str
    label: str
    present: bool
    detected_via: Optional[str] = None
    """Canonical field that satisfied detection (may differ from id for alts)."""
    evidence: Optional[str] = None
    """confirmed | mapped_level_tbd — TBD only when level ID exists but device_type is unconfirmed."""
    kind: Optional[str] = None
    """identity (level-specific) | measurement (credited only when that level is in play)."""


class UploadHierarchyLevel(BaseModel):
    level_id: str
    title: str
    signals: list[UploadHierarchySignalItem] = Field(default_factory=list)
    detected_count: int = 0
    total_count: int = 0
    optional: bool = False


class UploadArchitectureSummary(BaseModel):
    detected: bool = False
    source: str = "not_detected"
    inverter_count: int = 0
    scb_count: int = 0
    string_count: int = 0
    notes: list[str] = Field(default_factory=list)


class UploadModuleImpactItem(BaseModel):
    algorithm_id: str
    title: str
    message: str
    missing_fields: list[str] = Field(default_factory=list)
    missing_config: list[str] = Field(default_factory=list)


class UploadModuleImpactPreview(BaseModel):
    preview_note: str = ""
    ready_count: int = 0
    may_run_count: int = 0
    blocked_count: int = 0
    may_run_modules: list[UploadModuleImpactItem] = Field(default_factory=list)
    blocked_modules: list[UploadModuleImpactItem] = Field(default_factory=list)


class UploadFileInventoryItem(BaseModel):
    """One row in the Upload review “Files in this job” table."""

    filename: str
    sheet_name: Optional[str] = None
    row_count: int = 0
    detected_as: str = "SCADA data"
    signals_present: list[str] = Field(default_factory=list)
    hierarchy_levels: list[UploadHierarchyLevel] = Field(default_factory=list)
    unmapped_column_count: int = 0
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    # Optional: retained for hierarchy rebuild; not shown in UI
    column_names: list[str] = Field(default_factory=list)


class UploadSignalCheckItem(BaseModel):
    id: str
    label: str
    present: bool
    setup_only: bool = False
    hint: Optional[str] = None


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
    file_inventory: list[UploadFileInventoryItem] = Field(default_factory=list)
    total_rows: int = 0
    signal_checklist: list[UploadSignalCheckItem] = Field(default_factory=list)
    hierarchy_overview: list[UploadHierarchyLevel] = Field(default_factory=list)
    architecture_summary: Optional[UploadArchitectureSummary] = None
    module_impact_preview: Optional[UploadModuleImpactPreview] = None
    original_filename: Optional[str] = None
    upload_integrity: Optional["AiIntegrityCheck"] = None
    """Parse-time integrity checklist (rules always; Gemini/ZenMux when configured)."""


class ColumnMappingSuggestion(BaseModel):
    column_name: str
    canonical_field: Optional[str]
    confidence: float
    band: str  # "auto" | "confirm" | "manual"
    field_type: Optional[str] = None
    """e.g. string_current_channel when detected from multi-row stitch."""
    channel_index: Optional[int] = None
    group_label: Optional[str] = None
    hierarchy_level: Optional[str] = None
    """plant | icr | inverter | scb | string | equipment | multi — UI level badge."""
    hierarchy_level_label: Optional[str] = None
    """Human label e.g. Inverter, SCB / SMB, Equipment (row)."""


class MappingSubmission(BaseModel):
    job_id: str
    column_to_canonical: dict[str, str]
    """Final mapping (auto + confirmed + manually assigned). "ignore" is a valid target."""
    column_hierarchy_levels: dict[str, str] | None = None
    """Optional per-column hierarchy overrides from Excel mapping UI (plant/icr/inverter/scb/string)."""


class ArchitectureEntry(BaseModel):
    """Per-SCB layout consumed by clipping / disconnected-string / module-damage algorithms."""

    inverter_id: str
    strings_per_scb: Optional[int] = Field(default=None, ge=1)
    modules_per_string: Optional[int] = Field(default=None, ge=1)
    spare_flag: Optional[bool] = Field(default=None)
    """True when this SCB is a spare (no live strings) — excluded from disconnected-string checks."""
    dc_capacity_kwp: Optional[float] = Field(default=None, gt=0)
    """Optional SCB DC nameplate (kWp) from Complete Analysis Pack hierarchy."""
    ac_capacity_kw: Optional[float] = Field(default=None, gt=0)
    """Optional SCB AC capacity (kW) when relevant."""


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
    # Frozen nameplates from pack / architecture Excel — used for Setup vs import consistency.
    imported_equipment_ratings: Optional[dict[str, float]] = None
    imported_inverter_capacity_kw: Optional[float] = Field(default=None, gt=0)
    imported_ac_capacity_mw: Optional[float] = Field(default=None, gt=0)
    imported_dc_capacity_mwp: Optional[float] = Field(default=None, gt=0)
    architecture_imported: Optional[bool] = None
    architecture_format: Optional[str] = None


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
    preliminary: bool = False
    missing_fields: list[str] = Field(default_factory=list)
    missing_config: list[str] = Field(default_factory=list)
    message: str
    how_to_fix: str = ""
    module_kind: Optional[str] = None
    """fault | analysis | kpi — box plot is analysis (not a fault)."""


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
    file_inventory: list[UploadFileInventoryItem] = Field(default_factory=list)
    total_rows: int = 0
    signal_checklist: list[UploadSignalCheckItem] = Field(default_factory=list)
    hierarchy_overview: list[UploadHierarchyLevel] = Field(default_factory=list)
    architecture_summary: Optional[UploadArchitectureSummary] = None
    module_impact_preview: Optional[UploadModuleImpactPreview] = None
    original_filename: Optional[str] = None


class ArchitectureUploadResponse(BaseModel):
    equipment_ratings: dict[str, float] = Field(default_factory=dict)
    architecture: dict[str, ArchitectureEntry] = Field(default_factory=dict)
    inverters: list[InverterStructureOut] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    row_count: int = 0
    # rated_kw is not on InverterStructureOut — frontend gets it via a parallel list
    inverter_ratings: dict[str, Optional[float]] = Field(default_factory=dict)
    # Present when hierarchy sheet includes a plant row / capacities (kW→MW already converted).
    plant_name: Optional[str] = None
    ac_capacity_mw: Optional[float] = None
    dc_capacity_mwp: Optional[float] = None
    inverter_capacity_kw: Optional[float] = None


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
    is_demo: bool = False
    original_filename: Optional[str] = None

class InverterPrRow(BaseModel):
    inverter_id: str
    pr_pct: float
    ac_energy_kwh: float
    dc_kwp: float


class KpiResponse(BaseModel):
    plant_availability_pct: Optional[float]
    performance_ratio_pct: Optional[float]
    specific_yield_kwh_per_kwp: Optional[float]
    estimated_energy_loss_kwh: Optional[float]
    revenue_loss_inr: Optional[float]
    revenue_loss_available: bool
    fault_count: int
    total_ac_energy_kwh: Optional[float]
    # CUF % = generation / (AC capacity × period hours) × 100
    cuf_pct: Optional[float] = None
    # PLF % = generation / (DC capacity × period hours) × 100
    plf_pct: Optional[float] = None
    # GHI insolation over the analysis window (kWh/m²)
    ghi_kwh_m2: Optional[float] = None
    # GTI / POA insolation over the analysis window (kWh/m²)
    gti_kwh_m2: Optional[float] = None
    inverter_pr: list[InverterPrRow] = Field(default_factory=list)


class IntegrityFinding(BaseModel):
    severity: str  # pass | warn | fail
    code: str
    message: str
    module_id: Optional[str] = None


class AiIntegrityCheck(BaseModel):
    status: str  # pass | warn | fail | skipped | error
    configured: bool = False
    source: str = "none"  # none | rules | ai | rules+ai | rules+gemini | rules+zenmux
    summary: str = ""
    findings: list[IntegrityFinding] = Field(default_factory=list)
    checked_at: Optional[str] = None
    model: Optional[str] = None
    error: Optional[str] = None
    phase: Optional[str] = None  # upload | results
    ai_layer: Optional[str] = None  # ok | failed | skipped | not_configured
    rules_finding_count: Optional[int] = None
    mapping_hints: list[dict[str, Any]] = Field(default_factory=list)
    provider: Optional[str] = None  # gemini | zenmux
    parse_assist: Optional[dict[str, Any]] = None


class ResultsResponse(BaseModel):
    job_id: str
    kpis: KpiResponse
    results: list[dict[str, Any]]
    """Serialized ResultObject list (analytics.core.result.ResultObject.model_dump())."""
    ai_integrity: Optional[AiIntegrityCheck] = None
    """Cached run-integrity checklist; omitted/null when never run or skipped quietly."""


class DemoJobResponse(BaseModel):
    job_id: str
    state: str
