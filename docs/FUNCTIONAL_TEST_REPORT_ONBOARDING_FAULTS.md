# Functional Test Report: Onboarding + Fault Detection

**Date:** 2026-07-30  
**Scope:** Analytics / backend accuracy only (no UI). Local pytest + fixtures.  
**Reference logics:** `C:\Users\ayush.r\Desktop\PIC\solar_analytics_codex_bundle` + PIC Lite `docs/algorithm_parity.md`, `docs/RCA_COLUMN_DETECTION.md`, `docs/COMPLETE_DATA_FORMAT.md`.

---

## 1. Scope

| Area | Covered |
|------|---------|
| Onboarding | Upload headers → alias map → equipment ID / `device_type` → architecture → validation readiness |
| Equipment tree | Inverters, SMB/SCB, strings; parent linking; architecture `inverter_id` backfill |
| Column mapping | AC/DC power, DC current/voltage (incl. SMB variants), irradiance, temps; confidence bands; no silent suggestion drops |
| Excel | Wide SMB sheets, multi-sheet probe, long tidy CSV |
| Fault algorithms | Disconnected strings, module damage / bypass, string outlier, clipping power/current, inverter efficiency, box plot |
| Explicitly out of scope | Frontend/UI, Lovable UI work, live-site-only checks |

**Suite run (this report):** `206 passed, 0 failed` (full `tests/`).

**New matrix tests:** 73 collected in `tests/test_functional_onboarding_matrix.py` + `tests/test_functional_fault_matrix.py` (all passing).

---

## 2. Inventory summary

### Onboarding path
`POST /api/upload` → Excel/CSV parse → `suggest_mapping` / `aliases.yaml` → `POST /api/mapping` + plant/architecture → `parse_validate_standardize` → `device_type` + hierarchy + architecture backfill → module readiness via `evaluate_prerequisites`.

Key modules: `backend/app/services/mapping_service.py`, `excel_parser/*`, `analytics/common/{aliasing,equipment_ids,plant_structure}.py`, `analytics/preprocessing/standardize.py`, `validation_service.py`.

### Registered fault / diagnostic algorithms
| Algorithm | Required signals (high level) | Reference |
|-----------|-------------------------------|-----------|
| `disconnected_strings` | SCB `dc_current_a` + irradiance + architecture | PIC `ds_detection.py` |
| `module_damage` | SCB `dc_voltage_v` + architecture | PIC `module_damage.py` |
| `clipping_power` | inverter `ac_power_kw` + irradiance + ratings | PIC `clipping_derating.py` |
| `clipping_current` | SCB `dc_current_a` + irradiance + architecture | **PIC Lite only** (v1) |
| `string_outlier` | string or SCB `dc_current_a` | PIC `fault_engine` placeholders (enhanced) |
| `inverter_efficiency` / `box_plot` | AC + DC (or SCB I×V fallback) | PIC `faults.py` |
| KPIs | AC + irradiance (+ losses) | PIC dashboard helpers |

**Not in PIC Lite MVP** (present in reference codex): soiling, inverter shutdown, grid breakdown, communication issues, power limitation (peer AC underperformance 10:00–15:00), MPPT/TIGER DS branch.

---

## 3. Test matrix results

### 3.1 Onboarding / detection (`test_functional_onboarding_matrix.py`)

| Case | Result |
|------|--------|
| Alias matrix: AC/DC power, SMB/SCB/string current, voltage, POA/GHI, temps, IDs | PASS |
| `suggest_mapping` returns every header (incl. unmapped manual) — no silent drop | PASS |
| Plant-total AC demotion vs per-inverter-like column | PASS |
| Official Complete Analysis Pack headers → confidence 1.0 | PASS |
| `derive_level` for INV / SMB / SCB / Combiner / STR variants | PASS |
| Infer 3 inverters × 4 SCBs × 4 strings from IDs | PASS |
| Standalone `SMB-01/02` + architecture → `inverter_id` backfill | PASS |
| Demo CSV full INV→SCB→STR tree | PASS |
| DS prerequisites ready / not ready with architecture gate | PASS |
| Long tidy CSV → standardize hierarchy | PASS |
| Wide Excel (~48 SMB columns) headers preserved (not collapsed to INV-only) | PASS |
| Multi-sheet workbook loads SCADA sheet | PASS |

### 3.2 Fault detection — MUST fire / MUST NOT fire (`test_functional_fault_matrix.py`)

