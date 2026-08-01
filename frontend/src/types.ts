export interface ColumnMappingSuggestion {
  column_name: string;
  canonical_field: string | null;
  confidence: number;
  band: "auto" | "confirm" | "manual";
  hierarchy_level?: string | null;
  hierarchy_level_label?: string | null;
}

export interface ExcelParseReport {
  layout: string;
  strategy: string;
  sheet_name: string;
  confidence: number;
  header_rows: number[];
  timestamp_column?: string | null;
  inverters_found: string[];
  columns_mapped: string[];
  row_count: number;
  warnings: string[];
  sheets_probed: string[];
  error?: string | null;
  multi_row_header?: boolean;
  header_preview?: string[][];
  channel_columns?: Array<{
    index: number;
    display_name: string;
    primary_candidate: string;
    channel_index?: number | null;
    field_type?: string | null;
  }>;
  needs_header_confirm?: boolean;
}

export interface UploadHierarchySignalItem {
  id: string;
  label: string;
  present: boolean;
  detected_via?: string | null;
  /** confirmed | mapped_level_tbd — measurements can appear at multiple levels */
  evidence?: string | null;
  /** identity (level-specific) | measurement (multi-level) */
  kind?: string | null;
}

export interface UploadHierarchyLevel {
  level_id: string;
  title: string;
  signals: UploadHierarchySignalItem[];
  detected_count: number;
  total_count: number;
  optional?: boolean;
}

export interface UploadArchitectureSummary {
  detected: boolean;
  source: string;
  inverter_count: number;
  scb_count: number;
  string_count: number;
  notes: string[];
}

export interface UploadModuleImpactItem {
  algorithm_id: string;
  title: string;
  message: string;
  missing_fields: string[];
  missing_config: string[];
}

export interface UploadModuleImpactPreview {
  preview_note: string;
  ready_count: number;
  may_run_count?: number;
  blocked_count: number;
  may_run_modules?: UploadModuleImpactItem[];
  blocked_modules: UploadModuleImpactItem[];
}

export interface UploadFileInventoryItem {
  filename: string;
  sheet_name?: string | null;
  row_count: number;
  detected_as: string;
  signals_present: string[];
  hierarchy_levels?: UploadHierarchyLevel[];
  unmapped_column_count: number;
  date_range_start?: string | null;
  date_range_end?: string | null;
}

export interface UploadSignalCheckItem {
  id: string;
  label: string;
  present: boolean;
  setup_only: boolean;
  hint?: string | null;
}

export interface UploadResponse {
  job_id: string;
  state: string;
  detected_columns: string[];
  mapping_suggestions: ColumnMappingSuggestion[];
  requires_manual_mapping: boolean;
  parse_report?: ExcelParseReport | null;
  looks_like_complete_pack?: boolean;
  pack_match_ratio?: number;
  file_inventory?: UploadFileInventoryItem[];
  total_rows?: number;
  signal_checklist?: UploadSignalCheckItem[];
  hierarchy_overview?: UploadHierarchyLevel[];
  architecture_summary?: UploadArchitectureSummary | null;
  module_impact_preview?: UploadModuleImpactPreview | null;
  original_filename?: string | null;
  upload_integrity?: AiIntegrityCheck | null;
}

export interface ArchitectureEntry {
  inverter_id: string;
  strings_per_scb?: number | null;
  modules_per_string?: number | null;
  dc_capacity_kwp?: number | null;
  ac_capacity_kw?: number | null;
}

export interface PlantConfigInput {
  job_id: string;
  plant_name: string;
  ac_capacity_mw: number;
  dc_capacity_mwp: number;
  module_rating_wp: number;
  inverter_capacity_kw: number;
  module_technology: string;
  bifacial: boolean;
  timezone: string;
  strings_per_scb?: number | null;
  tariff_inr_per_kwh?: number | null;
  pr_benchmark_pct?: number | null;
  plant_type: string;
  equipment_ratings?: Record<string, number>;
  architecture?: Record<string, ArchitectureEntry>;
  imported_equipment_ratings?: Record<string, number>;
  imported_inverter_capacity_kw?: number;
  imported_ac_capacity_mw?: number;
  imported_dc_capacity_mwp?: number;
  architecture_imported?: boolean;
  architecture_format?: string;
}

export interface ScbStructure {
  scb_id: string;
  strings_per_scb: number | null;
  strings_detected: boolean;
}

export interface InverterStructure {
  inverter_id: string;
  scbs: ScbStructure[];
}

