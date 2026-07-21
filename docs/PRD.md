# Photon Intelligence Center Lite — Product Requirements Document

> **Authoritative status:** This document is the supplied product specification for PIC Lite,
> annotated with the locked build decisions from planning. Where the original text is superseded
> by a locked decision, the section is marked **`[SUPERSEDED — see Locked Decisions]`** and the
> original text is retained struck through in intent (kept verbatim below it) for traceability.
> See [`docs/architecture_decisions.md`](architecture_decisions.md) for full rationale and
> [`docs/algorithm_parity.md`](algorithm_parity.md) for algorithm-level porting notes.

## 0. Locked Decisions (supersede conflicting PRD text)

| Topic | Locked decision |
|---|---|
| Algorithm source | Port **logic only** from the existing PIC codebase (`solar_analytics_codex_bundle`). No UI, auth, routers, sessions, or persistence patterns are reused. |
| Deployment | Local Docker Compose (dev parity) + free-tier cloud: **Vercel** (frontend), **Render** (FastAPI API, Docker), **Neon** (Postgres, metadata only). |
| Job queue | **In-process worker pool** (`MAX_CONCURRENT_JOBS`, default 4) — multiple analyses run concurrently; no Redis/Celery. **Postgres advisory lock / single-job mutex is retired.** Redis and Celery remain out of MVP scope — superseded wherever the original PRD recommends them (§13, §16, §25). |
| Data window | 1 day (lower bound) → 1 month (upper bound, hard UX/perf target). |
| Free-tier vs local scope split | Free tier targets **1 month of 15-minute data**. **1 month of dense 1-minute multi-inverter data is a local-Docker-only target**, not a free-tier promise (Render free tier: 512 MB RAM, ephemeral disk). |
| Upload format | `.csv` and `.csv.gz`. Browser may gzip plain CSV client-side; already-compressed files pass through. Uploads are streamed and chunk-parsed — never loaded fully into memory. |
| External irradiance fallback | **Out of MVP.** Deferred to Phase 6 / post-MVP. §7.6 and §11 external-irradiance provisions are deferred; the `analytics/external/` module exists as an isolated, disabled placeholder only. |
| OEM alias priority | Seeded from the existing PIC mapping dictionaries plus common vendor aliases (Sungrow, Huawei, ABB/FIMER, SMA, TBEA naming conventions where documented). Refined once real SCADA export samples are supplied. |
| File size cap | `MAX_COMPRESSED_UPLOAD_MB` / `MAX_DECOMPRESSED_UPLOAD_MB` — 100 MB / 250 MB local; 25 MB / 60 MB on free Render (env-overridable). Supersedes the flat "100–200 MB" figure in §7.2/§8.1/§13/§24 wherever it conflicts. |
| Job timeout | `JOB_TIMEOUT_SEC` is **measured**, not guessed: set to 3× the measured full-pipeline wall-clock time for the bundled demo dataset on the deployed free-tier instance, with a documented upper safety cap. Supersedes the flat "300s" default suggested during planning. |
| Keepalive | **No self-ping / keepalive cron.** Superseded wherever background "ping to avoid cold start" ideas might otherwise be implied — this is explicitly rejected because Render flags such traffic as abnormal. The UI's 2–3s status poll during active jobs, plus stale-job reclaim for orphaned jobs, is the whole mechanism. |

---

## 1. Product Vision

Photon Intelligence Center Lite is a professional web-based analytics platform for utility-scale solar PV plants.

Its purpose is to let an engineer upload a SCADA CSV file, automatically detect the file structure, validate the data, run fault and loss analytics using proprietary algorithms, visualize the findings through an interactive dashboard, and generate professional downloadable reports.

The product should feel like enterprise engineering software used by utility-scale solar organizations such as Tata Power, NTPC, Adani Green, Vikram Solar, ReNew, Brookfield, ENGIE, and EDF.

This is not a chatbot, not a generic BI tool, and not a data warehouse. It is a focused solar analytics application.

## 2. Product Principles

The system must follow these principles at all times:

- Minimal user effort.
- Very fast workflow.
- Professional appearance.
- No unnecessary navigation.
- No permanent storage of plant operational data.
- Automatic detection wherever possible.
- Manual intervention only when required.
- Clear errors instead of failures.
- One-click reporting.
- Dashboard-first output.
- Safe cleanup after processing.
- **Deterministic and explainable analytics** — given the same input file and mapping, every algorithm must produce identical output every time. Every reported loss or fault must be traceable back to the rows/columns that produced it. Engineers reviewing a report will not trust a number they can't reconstruct.

