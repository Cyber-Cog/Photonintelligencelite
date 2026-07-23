# RCA: Column / Signal Detection (PIC Lite)

**Date:** 2026-07-23  
**Scope:** Upload → header extraction → alias mapping → plant/architecture → algorithm readiness (esp. disconnected strings / SMB DC current)  
**Site:** piclite.vigorithm.com  

---

## 1. Symptoms

1. After Excel upload (post async-parse / 502 fix), users reported **columns not detected** or that something “got removed” — mapping suggestions empty or incomplete.
2. Friend uploaded **SMB current** telemetry — **not detected as DC current** for **disconnected string analysis**. Expectation: all relevant parameters detected; no silent misses.
3. Trust demand: proper RCA → root cause → functional tests → fix → written report (this document).

---

## 2. Investigation summary (pipeline traced)

| Stage | Path | Finding |
|-------|------|---------|
| Upload / async Excel | `backend/app/routers/upload.py` | Async deferral does **not** drop headers by itself; while `state=parsing`, Setup briefly sees `detected_columns=[]` until poll completes. |
| Probe early-break | `excel_parser/probe.py` | Breaks on **rows** (`sample_rows=30`), not columns. **Not** a first-N column cap. |
| Full sheet load | `load_sheet_matrix` | openpyxl `read_only` can under-report width; CSV write clips rows to header width — trailing columns at risk if width understated. |
| Layout strategies | `excel_parser/orchestrator.py` | Wide INV strategies early-accept at confidence ≥ 0.85 and emit only tidy INV metrics — can **discard** hundreds of SMB/string columns on wide non-INV sheets. |
| Aliases | `analytics/config/aliases.yaml` + `aliasing.py` | Canonical signal is `dc_current_a`. **No SMB current aliases** previously; short aliases (`i`) were dead because `len<=2` blocked **before** exact match. |
| Equipment level | `equipment_ids.py` | `SMB-01` / standalone combiner IDs did **not** classify as `device_type=scb`. |
| Disconnected strings | `disconnected_strings.py` | Requires `device_type=="scb"` + non-null `scb_id`, `inverter_id`, `dc_current_a`. Standalone SMB ids failed parent inverter resolution even when architecture existed. |
| Readiness UI | `prerequisites.py` / `validation_service.py` | Field presence of `dc_current_a` + architecture → “Will run”; runtime still unavailable if rows are not SCB-level with `inverter_id`. |

---

## 3. Root causes (numbered)

### RC1 — Missing SMB / string / combiner aliases for `dc_current_a` (and related IDs)
**Evidence:** `aliases.yaml` had `string current` / `scb current` but not `smb current`, `smb_current`, `combiner current`, etc. Mapping auto-suggest never proposed `dc_current_a` for “SMB Current”.  
**Impact:** User-visible “SMB current not detected as DC current.”

### RC2 — Exact short aliases blocked by ambiguous-length check
**Evidence:** `score_column` called `_is_ambiguous_column` (includes `len(n) <= 2`) **before** exact alias lookup, so YAML entries `i`, `v`, `p`, `id` never matched.  
**Impact:** Dead aliases; false sense that vocabulary covered OEM short names.

### RC3 — SMB equipment IDs not classified as SCB
**Evidence:** `derive_level` only recognized `SCB` / `MPPT` patterns, not standalone `SMB-01` or `INV-01-SMB-02`. Rows fell through to `device_type=plant`.  
**Impact:** Disconnected-string filter (`device_type == "scb"`) dropped all SMB telemetry.

### RC4 — No architecture backfill of `inverter_id` for standalone SMB ids
**Evidence:** `standardize` only derived parent inverter from ID string patterns; architecture map was unused at ingest. DS `dropna(subset=["inverter_id"])` emptied the frame.  
**Impact:** Even with Setup architecture filled, DS returned unavailable.

### RC5 — Wide Excel early-accept could discard non-INV wide headers
**Evidence:** `_run_strategies` returned immediately on wide confidence ≥ 0.85; wide builders only keep mapped INV tidy fields. SMB-metric-heavy sheets (≥40 cols with many `SMB*Current` headers) could lose most columns.  
**Impact:** “Columns got removed” / mapping list far smaller than the sheet.