export interface DetectEquipmentResponse {
  detected: boolean;
  source: string | null;
  unique_id_count: number;
  inverters: InverterStructure[];
  notes: string[];
}

export interface ArchitectureUploadResponse {
  equipment_ratings: Record<string, number>;
  architecture: Record<string, ArchitectureEntry>;
  inverters: InverterStructure[];
  notes: string[];
  row_count: number;
  inverter_ratings: Record<string, number | null>;
  plant_name?: string | null;
  ac_capacity_mw?: number | null;
  dc_capacity_mwp?: number | null;
  inverter_capacity_kw?: number | null;
}

export interface ModuleReadiness {
  algorithm_id: string;
  title: string;
  will_run: boolean;
  preliminary?: boolean;
  missing_fields: string[];
  missing_config: string[];
  message: string;
  how_to_fix: string;
  module_kind?: string;
}

export interface ValidationIssue {
  code: string;
  severity: "blocker" | "warning";
  message: string;
  likely_cause: string;
  blocks_analysis: boolean;
  affected_rows: number;
  affected_columns: string[];
  sample_values?: string[];
  remediation?: string;
}

export interface ValidationResponse {
  job_id: string;
  row_count: number;
  column_count: number;
  detected_interval_minutes: number;
  is_irregular_interval: boolean;
  interval_notes: string[];
  blockers: ValidationIssue[];
  warnings: ValidationIssue[];
  can_proceed: boolean;
  module_readiness: ModuleReadiness[];
  timestamp_column?: string | null;
  timestamp_parse_ok?: number;
  timestamp_parse_fail?: number;
  can_proceed_with_row_drops?: boolean;
  proceed_with_drops_min_ok_ratio?: number;
  recovery_actions?: string[];
  rows_that_would_be_dropped?: number;
  rows_that_would_be_kept?: number;
  state?: string | null;
}

export interface SetupContextResponse {
  job_id: string;
  state: string;
  detected_columns: string[];
  mapping_suggestions: ColumnMappingSuggestion[];
  requires_manual_mapping: boolean;
  current_mapping: Record<string, string>;
  plant_config: Record<string, unknown> | null;
  looks_like_complete_pack?: boolean;
  pack_match_ratio?: number;
  file_inventory?: UploadFileInventoryItem[];
  total_rows?: number;
  signal_checklist?: UploadSignalCheckItem[];
  hierarchy_overview?: UploadHierarchyLevel[];
  architecture_summary?: UploadArchitectureSummary | null;
  module_impact_preview?: UploadModuleImpactPreview | null;
  original_filename?: string | null;
}

export interface JobStatusResponse {
  job_id: string;
  state: string;
  progress_message: string | null;
  error_summary: string | null;
  created_at: string;
  updated_at: string;
  queue_position: number | null;
  estimated_wait_seconds: number | null;
  is_active: boolean;
  is_demo?: boolean;
  original_filename?: string | null;
}

export interface InverterPrRow {
  inverter_id: string;
  pr_pct: number;
  ac_energy_kwh: number;
  dc_kwp: number;
}

export interface KpiResponse {
  plant_availability_pct: number | null;
  performance_ratio_pct: number | null;
  specific_yield_kwh_per_kwp: number | null;
  estimated_energy_loss_kwh: number | null;
  revenue_loss_inr: number | null;
  revenue_loss_available: boolean;
  fault_count: number;
  total_ac_energy_kwh: number | null;
  /** CUF % — generation / (AC capacity × period hours) × 100 */
  cuf_pct?: number | null;
  /** PLF % — generation / (DC capacity × period hours) × 100 */
  plf_pct?: number | null;
  /** GHI insolation (kWh/m²) over the analysis window */
  ghi_kwh_m2?: number | null;
  /** GTI / POA insolation (kWh/m²) over the analysis window */
  gti_kwh_m2?: number | null;
  /** Per-inverter PR for Summary comparison (not a fault module). */
  inverter_pr?: InverterPrRow[];
}

export interface ResultTable {
  title: string;
  columns: string[];
  rows: unknown[][];
}

export interface ChartSpec {
  chart_id: string;
  title: string;
  chart_type: string;
  figure: { data: unknown[]; layout: Record<string, unknown> };
}

export interface EvidenceRef {
  equipment_ids: string[];
  time_range_start: string | null;
  time_range_end: string | null;
  source_fields: string[];
  affected_sample_count: number;
  total_sample_count: number;
  notes: string | null;
}