The user experience should feel simple, controlled, and reliable.

## 3. MVP Objective

The MVP must support a complete single-job analysis lifecycle:

1. User opens the platform.
2. User uploads a SCADA CSV.
3. The system identifies the file layout.
4. The system requests only missing mandatory inputs.
5. The system validates the data.
6. The system normalizes sampling interval and timezone.
7. The system runs the analysis engine.
8. The system renders dashboards and results.
9. The system generates PDF and Excel reports.
10. The user downloads the report.
11. The system deletes temporary operational data.

Only one analysis job should run at a time in the MVP.

### 3.1 Key Assumptions & Open Questions (resolved — see §0 Locked Decisions)

- Assumes CSV files are single-plant, single-time-range exports (not multi-plant portfolios).
- Assumes a maximum practical file size in the tens of MB, not GB-scale (see §13; concrete caps locked in §0).
- Assumes deployment target is cloud-hosted (locked: Vercel + Render + Neon, see §0).
- Assumes IST is the dominant but not exclusive timezone; DST is not a concern for India but may matter if the tool is ever used outside India.
- Assumes "proprietary algorithms" referenced in the vision are being supplied separately by the existing PIC codebase — this PRD does not define their internal math beyond what is ported (see `docs/algorithm_parity.md`).

## 4. In Scope

- CSV upload (`.csv`, `.csv.gz`)
- File validation
- Automatic column detection
- Manual column mapping only when needed
- Minimal plant detail entry
- Analysis job creation
- Single-job execution (in-process, Postgres-locked)
- Sampling interval and timezone normalization
- Fault and loss calculation
- Interactive dashboard
- PDF report generation
- Excel report generation
- Temporary file storage
- Automatic cleanup after completion
- Basic logging and error tracking
- Bundled demo/sample CSV for the "Try Demo" landing page CTA

## 5. Out of Scope

- Multi-user collaboration
- Authentication and role management
- SCADA API connectors
- Live monitoring
- Portfolio management
- Historical plant storage
- Cloud file storage for operational data
- Machine learning training workflows
- Predictive maintenance
- Push notifications
- Multi-language support
- Mobile app
- Permanent plant history
- Real-time control actions
- External irradiance data as a primary source or as an MVP fallback (deferred entirely — see §0)
- Custom/white-label report branding (deferred to a later phase — see §21)
- ~~Redis/Celery job queue~~ **`[SUPERSEDED — see Locked Decisions]`** — never in MVP scope; in-process worker only.

## 6. Primary User

The primary user is a solar performance engineer, O&M analyst, data analyst, or technical manager who wants to assess plant health quickly from SCADA exports.

The user expects: minimal setup, low manual mapping effort, accurate analytics, clean charts, exportable reports, no technical complexity.

## 7. End-to-End User Workflow

### 7.1 Landing and Entry

The user opens the application and immediately sees the purpose of the product.

The landing page must include: product name, concise value proposition, primary CTA (Analyze Plant), secondary CTA (View Sample Report or Try Demo CSV), no clutter.

The user should not need to read documentation before starting.

The demo CSV should be a real (or realistically synthetic) file that exercises every algorithm at least once, so "Try Demo" is a genuine product tour, not a placeholder. (Built via `tests/fixtures/synthetic_generator.py`, reused for both product demo and algorithm test fixtures.)

### 7.2 Upload Stage

Requirements: accept CSV (and CSV.GZ) only, reject unsupported formats clearly, display file size limits, show upload progress, prevent accidental double submission.

`[SUPERSEDED — see Locked Decisions]` ~~Set an initial file size cap around 100–200 MB.~~ Locked caps: see §0 (separate compressed/decompressed caps, environment-tunable, different for local vs free-tier).

The app should immediately create an analysis session when the file is accepted.

### 7.3 Minimal Plant Metadata Stage

Required fields: Plant Name, Plant AC Capacity (MW), Plant DC Capacity (MWp) — required separately from AC capacity for clipping-loss and DC/AC-ratio algorithms, Module Rating (Wp), Inverter Capacity (per unit), Module Technology, Monofacial/Bifacial, Timezone.

Optional fields (progressively disclosed only when relevant algorithms are selected):

