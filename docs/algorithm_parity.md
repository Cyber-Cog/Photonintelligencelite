# Algorithm Parity Notes

Tracks every place PIC Lite's ported logic intentionally differs from the source PIC
codebase (`C:\Users\ayush.r\Desktop\PIC\solar_analytics_codex_bundle`) or its formula docs
(`backend/docs/FORMULAS_REFERENCE.md`, `backend/docs/PLATFORM_ARCHITECTURE_AND_FLOW.md`).
Per docs/PRD.md §9, every threshold is named and overridable in
`analytics/config/thresholds.yaml`; this document explains *why* each divergence exists.

## Disconnected strings (`analytics/algorithms/disconnected_strings.py`)

Ported from `backend/engine/ds_detection.py::run_ds_detection`.

- **Removed**: all SQLAlchemy session/DB read-write code, `fault_events`/`fault_diagnostics`
  bulk-insert, fault-episode sidecar rebuild, cache invalidation. PIC Lite returns a
  `ResultObject`, not database rows.
- **Not ported**: the MPPT-specific comparison branch (`plant_type == "MPPT"`, keyed off a
  hardcoded `"TIGER" in plant_id` string check in the source). PIC Lite has no equivalent
  plant-name hack and no generic way to detect "MPPT-style SCB" from a CSV upload alone;
  only the SCB central-inverter comparison path is implemented. If a real MPPT-style export
  is supplied, string_outlier and disconnected_strings will run in SCB mode, which is more
  conservative (see `docs/PRD.md §0` OEM alias note — revisit once real exports are supplied).
- **Ported (2026-07-20)**: the smoothing rolling-median step (Step 5b in the source) is now
  implemented (`_smooth_measurements`, per-SCB centered rolling median on current/voltage,
  window `rolling_median_window`=5). The string-level detection variant
  (`run_ds_detection_string_level`) is still **not ported** — string-level DS is instead
  covered by `string_outlier.py`'s low-current rule, a reasonable proxy for MVP that avoids
  maintaining two near-duplicate persistence-window implementations.
- **Ported (2026-07-20)**: spare-SCB support. Architecture entries may carry `spare_flag`;
  spare SCBs are excluded from DS detection exactly as PIC's `spare_scbs` set does, so a
  parked/spare combiner is never reported as a disconnected string.
- **Simplified**: irradiance/inverter-status/zero-export operating filters
  (`_apply_operating_filters` in the source) are reduced to the irradiance/time-of-day gate
  only. The inverter-status and zero-export suppression filters depend on signals
  (`status`, `active_power`, `energy_export_kwh`) that are not part of PIC Lite's fixed
  canonical schema and are not guaranteed to exist in an arbitrary upload.
- **Preserved as-is**: leakage-current pre-filter, near-constant/frozen-day removal,
  top-percentile virtual reference, persistence-window confirmation, and the V×I_missing
  energy-loss integration with per-sample Δt.

## Module damage / bypass diode (`analytics/algorithms/module_damage.py`)

Ported from `backend/engine/module_damage.py::run_module_damage`. Formulas (3-8% bypass,
8-30% module damage, plant-reference = median of top-quartile inverter-median voltage) are
unchanged. `dc_kw` per SCB is derived from `strings_per_scb × modules_per_string ×
module_rating_wp` (plant config) instead of the source's `soiling_queries.scb_dc_map` DB
lookup, since PIC Lite has no persisted per-SCB nameplate table — this is a deliberate,
documented substitution, not a bug.

- **Ported (2026-07-20)**: energy-loss integration now uses the source's per-SCB *forward*
  Δt (`_forward_dt_hours`: time to the next sample, capped at 2× the per-SCB median cadence)
  instead of a flat `sample_interval` interval. This matches PIC so a data gap after a
  faulted sample is not integrated as loss time.

## Clipping by power (`analytics/algorithms/clipping_power.py`)

Ported from `backend/engine/clipping_derating.py::run_clipping_derating`. The virtual-curve
calibration (`k = median(P/GTI)` over healthy samples), rated-hit-ratio/noise/persistence
classification, and merge_asof irradiance join (`analytics/common/irr_join.py`, ported from
`backend/engine/irr_join.py`) are unchanged. Static/dynamic derate classification is
retained internally (required to correctly exclude derate samples from the clip-only loss
sum) but is **not exposed as its own `ResultObject`** — the MVP algorithm list
(docs/PRD.md §7.8) only requires "inverter clipping by power" as a first-class result.

