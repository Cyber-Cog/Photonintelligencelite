# PIC Lite — Architecture Decisions

Companion to [`docs/PRD.md`](PRD.md). This document defines the core contracts that every
part of the system (backend, analytics, frontend) is built against.

## 1. Canonical data schema

> **Official upload format:** see [`COMPLETE_DATA_FORMAT.md`](COMPLETE_DATA_FORMAT.md)
> (Complete Analysis Pack — Excel / ZIP templates at `/api/templates/complete-analysis`).

All vendor-specific SCADA columns are mapped **once**, during standardization, into this
fixed canonical schema. Algorithms never see vendor column names.

| Field | Type | Notes |
|---|---|---|
| `timestamp_utc` | datetime64[ns, UTC] | Converted from the plant's declared timezone |
| `device_id` | string | Generic equipment identifier (whatever level the row is at) |
| `device_type` | enum | `inverter` \| `scb` \| `string` \| `plant` \| `wms` |
| `inverter_id` | string \| null | Resolved parent inverter, when derivable |
| `scb_id` | string \| null | Resolved parent SCB/MPPT, when derivable |
| `string_id` | string \| null | Resolved string identifier, when present |
| `ac_power_kw` | float \| null | |
| `dc_power_kw` | float \| null | |
| `dc_current_a` | float \| null | |
| `dc_voltage_v` | float \| null | |
| `poa_w_m2` | float \| null | Plane-of-array irradiance |
| `ghi_w_m2` | float \| null | Global horizontal irradiance |
| `module_temp_c` | float \| null | |
| `ambient_temp_c` | float \| null | |
| `energy_kwh` | float \| null | Cumulative or interval energy, as detected |

Canonical rows are written as partitioned Parquet under
`{job_dir}/canonical/device_type={type}/date={YYYY-MM-DD}/part.parquet` so algorithms and
the orchestrator can lazily read only what they need (Polars `scan_parquet`).

## 2. `AnalysisContext`

Defined in [`analytics/core/context.py`](../analytics/core/context.py). Immutable per job.
Every algorithm's `run(context)` receives exactly one context object, never raw DataFrames
plus scattered arguments. It exposes:

- `canonical` — a `CanonicalDataAccess` handle (lazy Polars scan over the job's partitions),
  not a materialized pandas DataFrame.
- `plant` — validated `PlantConfig` (capacities, tariff, PR benchmark, strings-per-SCB, etc).
- `mapping` — resolved column mapping + detected OEM signature.
- `timezone` / `sample_interval_minutes` — normalization outcome.
- `thresholds` — effective per-algorithm threshold values (defaults merged with any
  per-job overrides), always recorded back onto the result.
- `job_meta` — job id, created_at, trace id for logging correlation.

## 3. `ResultObject`

Defined in [`analytics/core/result.py`](../analytics/core/result.py). Every algorithm
returns exactly this Pydantic model — never a raw DataFrame or ad-hoc dict:

```text
algorithm_id, algorithm_version, status            # status: ok | unavailable | error
title, summary, severity, confidence
affected_equipment: list[str]
loss_energy_kwh, loss_revenue
metrics: dict[str, float]
tables: list[ResultTable]
charts: list[ChartSpec]
recommendations: list[str]
thresholds_used: dict[str, float]
evidence: EvidenceRef                              # equipment ids, time range, row counts, source fields
execution_time_ms
error: str | null
```

`status="unavailable"` is used when prerequisites are missing (e.g. no irradiance column
for a clipping algorithm) — this is expected, not a crash. `status="error"` is used when the
algorithm raised unexpectedly; the orchestrator catches it, wraps it into this shape, and the
job continues.

## 4. Algorithm registry and orchestrator

- [`analytics/core/registry.py`](../analytics/core/registry.py) — `@register_algorithm(id, version, required_fields)`
  decorator populates a module-level registry: `{algorithm_id: AlgorithmSpec}`.
- [`analytics/core/orchestrator.py`](../analytics/core/orchestrator.py) — the **only** thing
  the backend calls. For each registered, enabled algorithm: checks `required_fields` against
  the resolved mapping, calls `run(context)` inside a try/except, records `execution_time_ms`,
  and appends the result (or a synthesized `unavailable`/`error` result) to the job's result set.
  Also assembles plant-level KPIs (§5) from the collected results plus the canonical data.
- A structural failure (unreadable file, unresolved mandatory mapping, canonical write failure)
  raises out of the orchestrator and fails the whole job. Everything else is isolated per module.

## 5. KPI assembly

Deterministic pure functions in [`analytics/algorithms/kpis.py`](../analytics/algorithms/kpis.py),
ported from the existing PIC formulas (see `docs/algorithm_parity.md`):

- **Performance Ratio (%)** = `total_ac_kwh / (plant_dc_kwp × insolation_kwh_m2)` × 100
- **Specific Yield (kWh/kWp)** = `total_ac_kwh / plant_dc_kwp`
- **Insolation (kWh/m²)** = Σ(irradiance samples in W/m²) × Δt_h / 1000
- **Plant Availability (%)** = `(1 − Σ(impacted_dc_kw × fault_hours) / (plant_dc_kw × operating_hours)) × 100`
- **Estimated Energy Loss (kWh)** = Σ of every algorithm's `loss_energy_kwh`
- **Revenue Loss** = `total_loss_mwh × 1000 × tariff` — `null`/"not available" if no tariff
  was supplied (never silently defaulted, per PRD §7.10)

## 6. Configuration files

- [`analytics/config/aliases.yaml`](../analytics/config/aliases.yaml) — canonical field → list of vendor aliases
- [`analytics/config/thresholds.yaml`](../analytics/config/thresholds.yaml) — per-algorithm named thresholds, ported from PIC's env-overridable constants
- [`analytics/config/defaults.yaml`](../analytics/config/defaults.yaml) — plant-type default overrides (fixed-tilt vs tracker, monofacial vs bifacial), deployment limits

All three are loaded once at process start via Pydantic-validated loaders in
`analytics/common/config_loader.py`. Environment variables only override deployment limits
(upload size, job timeout); they never override algorithm thresholds — those are per-job
overrides validated against the YAML schema and recorded in `thresholds_used`.

## 7. Job and file lifecycle

Heavy analysis runs in an **in-process worker pool** (`MAX_CONCURRENT_JOBS`, default 4).
Multiple jobs can execute at once; each uses its own `{JOB_ROOT}/{job_id}/` directory.
When all workers are busy, new jobs wait in a shared queue (UI shows slot position; position 0 = running).

Job states (persisted in Postgres `jobs` table):

```text
uploaded → parsing → mapping → validating → normalizing → queued → running →
generating_charts → generating_report → completed | failed → cleaned_up
```

Filesystem layout per job (ephemeral, under a per-job UUID directory):

```text
{JOB_ROOT}/{job_id}/
  raw/input.csv(.gz)          # deleted after canonical standardization
  canonical/**/*.parquet      # deleted after algorithms finish reading (or at cleanup)
  results/results.json        # unified ResultObject list + KPIs
  reports/report.pdf, report.xlsx
  charts/*.png                # only if the user exports a chart
```

Cleanup triggers: `finally` block around the pipeline, explicit user download completion,
TTL expiry (report kept 1 hour), and a startup + periodic stale-job reclaim sweep that marks
`running` jobs older than `JOB_TIMEOUT_SEC` as `failed` and deletes their directories.

Postgres retains only: job status/timings/non-sensitive error summary rows, and saved
column-mapping templates (keyed by detected OEM signature). No raw or canonical time-series
data is ever written to Postgres or to logs.

## 8. No self-ping / keepalive

The system does not run any keepalive or self-ping cron against the deployed free-tier API.
Render flags such synthetic traffic as abnormal. The 2–3 second UI status poll during an
active job provides natural keep-warm traffic; the stale-job reclaim sweep guarantees no job
is left stuck if the instance sleeps mid-run. Cold starts are surfaced to the user as an
explicit "Starting analysis service…" state rather than hidden.