### RC6 — Header width robustness under openpyxl read_only (secondary)
**Evidence:** Trailing empty cells omitted per row; if declared dimensions understate width, CSV clip can drop trailing headers. Probe row sampling does **not** intentionally truncate columns.  
**Impact:** Possible trailing-column loss on pathological sheets; hardened load/pad path.

### RC7 — Empty columns during async parse (UX, not data loss)
**Evidence:** Intake returns `detected_columns=[]` while Excel is still parsing. Frontend polls until ready; if user navigates early or poll fails, UI looks like “no columns.”  
**Impact:** Confusion after 502 fix; not a permanent header drop when poll succeeds.

---

## 4. Fixes applied

| Fix | Location |
|-----|----------|
| Expanded `dc_current_a` / `dc_voltage_v` / `scb_id` / `string_id` aliases (SMB, combiner, string variants) | `analytics/config/aliases.yaml` |
| Exact alias before ambiguous check; OEM numbered patterns (`SMB01 Current`, etc.) | `analytics/common/aliasing.py` |
| `SMB` / standalone combiner → `device_type=scb`; architecture inverter lookup helper | `analytics/common/equipment_ids.py` |
| `standardize(..., architecture=)` backfills `inverter_id` | `analytics/preprocessing/standardize.py` + `pipeline.py` |
| DS runtime architecture backfill + clearer unavailable message | `analytics/algorithms/disconnected_strings.py` |
| Probe/load: pad to declared width; never sample away columns | `excel_parser/probe.py` |
| Demote wide early-accept on SMB-metric-heavy sheets so tidy preserves headers | `excel_parser/orchestrator.py` |
| Tidy strategy accepts current-like columns without AC power | `excel_parser/strategies/tidy_long.py` |

Canonical name remains **`dc_current_a`** (no separate `smb_current` field). SMB current is an alias of DC current; architecture + equipment level make it usable for disconnected strings.

---

## 5. Test evidence

New suite: `tests/test_column_detection_rca.py`

- Alias matrix: `SMB Current`, `SMB_Current`, `String Current`, `Idc`, `DC Current (A)`, combiner/MPPT variants → `dc_current_a` @ auto band  
- Numbered patterns: `SMB01 Current`, `SCB 3 Current (A)`, …  
- `SMB ID` / `smb` → `scb_id`  
- Exact short alias `i` still maps when listed in YAML  
- Complete Analysis Pack official headers still map 1.0  
- `derive_level("SMB-01") == "scb"`; architecture resolves parent INV  
- `standardize` with SMB current + architecture → SCB rows with `inverter_id`  
- Disconnected-string prerequisites `will_run` when `dc_current_a` + irradiance + architecture present  
- Wide Excel (≥120 SMB current columns): probe/`load_sheet_matrix` keep full header; strategy preserves SMB columns  

Run:

```bash
pytest tests/test_column_detection_rca.py tests/test_standardize.py tests/test_complete_analysis_pack.py tests/test_disconnected_strings.py -q
```

---

## 6. Residual risks / known limits

1. **Many SMB columns all mapped to one `dc_current_a`** still **coalesce** (first non-null wins) in `standardize`. Wide-per-timestamp “one column per SMB” layouts need a dedicated melt strategy or long-format export (Timestamp + Equipment ID + current). Header preserve + alias suggest is fixed; reshape-to-long for N SMB metric columns is not fully automated.
2. **Architecture keys must match** equipment ids (case-insensitive match added; fuzzy rename still manual).
3. **Async parse UX:** Setup can briefly show zero columns until polling finishes — frontend wait is required.
4. **Inverter-level DC current** can still make readiness look OK while DS needs **SCB/SMB-level** rows — improved messaging, but users must map SCB/SMB current (not only inverter DC).
5. **`max_columns` in defaults.yaml** remains unused at upload — very wide files are allowed; memory/time limits still apply.

---

## 7. Deploy note

Mapping/alias and Excel-parser fixes must be deployed for piclite.vigorithm.com to pick them up (push to `main` / production pipeline). Client-only refresh will not fix server-side alias or parse behavior.
