# PIC Lite — Complete Analysis Pack (official data format)

This is the **canonical upload format** for running every PIC Lite fault module
end-to-end. Multi-file / fuzzy OEM mapping remains fully supported for messy real
SCADA; this document defines the **accurate / methodical path**.

**Code source of truth for column headers:** `analytics/common/complete_analysis_pack.py`
(`SCADA_COLUMNS` / `OFFICIAL_COLUMN_TO_CANONICAL`). Download endpoints build templates
from that module at request time — there is no separate static file to go stale.
Run `scripts/check_template_sync.py` after changing headers.

Download before upload:

| Artifact | Endpoint |
|---|---|
| Excel (README + `scada` + `architecture` + checklist) | `GET /api/templates/complete-analysis` |
| ZIP (`01_scada_long.csv` + `02_architecture.xlsx` + README) | `GET /api/templates/complete-analysis.zip` |
| Architecture-only (Setup Method A) | `GET /api/architecture-template` |

UI: **Landing** and **Upload** pages — “Download complete analysis template”.

---

## 1. What is necessary for ALL faults to run

Point this out first — if any of these are missing, Validation will correctly show
**Blocked** / Results **Needs input** for the affected modules.

| # | Necessity | Why |
|---|---|---|
| 1 | **Timestamp** on every telemetry row | Interval normalization; fault windows |
| 2 | **Resolvable equipment IDs** (inverter / SCB / string) | Peer groups, parent rollups, architecture join |
| 3 | **AC power (kW)** | KPIs, clipping-by-power, efficiency, box plot |
| 4 | **DC power (kW) *or* DC current (A)** | Efficiency / box plot (DC synthesizable from ΣI×V) |
| 5 | **DC current (A)** at SCB or string | Clipping-by-current, disconnected strings, string outlier |
| 6 | **DC voltage (V)** at SCB | Module damage / bypass diode |
| 7 | **POA or GHI (W/m²)** | Clipping (power & current), disconnected strings |
| 8 | **Plant architecture** (INV → SCB → `strings_per_scb`) | Current clipping, DS, module damage |
| 9 | **Inverter ratings (kW)** | Clipping-by-power clip limit |

**Units (required):** power in **kW** (not MW), current in **A**, voltage in **V**,
irradiance in **W/m²**, temperature in **°C**.

Demo / customer exports that omit SCB DC current/voltage will correctly leave
SCB-level modules unavailable — that is expected, not a bug.

---

## 2. Official SCADA shape: long tidy table

One row = one equipment reading at one timestamp. Blank cells are fine where a
signal does not apply at that level (e.g. AC power only on inverter rows).

### Required / recommended columns

| Column header (official) | Canonical field | Required? |
|---|---|---|
| `Timestamp` | `timestamp` | **Required** |
| `Equipment ID` | `device_id` | **Required** (or separate ID columns) |
| `AC Power (kW)` | `ac_power_kw` | Required for KPIs / AC faults |
| `DC Power (kW)` | `dc_power_kw` | Recommended (or use DC current) |
| `DC Current (A)` | `dc_current_a` | Required for SCB/string faults |
| `DC Voltage (V)` | `dc_voltage_v` | Required for module damage |
| `Irradiance (W/m2)` | `poa_w_m2` | Required for irradiance-gated faults (or GHI) |
| `GHI (W/m2)` | `ghi_w_m2` | Optional if POA present |
| `Module Temp (C)` | `module_temp_c` | Optional |
| `Ambient Temp (C)` | `ambient_temp_c` | Optional |

Optional explicit ID columns (instead of / in addition to hierarchical `Equipment ID`):
`Inverter ID`, `SCB ID`, `String ID` — see `analytics/config/aliases.yaml`.

### Recommended hierarchy (Equipment ID)

```text
INV-01                          ← inverter
INV-01-SCB-01                   ← SMB / combiner / MPPT
INV-01-SCB-01-STR-01            ← string (optional but enables string outlier / DS detail)
PLANT-WMS-01                    ← weather / meteo row (irradiance + temps)
```

PIC Lite derives parent inverter/SCB from these IDs when architecture is present.
Other OEM naming still works via fuzzy mapping + Setup architecture.

### Timestamp conventions

- Prefer `YYYY-MM-DD HH:MM:SS` (no timezone suffix in the cell).
- Declare the plant timezone in Setup (e.g. `Asia/Kolkata`).
- Use a consistent sample interval (5 / 10 / 15 min typical).

---

## 3. Excel Complete Analysis Pack layout

| Sheet | Purpose | Uploaded how? |
|---|---|---|
| `README` | Instructions + necessities | Not ingested |
| `scada` | Long-format sample / your filled telemetry | **Upload this workbook** on Upload page (parser prefers `scada`) |
| `architecture` | One row per SCB: `inverter_id`, `inverter_rated_kw`, `scb_id`, `strings_per_scb`, `notes` | Setup → Equipment structure → Method A (save sheet or use ZIP’s `02_architecture.xlsx`) |
| `fault_checklist` | Per-module column/config matrix | Reference only |

---

## 4. ZIP Complete Analysis Pack layout

| File | Purpose |
|---|---|
| `README.txt` | Same necessities + how-to |
| `01_scada_long.csv` | Official long SCADA (upload on Upload page) |
| `02_architecture.xlsx` | Matching architecture for sample IDs (upload in Setup) |

Clients who already export CSV SCADA can keep their multi-file habit and only
adopt the column/ID conventions from this pack.

---

## 5. Per-fault input matrix

| Module | SCADA fields | Setup config |
|---|---|---|
| Plant KPIs | `ac_power_kw` | — |
| Clipping by power | `ac_power_kw` + (`poa_w_m2` ∨ `ghi_w_m2`) | Inverter ratings |
| Inverter efficiency | `ac_power_kw` + (`dc_power_kw` ∨ `dc_current_a`) | — |
| Box plot | same as efficiency | — |
| Clipping by current | `dc_current_a` + (`poa_w_m2` ∨ `ghi_w_m2`) | Architecture |
| Disconnected strings | `dc_current_a` + (`poa_w_m2` ∨ `ghi_w_m2`) | Architecture |
| Module damage | `dc_voltage_v` | Architecture |
| String outlier | `dc_current_a` | — |

Source of truth in code: `analytics/common/prerequisites.py`.

---

## 6. Optional vs required (summary)

**Always required for a useful run:** timestamp, equipment identity, AC power,
irradiance (POA or GHI), inverter ratings, architecture.

**Required only for full fault coverage:** DC current, DC voltage (and ideally
string-level current for string outlier / DS detail).

**Optional:** module/ambient temperature, energy (kWh), GHI when POA exists,
string-level rows when SCB aggregates are enough for plant-level screening.

---

## 7. Versatility (unchanged)

- Multi-file upload + timestamp join of inverter + WMS exports still works.
- Fuzzy alias mapping and saved OEM templates still work.
- The Complete Analysis Pack is the **official clear path**, not the only path.

Canonical schema after standardization: see
[`architecture_decisions.md`](architecture_decisions.md) §1.
