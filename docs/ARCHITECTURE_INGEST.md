# Architecture ingest (Indian-site friendly)

PIC Lite stores plant structure as `plant_config.architecture` (SCB → inverter map)
plus `equipment_ratings`. Upload parsers normalize **all** accepted shapes into that
JSON — Setup does not require the nested hierarchy UI.

Code: `analytics/common/architecture_excel.py` · merge: `backend/app/services/pack_architecture_import.py`.

---

## Supported formats

### Method A — Flat table (recommended)

One row per SMB/SCB. Typical Indian EPC / O&M export:

| Canonical | Example headers accepted |
|---|---|
| `inverter_id` | Inverter ID, INV, INV No, PCS |
| `scb_id` | SCB ID, SMB, SMB No, Combiner, AJB, MPPT |
| `inverter_rated_kw` | Rating kW, Inverter kW, Capacity kW, Rated kW |
| `strings_per_scb` | No of Strings, Strings per SMB, String Count |
| `dc_capacity_kwp` (optional) | DC Capacity, kWp, DC kWp |
| `string_id` (optional) | String ID, STR — used to count strings when count column is blank |

Download template: `GET /api/architecture-template`.

### Method B — Same workbook as SCADA

1. Companion sheet named e.g. `Architecture`, `Plant`, `Master`, `Inverter List`,
   `Equipment`, `Hierarchy`, `SMB List`, … with Method A (or C) columns, **or**
2. SCADA sheet that already has `Inverter ID` + `SCB ID` (unique pairs → architecture;
   format tag `scada_embedded`).

Upload on the Upload page auto-imports into Setup (`architecture_imported`).

### Method C — Hierarchy (advanced / Complete Analysis Pack sample)

Columns: `id`, `parent_id`, `device_type`, `ac_capacity_kw`, `dc_capacity_kwp`,
`strings_per_scb`, `notes`. Plant → Inverter → SCB → String. Still fully supported;
not required for most Indian sites.

---

## Detection order

1. Score every sheet by **name** (architecture / plant / master / … beat `scada`).
2. Read header row; map OEM synonyms → canonical columns.
3. Detect layout: hierarchy (`id` + `device_type`/`parent_id`) or flat (`inverter_id` + `scb_id`).
4. Prefer dedicated flat/hierarchy sheets over SCADA-embedded ID columns.
5. Normalize to `plant_config` draft (ratings, per-SCB map, optional plant MW/MWp).

SCADA telemetry parsing still prefers the `scada` sheet; architecture sheets are
demoted in that ranking so they are not mistaken for telemetry.

---

## Setup UX

- Banner **Detected from upload** when the workbook already supplied structure.
- Otherwise: flat Excel upload, re-detect from mapped SCADA IDs, or optional bulk pattern.