export interface DataPreviewResponse {
  source: string;
  columns: string[];
  rows: string[][];
  total_rows: number;
  offset: number;
  limit: number;
  upload_sources?: string[];
  original_filename?: string | null;
  time_column?: string | null;
  time_min?: string | null;
  time_max?: string | null;
  start?: string | null;
  end?: string | null;
  date_filtered?: boolean;
  unfiltered_rows?: number;
}

export interface ArchitectureScbView {
  scb_id: string;
  strings_per_scb?: number | null;
  modules_per_string?: number | null;
  spare_flag?: boolean;
}

export interface ArchitectureInverterView {
  inverter_id: string;
  rated_kw?: number | null;
  scbs: ArchitectureScbView[];
}

export interface ArchitectureViewResponse {
  plant_name: string | null;
  ac_capacity_mw?: number | null;
  dc_capacity_mwp?: number | null;
  module_rating_wp?: number | null;
  timezone?: string | null;
  inverters: ArchitectureInverterView[];
  summary: { inverter_count: number; scb_count: number; string_count: number | null };
  source?: string;
  hint?: string | null;
}

export interface TimeseriesSeries {
  name: string;
  equipment_id: string;
  signal: string;
  timestamps: string[];
  values: number[];
}

export interface TimeseriesResponse {
  series: TimeseriesSeries[];
  point_count: number;
  note?: string;
}

export interface ResultObject {
  algorithm_id: string;
  algorithm_version: string;
  status: "ok" | "unavailable" | "error";
  title: string;
  summary: string;
  severity: string | null;
  confidence: number | null;
  affected_equipment: string[];
  loss_energy_kwh: number | null;
  loss_revenue: number | null;
  metrics: Record<string, number>;
  tables: ResultTable[];
  charts: ChartSpec[];
  evidence_charts?: ChartSpec[];
  recommendations: string[];
  thresholds_used: Record<string, number>;
  evidence: EvidenceRef;
  execution_time_ms: number;
  error: string | null;
  /** Canonical fields missing when status=unavailable (honest Needs: messaging). */
  missing_fields?: string[];
  missing_config?: string[];
  /** "fault" | "analysis" | "kpi" — guides Diagnostics framing. */
  module_kind?: string | null;
}

export interface ResultsResponse {
  job_id: string;
  kpis: KpiResponse;
  results: ResultObject[];
  ai_integrity?: AiIntegrityCheck | null;
}

export interface IntegrityFinding {
  severity: string;
  code: string;
  message: string;
  module_id?: string | null;
}

export interface AiIntegrityCheck {
  status: string;
  configured: boolean;
  source: string;
  summary: string;
  findings: IntegrityFinding[];
  checked_at?: string | null;
  model?: string | null;
  error?: string | null;
  phase?: string | null;
  /** ok | failed | skipped | not_configured */
  ai_layer?: string | null;
  rules_finding_count?: number | null;
  mapping_hints?: Array<{
    column_name: string;
    canonical_field: string;
    confidence?: number;
  }>;
  /** gemini | zenmux */
  provider?: string | null;
  parse_assist?: {
    attempted?: boolean;
    applied?: number;
    model?: string | null;
    error?: string | null;
    provider?: string | null;
  } | null;
}

export interface AdminUser {
  id: string;
  email: string;
  name: string;
  role: string;
  email_verified: boolean;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
  job_count: number;
}

export interface AdminSession {
  id: string;
  user_id: string;
  user_email: string | null;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
  ip: string | null;
  user_agent: string | null;
}

export interface AdminJob {
  id: string;
  state: string;
  user_id: string | null;
  user_email: string | null;
  is_demo: boolean;
  original_filename: string | null;
  plant_name: string | null;
  created_at: string;
  completed_at: string | null;
  abandoned_at: string | null;
}

export interface FunnelStats {
  uploaded: number;
  mapping: number;
  validating: number;
  queued_or_running: number;
  completed: number;
  failed: number;
  abandoned: number;
  demo: number;
}

export interface AuditEvent {
  id: string;
  action: string;
  user_id: string | null;
  job_id: string | null;
  ip: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface FaultModuleCategory {
  algorithm_id: string;
  label: string;
  hint: string;
  category: "actionable" | "non_actionable";
  is_default: boolean;
}

export interface FaultCategoriesResponse {
  actionable: string[];
  non_actionable: string[];
  categories: Record<string, "actionable" | "non_actionable">;
  modules: FaultModuleCategory[];
}