- Strings per SCB / Inverter — needed for disconnected-string and string-outlier detection to have a baseline.
- Applicable energy tariff (₹/kWh) or PPA rate — required to compute the "Revenue Loss" KPI (§7.10); without this the KPI is shown as "not available."
- Contracted/guaranteed Performance Ratio benchmark — used to set PR-deviation severity thresholds; falls back to a generic industry default if not provided.
- PVsyst or design-stage expected generation file, if available — enables actual-vs-expected comparison. **Not implemented in MVP** (no UI/parsing for this file type yet); field is captured but unused until Phase 6.

### 7.4 Automatic Structure Detection

The detection layer identifies likely columns for: timestamp, inverter power, inverter voltage, inverter current, string current, SCB identifier, inverter identifier, POA irradiance, GHI, module temperature, ambient temperature, energy, and any additional fields used by the algorithms.

The system uses an alias dictionary and confidence scoring.

Confidence bands:

- ≥ 90% confidence — map automatically, no user interaction.
- 60–89% confidence — proceed automatically but show a dismissible one-click confirmation ("We mapped 'P(kW)' → Power — correct?").
- < 60% confidence, or no candidate found — open the manual mapping wizard for that column only.

Rules: if confidence is high, continue automatically; if ambiguous, open the mapping wizard; if unmappable, the user must be able to assign it once; save only the mapping template, not the CSV data.

### 7.5 Manual Mapping Wizard

The user is only asked to map ambiguous columns, assigning each to an approved semantic type: timestamp, power, current, voltage, irradiance, temperature, energy, inverter, string, SCB, ignore.

This step must be minimal. The goal is to handle heterogeneous SCADA exports without hardcoding every vendor layout.

OEM priority for the alias dictionary at launch: seeded from PIC's existing equipment-ID/signal conventions plus common industry aliases for Sungrow, Huawei, ABB/FIMER, SMA, and TBEA naming patterns; refined against real export samples as they are supplied (locked in §0).

### 7.6 Validation Stage

Validation checks include: missing timestamps, duplicate timestamps, unsorted timestamps, invalid datetime format, timezone mismatch, negative values where impossible, null values in required columns, missing power data, missing irradiance data if required for an algorithm, missing inverter or string identifiers where needed, abnormal sampling intervals, corrupted rows, non-numeric values in numeric columns, file truncation or unreadable content.

**Sampling interval normalization.** The pipeline detects the dominant interval and resamples (or explicitly flags mixed/irregular intervals as a blocking issue) so downstream PR/CUF/loss calculations are computed on a consistent basis. Sits between validation and analysis (§7.8, §9).

**Missing irradiance fallback.** `[SUPERSEDED — see Locked Decisions]` ~~Offer an opt-in fetch of external GHI from NASA POWER / Global Solar Atlas.~~ **Deferred entirely out of MVP.** If POA/GHI columns are absent, irradiance-dependent algorithms are marked `unavailable` with a clear reason rather than falling back to an external source. The `analytics/external/` module is scaffolded and disabled by a config flag for Phase 6.

Validation output must be human-readable: warnings with severity, likely cause, and whether the issue blocks analysis or only reduces accuracy. The application must never crash during validation.

### 7.7 Job Creation and Processing

Job states: `uploaded → parsing → mapping → validating → normalizing → queued → running → generating_charts → generating_report → completed | failed → cleaned_up`.

Only one job runs at a time. If a second job is submitted while one is running, the system queues it and shows a clear message including an estimated wait; the system must not freeze or crash.

### 7.8 Analysis Execution

The analysis engine receives a standardized, resampled canonical dataset; plant configuration (including DC capacity, tariff, PR benchmark where provided); resolved column mapping; algorithm selection configuration; configurable per-algorithm thresholds.

The analysis engine processes data independently of the UI via an `AnalysisContext` object and an algorithm registry driven by a central orchestrator (see `docs/architecture_decisions.md`).

Every algorithm follows a consistent pipeline: input → validation → preprocessing → processing → loss calculation → chart generation → recommendation generation → result object.

The platform supports at minimum: inverter efficiency loss, box plot analysis, module damage, bypass diode failure, disconnected strings, inverter clipping by power, inverter clipping by current, string outlier detection.

Future algorithms are pluggable via the registry without rewriting the core workflow.

### 7.9 Result Assembly

