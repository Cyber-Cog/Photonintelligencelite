# PIC Lite — Final UAT (customer-ready pass)

**Date:** 2026-07-20 (re-verified after Will-run / Needs-input honesty fix)
**Environment:** Local, no Docker. Bundled PostgreSQL 16, FastAPI (uvicorn :8000), Vite UI (:5173).
**Restart:** `stop.bat` → `start.bat` (required after backend changes so the live API picks up the fix).

## Bug fixed this pass: Clipping “Will run” → “Needs input”

**Root cause:** Validation and the orchestrator treated *schema column names* as available telemetry. Canonical parquet always includes empty columns (`dc_power_kw`, `dc_current_a`, …). That made Validation say **Will run** for modules that later correctly returned **Needs input** / unavailable.

**Fix:**
- `CanonicalDataAccess.populated_columns()` — fields with ≥1 non-null value only
- Validation readiness and orchestrator both use populated columns (not full schema)

**Expected on user’s 3 CSVs** (Weather + Inverter SCADA + Plant SCADA):

| Module | Validation | Results |
|--------|------------|---------|
| KPIs | Will run | OK |
| Clipping by Power | Will run | OK (clip energy computed) |
| Efficiency / Box plot | Blocked | Needs input (no real inverter DC) |
| Clipping by Current / DS / Module damage / String outlier | Blocked | Needs input (no SCB I/V) |

## Product UAT (`.tools/uat_product.py`) — **12/12 PASS**

| # | Step | Result |
|---|------|--------|
| 1 | Multi-file upload (3 CSVs) | PASS |
| 2 | Validation readiness honest (clipping/KPIs only) | PASS |
| 3 | Analysis completed | PASS |
| 4 | Clipping power OK **matches** Will run | PASS |
| 5 | KPIs populated | PASS |
| 6 | SCB modules unavailable (honest) | PASS |
| 7 | Raw data preview | PASS |
| 8–10 | Analytics Lab equipment / signals / plot | PASS |
| 11 | Architecture view | PASS |
| 12 | PDF + Excel reports | PASS |

## Broader harness (`.tools/uat_final.py`)

Demo + synthetic + recovery flows remain covered. Re-run after restart if the live stack was started before this fix.

## How to verify in the UI

1. `stop.bat` then `start.bat`
2. Upload Weather + Inverter + Plant CSVs together
3. Map: AC power, POA, inverter id; **ignore** PlantDC_MW / PlantAC_MW
4. Setup plant + architecture → Validation: clipping power **Will run**, SCB modules **Blocked**
5. Run analysis → Results: clipping power **OK** (not Needs input)
6. Raw data / Architecture / Analytics Lab should load equipment and plot AC + POA

## Intentional algorithm gaps

See `docs/algorithm_parity.md` (clipping-by-current Lite v1, DS MPPT deferred, availability proxy).

## Complete Analysis Pack (official format)

**Doc:** `docs/COMPLETE_DATA_FORMAT.md`  
**Downloads:** `GET /api/templates/complete-analysis` (Excel) · `GET /api/templates/complete-analysis.zip` (CSV + architecture)  
**UI:** Landing + Upload — “Download complete analysis template”

**Necessary for all faults:** timestamp, equipment IDs, AC power (kW), DC current (A), DC voltage (V), POA/GHI (W/m²), plant architecture, inverter ratings.

Multi-file / fuzzy OEM upload remains supported; the pack is the accurate methodical path. Sample rows in the template auto-map; upload the Excel `scada` sheet (or ZIP CSV), then architecture in Setup.