- **Ported (2026-07-20)**: the source's per-inverter coverage guard (Step 6,
  `CD_MIN_COVERAGE_FRAC`=0.40). Inverters whose usable daytime samples fall below
  `min_coverage_frac` of the expected count (denominator capped by observed AC↔GTI pairs so
  sparse-but-complete uploads don't false-fail) are skipped and reported in the result's
  `skipped_inverter_count` metric + a recommendation line, rather than being silently
  calibrated on too little data.

## Clipping by current (`analytics/algorithms/clipping_current.py`) — v1, NEW

Not present in the source PIC codebase — `clipping_derating.py`'s
`loss_current_clipping_kwh` field is hard-coded to `0.0`, explicitly reserved for future
DC-side work. This is a first version built for PIC Lite from scratch, modeled after the
power-clipping virtual-curve approach but on DC current. **No production baseline exists to
validate against.** Thresholds are marked `v1` in `analytics/config/thresholds.yaml` and
must be checked against real plant data before being trusted for severity claims — see the
in-code warning and the recommendation text emitted in every result.

## Inverter efficiency (`analytics/algorithms/inverter_efficiency.py`)

Ported from `backend/routers/faults.py::_compute_inverter_efficiency_analysis_payload`.
Formula (`efficiency% = AC/DC × 100` on samples where `DC > AC`, cadence-aware Δt for
energy) is unchanged.

- **Ported (2026-07-20)**: the SCB current×voltage DC-power fallback. When an inverter has
  no native `dc_power_kw` at a timestamp, DC is reconstructed as `ΣI_scb × avg(V_scb) / 1000`
  over its child SCBs (dummy 1000 V when SCB voltage is missing), exactly as the source
  does via its `plant_architecture` join. `compute_efficiency_frame` exposes a
  `dc_synthesized` flag so the efficiency result (and the shared box-plot module) can tell
  the plant owner when a figure is an estimate rather than metered. Prerequisites for both
  `inverter_efficiency` and `box_plot` were relaxed to `ac_power_kw` + (`dc_power_kw` OR
  `dc_current_a`) so the module runs on current-only SCB uploads.

## Box plot (`analytics/algorithms/box_plot.py`)

PRD gap fix #3: extracted from the efficiency payload into a first-class module (source:
`inverter_box_stats` embedded in the same function above). Box statistics (min/Q1/median/
Q3/max, clamped to a plausible efficiency range) are computed identically; both modules
share `inverter_efficiency.compute_efficiency_frame` so they never disagree on the
underlying per-sample values.

## String outlier (`analytics/algorithms/string_outlier.py`)

PRD gap fix #2: promoted from `backend/modules/fault_diagnostics/fault_engine.py`'s
`low_current_fault` and `scb_unbalance` placeholders. Two behavioral upgrades over the
source: (1) a persistence filter (`min_persist_samples`) is applied — the source flagged
every single low/imbalanced sample with no run-length requirement, which would be far too
noisy for a production result card; (2) the loss estimate (deviation-from-group-median ×
voltage × Δt) is new — the source placeholders returned fault *rows* with no loss
quantification at all. This loss number is explicitly labeled a proxy, not a confirmed
energy balance, in the result's recommendation text.

## KPIs (`analytics/algorithms/kpis.py`)

Performance Ratio, Specific Yield, and Insolation formulas are ported unchanged from
`backend/routers/dashboard.py::_plant_pr_pct` and
`backend/dashboard_helpers.py::gti_insolation_kwh_m2_from_sums`. **Plant Availability is a
documented MVP simplification**: the source computes availability by weighting
inverter-shutdown/grid-breakdown fault-hours by impacted DC capacity
(`backend/routers/faults.py` "Grid Availability" block), which requires engines
(`inverter_shutdown`, `grid_breakdown`) that are outside PIC Lite's MVP algorithm list
(docs/PRD.md §7.8 only lists 8 modules, none of which are shutdown/breakdown detection).
PIC Lite instead measures downtime as daylight hours (POA/GHI above a floor) during which
total plant AC output is negligible relative to nameplate capacity — deterministic,
traceable to the same canonical data, but not numerically identical to the source formula.
Revisit if inverter-shutdown/grid-breakdown detection is ever added post-MVP.

## Aliases (`analytics/config/aliases.yaml`)

Seeded from `backend/common/helpers.py` (`VALID_SIGNALS`) and `backend/common/templates.py`
(`TEMPLATE_COLUMNS`), plus common Sungrow/Huawei/ABB-FIMER/SMA/TBEA export column names
based on general industry knowledge (not from a real export sample yet — see
docs/PRD.md §0 OEM alias priority, "refined once real SCADA export samples are supplied").