Each result object includes: title, summary, severity/confidence, affected equipment, calculated loss, key metrics, tables, charts, recommendations, execution time, downloadable artifacts. Standardized so the UI renders every fault module consistently (see `ResultObject` contract in `docs/architecture_decisions.md`).

### 7.10 Dashboard Display

Overview KPIs: Plant Availability, Performance Ratio, Specific Yield, Estimated Energy Loss, Revenue Loss (requires tariff input; shown as "not available" if no tariff was provided rather than defaulting silently), Fault Count.

Charts: daily yield trend, loss distribution, heatmaps, monthly trend chart, box plots, inverter-wise comparison, string-wise comparison, fault timeline.

Fault Summary Cards: disconnected strings, module damage, bypass diode failure, inverter efficiency loss, clipping loss, current clipping, box plot outliers.

Downloads: PDF report, Excel report, raw result tables if needed, individual chart export (PNG/SVG) for reuse in other decks or reports.

**Job status delivery.** Polling every 2–3 seconds during active processing (locked; SSE/WebSocket rejected as unnecessary for a single-job MVP — see §0).

### 7.11 Reporting

Report outputs: PDF, Excel. Each report includes: executive summary, plant information, data source details, validation notes (including whether external irradiance fallback was used — always "not used" in MVP since the feature is deferred), detected issues, loss summary, charts, recommendations, algorithm notes (including any non-default thresholds used), appendix/supporting tables.

### 7.12 Download and Cleanup

After the report is generated and downloaded, temporary operational data is deleted automatically: uploaded CSV, intermediate processing files, generated charts, temporary report artifacts, cached transformed data. (No externally fetched irradiance data exists in MVP since the fallback is deferred.)

Only minimal non-operational metadata remains: logs, job records, saved column mapping templates. No plant time-series data is permanently stored.

## 8. Functional Requirements

### 8.1 Upload
Accept CSV/CSV.GZ only; show progress; reject invalid format; reject oversized files per locked caps (§0); return clear error messages.

### 8.2 Column Detection
Alias mapping; confidence thresholds (§7.4); vendor-layout support; manual input only when needed.

### 8.3 Validation
Structural integrity; data completeness; timestamp logic; required fields; detect and normalize sampling interval; surface warnings and blockers separately.

### 8.4 Analytics
Independent algorithms via registry; loss calculations; fault summaries; charts and tables; per-algorithm threshold overrides.

### 8.5 Dashboard
KPIs; interactive charts; fault cards; report actions; responsive rendering; per-chart export.

### 8.6 Reporting
Professional PDF; Excel; executive summary and evidence; download after completion.

### 8.7 Cleanup
Automatic temp file deletion; operational data removed after job lifecycle; minimal metadata preserved.

## 9. Algorithm Framework

```text
Input
↓
Validation
↓
Preprocessing (includes interval/timezone normalization)
↓
Processing
↓
Loss Calculation
↓
Chart Generation
↓
Recommendations
↓
Result Object
```

A result object includes at least: title, summary, loss value, severity, affected equipment, charts, tables, recommendations, execution time, thresholds used (if non-default).

Algorithms must not depend on frontend code and must not call each other directly unless explicitly coordinated by the central analysis orchestrator.

**Configurable thresholds.** Algorithms like clipping detection, string-outlier detection, and box-plot analysis depend on sensitivity thresholds. These are defined as named, overridable parameters in `analytics/config/thresholds.yaml`, with defaults ported from the existing PIC codebase's env-overridable constants (documented per-algorithm in `docs/algorithm_parity.md`).

## 10. Column Detection Logic

Semantic alias dictionary examples: Power/Pac/AC Power/Output Power/P/P(kW) → power; Timestamp/Date/Datetime/DateTime/Timestamp UTC → timestamp; Current/Idc/I/Current(A) → current; Voltage/Vdc/V/Voltage(V) → voltage; POA/Irradiance/POA Irradiance → poa; GHI/Global Horizontal Irradiance → ghi.

Behavior: map automatically when confidence is high; open the mapping wizard when ambiguous; save mapping templates for future reuse, keyed by detected OEM/file signature where possible; never block the user unnecessarily.

## 11. Data Handling and Storage

Allowed persistent storage: job records, logs, saved mapping templates, system configuration.

Disallowed persistent storage: raw CSV content, plant time-series data, SCADA history, operational records, generated temporary charts after completion, report artifacts after download, cached transformed data. (No externally fetched irradiance data in MVP — feature deferred.)

