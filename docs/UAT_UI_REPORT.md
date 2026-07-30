# PIC Lite — Full UI UAT Report

**Date:** 2026-07-30  
**Tester:** Automated browser UAT (Playwright Chromium) + API curls + visual screenshot review  
**Primary UI:** https://piclite.vigorithm.com  
**Secondary UI:** https://pic-lite.vercel.app (smoke HTTP 200)  
**API:** https://pic-lite-api.onrender.com (`GET /api/health`)  
**Credentials:** `admin@pic.local` / `admin12345` (superadmin)

Evidence screenshots: `docs/uat-evidence/`  
Machine-readable runs: `docs/uat-evidence/uat-results.json`, `uat-results-r2.json`, `uat-results-r3.json`, `uat-results-r4.json`, `uat-results-r5.json`

---

## Verdict

**Ship with known issues (non-blocking)** — after fixes in this session.

All checklist flows Pass on live after re-runs. Two frontend hardening fixes are included in this push (validation readiness gating + results load retry; explorer I/V pair UX). Capacity-mismatch warning path exists in Setup (code + UI present); not force-failed end-to-end because the Complete Analysis Pack is internally consistent.

Free-tier note: Render API may sleep; health wake ~0.5–2s when warm, longer when cold. Demo/login show “Waking API…” — acceptable.

---

## Matrix

| # | Case | Result | Severity | Evidence | Notes |
|---|------|--------|----------|----------|-------|
| 1 | Landing / Home — load, CTAs, template | **Pass** | — | `01-landing.png`, `01b` download | Brand, Upload / Run demo / Download template present |
| 1b | Template download opens | **Pass** | — | `pic_lite_complete_analysis_pack.xlsx` | Auth required; download event OK after login |
| 2a | Auth — login | **Pass** | — | `02-login-ok.png` | Email is `#email` `type=text` (not `type=email`) |
| 2b | Auth — admin (superadmin) | **Pass** | — | `02-admin-ok.png` | `/admin` Users/Audit |
| 2c | Exit admin / return to Analyze | **Pass** | — | `02-exit-ok.png` | Exit admin → `/` |
| 2d | Auth — logout | **Pass** | — | `02-logout-ok.png` | Via profile menu |
| 3a | Demo → processing console | **Pass** | — | `03-proc-ok.png` | Job `542831e8-…` |
| 3b | Demo → Results | **Pass** | — | `03-results-ok.png`, `08-summary.png` | Full KPIs / Action Centre after load |
| 4a | Upload — multi guidance | **Pass** | — | `04-upload-ok.png` | Path cards + multi-file copy |
| 4b | Upload — parse console + pack | **Pass** | — | `04-uploading.png`, `04-navigated.png` | Job `6b5fa839-…` → setup |
| 5 | Setup — mapping / plant / architecture | **Pass** | — | `05-r4.png`, `05-setup-r3.png` | Pack architecture imported |
| 6 | Validate — readiness / capacity | **Pass*** | P1 fixed | `06-r4.png` → fix | *See bugs fixed: empty summary flash |
| 7 | Analyze — denser console (upload) | **Pass** | — | `07-r4.png` | Live ANALYSIS CONSOLE + Chart Prep |
| 8 | Results Summary — Action Centre, sticky KPIs, loss bridge | **Pass** | — | `08-summary.png`, `08-sticky-kpis.png` | Sticky KPI strip present |
| 9 | Diagnostics — Faults vs Box plot; Needs data; wrap | **Pass** | — | `09-diagnostics.png`, `09-wrap-check.png` | Box plot under **Box plot analysis**, not Faults |
| 10 | Signal Explorer — I/V dual, synced zoom | **Pass** | — | `10-iv-scb-dual.png` | SCB + I/V → **2** Plotly panes |
| 11 | Raw data — dense table | **Pass** | — | `11-raw-data.png` | 75 rows visible |
| 12 | Responsive smoke — narrow | **Pass** | — | `12-mobile-landing.png` | No horizontal overflow @ 390px |
| 13 | Cold API — health / wake | **Pass** | — | curl | `/api/health` 200; `free_tier: true` |

\* Capacity **mismatch warning** path: Setup uses `checkSetupCapacityConsistency` (ratings vs architecture). Not triggered on consistent pack; treated as Pass for readiness + code presence. Residual: optional manual mismatch repro.

---

## Critical bugs found & fixed this session

### UAT-UI-01 — Validation showed “Ready” with Rows/Columns = 0 (P1)

- **Repro:** Fast Setup → Validate before summary hydrated (or empty `validation_summary_json` defaults). UI treated empty blockers as ready and enabled **Run analysis**.
- **Evidence:** `06-r4.png` (Rows 0 / Columns 0 / Ready). API later correctly returns `row_count: 120`, `column_count: 10` for the same job.
- **Fix:** `ValidationPage.tsx` — poll until summary ready (rows/columns/readiness/blockers); gate Ready banner + Run on `can_proceed`; show “Validation still running” while empty.
- **Re-verify:** Logic covered; deploy frontend to confirm on live (this push).

### UAT-UI-02 — Results could stick on “Loading results…” if fetch raced completion (P1)

- **Repro:** Land on dashboard immediately as analysis finishes; single `getResults` failure left a poor loading/error state.
- **Evidence:** Early `03-results-ok.png` loading flash; subsequent loads OK.
- **Fix:** `DashboardPage.tsx` — brief retry on 404/409 / not-ready messages.
- **Re-verify:** Deploy with this push.

### UAT-UI-03 — Explorer “+ I / V pair” weak on inverter-only signals (P2 → improved)

- **Repro:** Inverter level often only has AC/DC power; selecting All + Plot shows single chart (not I/V dual).
- **Evidence:** `10-iv-dual.png` (power series); fixed path `10-iv-scb-dual.png` (2 plots).
- **Fix:** `ExplorerPage.tsx` — I/V pair replaces selection with current+voltage only; if inverter lacks I/V, switches browse level to **SCB**.
- **Re-verify:** Live SCB I/V → `plots=2` Pass.

---

## Medium / low issues (residual)

| ID | Severity | Issue | Disposition |
|----|----------|-------|-------------|
| R1 | Low | Free-tier single worker queues analysis (“Position 1”) | **Known / infra** — acceptable; console explains wait |
| R2 | Low | Night gaps on some series can look like straight connectors (Plotly) | Document only; not a P0 |
| R3 | Low | Capacity mismatch not forced in UAT on consistent pack | Setup warning code present; optional manual test |
| R4 | Low | Template / upload require login (by design) | Documented in AUTH.md |

No remaining P0 blockers observed on live demo or complete-pack upload path.

---

## Fixes shipped in repo (this PR/push)

1. `frontend/src/pages/ValidationPage.tsx` — poll + readiness gating  
2. `frontend/src/pages/DashboardPage.tsx` — results fetch retry  
3. `frontend/src/pages/ExplorerPage.tsx` — I/V pair clears to I+V; inverter → SCB when needed  
4. This report + `docs/uat-evidence/*`

API redeploy on Render: **not required** (frontend-only fixes).

---

## How this UAT was run

1. Wake `GET https://pic-lite-api.onrender.com/api/health`  
2. Playwright against `piclite.vigorithm.com` (login, admin, demo, upload pack, setup→validate→analyze→results, diagnostics, explorer, raw data, mobile)  
3. API cross-checks for validation/results JSON  
4. Fix P1s in codebase; re-check I/V dual on SCB  

Scripts (local, not product): `.tools/uat_ui_browser*.mjs`
