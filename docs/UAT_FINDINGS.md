# PIC Lite UAT Findings (2026-07-18)

Live checks against `localhost:8000` + `localhost:5173` (API + Vite). Browser MCP was unavailable; flows exercised via HTTP API and unit tests. API was restarted mid-session so code changes were loaded.

## Checklist results (post-fix)

| # | Check | Result | Notes |
|---|--------|--------|-------|
| 1 | Health `/api/health` | **PASS** | `{"status":"ok","free_tier":false}` |
| 2 | Try Demo → dashboard | **PASS** | Completes; `box_plot` now `ok`; clipping modules explicitly `unavailable` |
| 3 | Upload CSV (demo sample) | **PASS** | State `mapping`, auto-map OK |
| 4 | Upload tidy Excel | **PASS** | Headers preserved |
| 5 | Upload wide multi-header inverter Excel | **PASS** | Reshaped to long CSV with INV-01/02 + metrics |
| 6 | Mapping UI (ambiguous columns) | **PASS** (API) | Unknown headers → `requires_manual_mapping=true` |
| 7 | Plant config → validate → ack → analyze | **PASS** | Wide Excel path completed with KPIs |
| 8 | PDF + Excel report download | **PASS** | Both 200 after BackgroundTask cleanup fix |
| 9 | Light/dark + navigation | **PARTIAL** | Frontend 200; visual toggle not browser-verified |
| 10 | Bad file type | **PASS** | `.txt` → 400 with accepted formats message |

---

## Issues

### UAT-01 — Try Demo / job runner: `ResolvedMapping` rejected `timestamp_column` (BLOCKER, fixed earlier)

- **Severity:** Blocker
- **Steps:** Try Demo → job failed while running
- **Evidence:** `.tools/api.err.log` — unexpected keyword `timestamp_column`
- **Root cause:** Whole `mapping_json` passed into `ResolvedMapping(**mapping_cfg)`
- **Fix status:** Already patched (explicit field extraction). Confirmed completed demos.

### UAT-02 — Box plot crashes on pandas MultiIndex Series (HIGH) — FIXED

- **Severity:** High
- **Steps:** Demo completes but Box Plot module `error`
- **Evidence:** `TypeError: 'float' object is not a mapping` at `box_plot.py`; unit test failed
- **Root cause:** `groupby.apply(dict)` expands to MultiIndex float Series
- **Fix:** Explicit per-inverter `_box_stats` loop in `analytics/algorithms/box_plot.py`

### UAT-03 — Wide multi-header “INVERTER REPORT” Excel not reshaped (BLOCKER) — FIXED

- **Severity:** Blocker for real SCADA Excel
- **Steps:** Upload wide inverter `.xlsx` → columns `INVERTER REPORT` / `Unnamed: N`
- **Root cause:** Naive sheet dump in `excel_convert.py`
- **Fix:** Detect header block, forward-fill merged groups, melt to long CSV; derive `DC Power (kW)` from V×I when missing

### UAT-04 — Timestamp / power aliases incomplete (MEDIUM) — FIXED

- **Severity:** Medium
- **Fix:** Added `date and time`, `power (kw)`, `power kw` to `aliases.yaml`

### UAT-05 — Clipping unavailable on demo (LOW / expected)

- **Severity:** Low
- **Action:** Leave as explicit unavailable (irradiance/prerequisite alignment)

### UAT-06 — Second report download 500 after cleanup (MEDIUM) — FIXED

- **Severity:** Medium
- **Steps:** Download PDF then Excel (or reverse) — second file 500
- **Root cause:** `cleanup_after_download` deleted files before `FileResponse` streamed
- **Fix:** `BackgroundTask` cleanup in `backend/app/routers/reports.py`

### UAT-07 — Light/dark toggle visual check (LOW) — OPEN

- Browser automation unavailable in this session; frontend serves OK. Manual glance recommended.

### UAT-08 — Validation blockers only offered “Start over” (CRITICAL UX) — FIXED

- **Severity:** Critical UX (plant-owner recovery)
- **Steps:** Upload messy Excel (title row → `Unnamed: 1` as timestamp) → Validate → `invalid_datetime_format` on ~all rows → only **Start over**
- **Evidence:** Validation page had no remap / retry / partial-proceed path; failed jobs forced re-upload
- **Root cause:**
  1. Excel title/multi-header dumps became CSV headers (`Unnamed: N`); Date And Time lost
  2. Timestamp parse used bare `pd.to_datetime` (weak vs PIC formats / Excel serials)
  3. UI treated blockers as terminal with re-upload as sole action
- **Fix:**
  - **Recovery UX:** Validation offers **Fix column mapping** (Setup, upload kept), **Retry validation**, and **Proceed with warnings** when ≥80% timestamps parse OK (drops bad rows). Start over is secondary.
  - **Setup reload:** `GET /api/jobs/{id}/setup-context` restores mapping without re-upload; garbage/`Unnamed` headers never auto-map as timestamp; Timestamp always confirmable/editable
  - **Parsing:** `analytics/preprocessing/timestamps.py` ports PIC `parse_timestamp` formats + Excel serials + dayfirst; used by validation + standardize
  - **Excel:** `try_promote_header_row` skips title banners so `Date And Time` becomes the header; blank headers sanitized away from silent `Unnamed`
  - **Messaging:** Blockers show timestamp column, sample raw values, and remediation (“remap to Date And Time”)
- **Threshold choice:** `PROCEED_WITH_DROPS_MIN_OK_RATIO = 0.80` — plant owners prefer partial analysis over restart when most rows are good; below 80% remap is required
- **Tests:** `tests/test_timestamp_recovery.py`, title-row case in `tests/test_excel_wide_inverter.py`

---

## Artifacts

- Fixture: `tests/fixtures/wide_inverter_report.xlsx`
- Tests: `tests/test_excel_wide_inverter.py` (reshape + convert + tidy non-false-positive + title-row promote)
- Tests: `tests/test_timestamp_recovery.py` (parse formats, Unnamed remediation, proceed-with-drops)