The platform behaves like a secure transient analysis service, not a data lake.

The no-retention policy is likely to align well with data-minimization principles under India's DPDP Act, 2023 — not legal advice; confirm with legal/compliance if this is a selling point.

## 12. Error Handling

Every error includes: what happened, why it happened, whether it blocks analysis, how to fix it.

Handleable errors: empty CSV, unsupported format, unknown encoding, malformed timestamps, missing required columns, excessive file size, memory pressure, algorithm failure, chart generation failure, report generation failure. (External irradiance fetch failure is not applicable in MVP — feature deferred.)

Transient failures (a single algorithm erroring out) do not fail the whole job — isolate the failure to that module, mark it `unavailable`, and continue. Reserve full job failure for structural problems (unparseable file, missing mandatory mapping).

The error UI must be calm, clear, and actionable.

## 13. Performance Requirements

`[SUPERSEDED — see Locked Decisions]` The system is designed for smooth analysis of one job at a time using an **in-process worker with a Postgres advisory lock**, not Celery/RQ + Redis as originally suggested. Upload starts processing quickly; the UI remains responsive during backend computation; heavy computation does not block the frontend event loop (runs as an async background task); large in-memory copies are minimized via chunked/streamed parsing (pandas `chunksize` / Polars lazy scan); charts render without freezing the page; the user always sees a progress state.

For files at the upper end of the size cap, chunked/streaming CSV parsing is used rather than loading the full file into memory at once.

The MVP limits concurrent analyses to one active job.

## 14. Security Requirements

Accept only CSV/CSV.GZ files; validate file type and extension; validate file size (compressed and decompressed); sanitize filenames; never execute uploaded content; store files only temporarily; delete files automatically after completion; prevent unsafe parsing or injection behavior; avoid exposing raw file content unnecessarily; guard against decompression bombs (ratio/row/column caps). (No third-party irradiance API calls in MVP — feature deferred, so the "coordinates only, never raw SCADA" rule applies only once that feature ships.)

## 15. Logging and Observability

Log: upload received, validation start, validation result, sampling interval detected/normalization applied, column mapping confidence scores per column, job queued, job started, algorithm execution start/end, report generation start/end, cleanup start/end, failures with stack traces, execution time per algorithm, total job duration.

Logs never expose raw operational data — no raw rows, plant time-series values, or complete filenames.

## 16. System Architecture

`[SUPERSEDED — see Locked Decisions]` ~~Celery/RQ + Redis for job queuing~~ **In-process async worker + Postgres advisory lock (no Redis, no Celery).**

Frontend: React, Vite, TypeScript, Tailwind CSS, Plotly.

Backend: FastAPI, Python, analysis worker, analysis orchestrator.

Storage: PostgreSQL for metadata only; temporary filesystem storage for processing artifacts (ephemeral, ~`/tmp`).

Analysis Layer: standalone Python analytics package; modular algorithm registry; shared preprocessing/validation/report/resampling utilities; optional external data client (irradiance fallback), isolated and disabled by a config flag for Phase 6.

The analytics engine is reusable outside the web app if needed later.

## 17. Folder Structure

```text
frontend/

backend/
  api/
  services/
  models/
  database/
  workers/
  utils/

analytics/
  core/
  common/
  algorithms/
  charts/
  reports/
  validation/
  preprocessing/
  external/          # irradiance fallback client, isolated & flag-gated (disabled in MVP)
  config/

uploads/
outputs/
templates/
tests/
docs/
```

Rules: frontend must not contain business logic; API routes stay thin; algorithms remain isolated; report generation lives in the analytics layer; utilities are reusable; external data clients are isolated and independently disableable.

## 18. Coding Standards

Python: type hints, Pydantic models, Black formatting, Ruff linting, Pytest coverage.

Frontend: strict TypeScript, reusable components, functional components, no duplicated UI logic, no inline styling unless necessary.

Backend: business logic separated from API routes; service layer for orchestration; clear boundaries between validation, processing, and reporting.

## 19. UI and Visual Design

Enterprise engineering software feel: clean, minimal, professional, structured, data-rich; no cartoon styling, no excessive gradients, no decorative clutter.

Visual inspiration: Power BI, Grafana, Tableau, SCADA dashboards.

Strong information hierarchy; readable typography; consistent spacing; card-based KPI layout; clear tables; interactive charts; restrained visual effects; dark mode and light mode support.

## 20. Report Design Standard

