export interface ColumnMappingSuggestion {
  column_name: string;
  canonical_field: string | null;
  confidence: number;
  band: "auto" | "confirm" | "manual";
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
}

export interface ArchitectureEntry {
  inverter_id: string;
  strings_per_scb?: number | null;
  modules_per_string?: number | null;
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
}

export interface ModuleReadiness {
  algorithm_id: string;
  title: string;
  will_run: boolean;
  missing_fields: string[];
  missing_config: string[];
  message: string;
  how_to_fix: string;
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
}

export interface ResultsResponse {
  job_id: string;
  kpis: KpiResponse;
  results: ResultObject[];
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