| Algorithm | MUST fire | MUST NOT fire | Demo GT | Result |
|-----------|-----------|---------------|---------|--------|
| Disconnected strings | 1-of-4 string missing ≥7 h | 30 min drop; healthy equal SCBs; spare flag | INV-01-SCB-01 | PASS |
| DS + standalone SMB IDs | Architecture backfill path | — | — | PASS |
| Module damage | 15% V drop → `module_damage` | 1% noise | INV-01-SCB-02 | PASS |
| Bypass diode | 5% V drop → `bypass_diode` | — | INV-02-SCB-01 | PASS |
| String outlier | 40% of peer current (time-major rows) | Equal strings | INV-02-SCB-03-STR-02 | PASS |
| Clipping power | At-rated + rising GTI | Well below rated | INV-01 | PASS |
| Clipping current (v1) | Runs without crash; soft GT | — | smoke | PASS |
| Inverter efficiency | Degraded INV ranked worse | — | INV-02 | PASS |
| Box plot | Produces stats/charts | — | demo | PASS |
| Scope gate | soiling / power_limitation / shutdown not in MVP | — | — | PASS |

### 3.3 Prior suites (still green)
RCA column detection, standardize, complete pack, per-algorithm demo GT tests, orchestrator, architecture/prerequisites, auth (after SQLite fix).

---

## 4. Bugs found + fixed

| Bug | Evidence | Fix |
|-----|----------|-----|
| **String outlier persistence order-dependent** | Time-major canonical frames (all devices at `t`, then `t+1`) shattered persistence runs to length 1 → false UNAVAILABLE. Demo passed only because synthetic generator writes equipment-major order. | Sort by `[unit_col, timestamp_utc]` before persistence in `analytics/algorithms/string_outlier.py`. Regression test: `test_string_outlier_must_fire_even_when_rows_are_time_major`. |
| **Auth tests crash on SQLite** | `_ensure_columns` queried Postgres-only `information_schema.columns` → 12 errors + 1 failure in `test_auth.py`. | Dialect-agnostic SQLAlchemy `inspect().get_columns()` in `backend/app/database.py`. |

No other production algorithm threshold changes were required for the matrix to match reference behavior on synthetic cases.

---

## 5. Still-failing / residual accuracy risks

Honest gaps — not claimed as 100% OEM coverage:

1. **Wide-per-SMB columns → one `dc_current_a`**: many SMB current columns mapped to the same canonical field still **coalesce** (first non-null wins). Need dedicated wide→long melt or OEM long-format export. (See `docs/RCA_COLUMN_DETECTION.md` §6.)
2. **DS outlier ceiling = `Isc_stc × strings`**: matches PIC; currents slightly above nameplate (noise / bifacial) drop peers from the virtual reference and can break persistence. Residual false-negative risk on hot plants.
3. **Clipping by current is v1** — no PIC baseline; synthetic high-current SCB does not hard-saturate, so “must fire” is soft.
4. **Not ported from reference:** soiling, power limitation (peer AC underperformance), inverter shutdown / grid breakdown, MPPT/TIGER DS path, status/zero-export operating filters.
5. **Architecture key mismatch** still needs human fix for fuzzy OEM renames (case-insensitive lookup only).
6. **Inverter-only DC current** can satisfy readiness while DS needs SCB/SMB-level rows.
7. **`max_columns` deployment limit** still not enforced at upload.
8. **OEM sample coverage:** aliases include industry-common names but are not yet validated against a broad set of real Sungrow/Huawei/ABB/SMA/TBEA exports.

---

## 6. Recommended next data packs (OEM coverage)

| Pack | Why |
|------|-----|
| Long tidy Complete Analysis Pack from 2–3 real plants | Gold path already coded; confirm live readiness + DS/SMB |
| Wide “one column per SMB current” Excel (OEM export as-is) | Forces melt/coalesce solution; highest residual mapping risk |
| Standalone `SMB-01` IDs + separate architecture sheet | Validates backfill under real naming |
| Inverter + separate WMS files (merge path) | Irradiance join + clipping/DS operating gate |
| MPPT / string-inverter export | Gap vs PIC TIGER/MPPT DS branch |
| Known fault windows from O&M (open fuse, clipping day, soiling step) | Calibrate thresholds; decide whether to port soiling / power_limitation |

---

## 7. How to re-run

```bash
# From repo root, with .venv activated
python -m pytest tests/ -q
python -m pytest tests/test_functional_onboarding_matrix.py tests/test_functional_fault_matrix.py -q
```

Artifacts: `tests/helpers_fault_context.py` (synthetic mini-plants), matrix modules above, this report.