Suggested order: title page/header, executive summary, plant details, input quality and validation results (including any external-data fallback disclosure — always "not used" in MVP), key findings, fault-wise analysis, loss tables, charts, recommendations, technical appendix (mapping used, thresholds applied, sampling interval detected).

Report white-labeling/branding is deferred to Phase 2 (post-MVP) — see §21.

## 21. Development Roadmap

**Phase 0 — Requirements Confirmation** — resolved via `docs/architecture_decisions.md`: OEM formats seeded from PIC + common vendors; file size caps locked (§0); deployment target locked (cloud, free-tier); demo dataset sourced from `tests/fixtures/synthetic_generator.py`.

**Phase 1** — project setup, folder structure, frontend shell, backend shell, database setup, Docker setup, in-process job runner setup (no external queue broker).

**Phase 2** — CSV upload, job creation, validation, sampling interval/timezone normalization, column detection, mapping wizard.

**Phase 3** — analysis engine integration, one algorithm at a time, unified result object, chart generation, configurable thresholds per algorithm.

**Phase 4** — dashboard, job status polling, report generation, download flow, cleanup flow.

**Phase 5** — testing (including a multi-OEM synthetic SCADA test corpus), performance optimization, error handling hardening, deployment, documentation.

**Phase 6 (Post-MVP)** — external irradiance fallback, report white-labeling/branding, authentication and multi-user support, API for programmatic job submission.

## 22. Acceptance Criteria

The MVP is complete only when all of the following are true:

- A user can open the website and immediately understand what it does.
- A user can upload a valid SCADA CSV (or CSV.GZ).
- The system can detect the file structure automatically in most cases.
- The system can request only truly necessary missing inputs.
- The system can validate the data without crashing.
- The system correctly detects and normalizes mixed or non-standard sampling intervals.
- The analysis engine can run successfully on supported files.
- The dashboard can display results clearly and interactively, including a Revenue Loss KPI when tariff data is supplied.
- The user can download PDF and Excel reports.
- Uploaded operational data is removed automatically after the job lifecycle ends.
- The entire workflow works without manual code intervention.
- The application remains stable even if the file layout differs between SCADA exports.
- The product feels polished enough to demonstrate professionally to solar asset owners and O&M teams.
- (Locked addition) One month of 15-minute-resolution data completes on the deployed free tier; one month of dense 1-minute multi-inverter data completes locally via Docker — these are validated as two distinct acceptance targets, not one.

## 23. Definition of Done

The product is done when an engineer can: open the platform, upload a supported CSV, provide only minimal required plant details, let the system auto-detect columns and normalize sampling interval, review validated results, inspect the dashboard, download reports, and trust that temporary operational data is cleaned up afterward.

The final outcome must feel like a real commercial solar analytics product, not a prototype.

## 24. Risks & Open Questions (resolved — see §0)

- Deployment target — **locked**: cloud (Vercel + Render + Neon), not on-prem/air-gapped.
- Priority OEM SCADA formats — **locked**: seed from PIC + common vendors; refine on real samples.
- File size ceiling — **locked**: see §0 caps table.
- Ownership of algorithm thresholds — **locked**: ported from PIC's existing env-overridable defaults; documented per-algorithm in `docs/algorithm_parity.md`.
- Multi-day/multi-month scope — **locked**: 1 day → 1 month.
- External irradiance fallback in MVP — **locked**: excluded entirely from MVP, deferred to Phase 6.

## 25. Recommended Tech Stack Additions

`[SUPERSEDED — see Locked Decisions]` The table below is retained for historical context; entries struck through are explicitly rejected for MVP.

| Concern | Original recommendation | MVP status |
|---|---|---|
| Job queue | ~~Celery or RQ + Redis~~ | **Rejected** — in-process worker + Postgres advisory lock |
| Job status delivery | Polling (2–3s) or SSE | **Locked**: polling only |
| Large CSV parsing | Chunked pandas or Polars lazy API | **Adopted** |
| PDF generation | WeasyPrint or ReportLab | **Adopted**: ReportLab (matches existing PIC usage) |
| Excel generation | openpyxl | **Adopted** |
| External irradiance fallback | NASA POWER API or Global Solar Atlas | **Deferred** — not built in MVP |

None of the adopted entries are exclusive commitments beyond MVP — they were chosen to keep the stack consistent and avoid unnecessary infrastructure for a single-job application.
