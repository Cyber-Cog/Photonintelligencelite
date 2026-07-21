export interface AlgorithmDoc {
  id: string;
  title: string;
  version: string;
  summary: string;
  inputs: string[];
  formula: string;
  steps: string[];
  thresholds: string[];
  outputs: string[];
}

export const ALGORITHM_DOCS: AlgorithmDoc[] = [
  {
    id: "kpis",
    title: "Plant KPIs",
    version: "1.0",
    summary: "Aggregates plant-level performance ratio, specific yield, availability, and total energy from canonical SCADA.",
    inputs: ["Inverter AC power (kW)", "POA or GHI irradiance", "Plant AC/DC capacity", "Timezone"],
    formula: "PR (%) = (AC energy / (DC capacity × insolation)) × 100 · Specific yield = AC energy / DC capacity (kWh/kWp)",
    steps: [
      "Sum AC energy using cadence-aware Δt between samples.",
      "Integrate irradiance to insolation (kWh/m²) over the analysis window.",
      "Compute PR when both AC energy and insolation are available.",
      "Availability: daylight hours (irradiance above floor) where plant AC is negligible vs nameplate.",
    ],
    thresholds: ["Daylight irradiance floor for availability", "PR benchmark (optional plant config)"],
    outputs: ["Performance ratio %", "Specific yield kWh/kWp", "Plant availability %", "Total AC energy"],
  },
  {
    id: "inverter_efficiency",
    title: "Inverter Efficiency Loss",
    version: "1.0-port",
    summary: "Compares inverter AC output to DC input; flags sustained sub-normal conversion efficiency.",
    inputs: ["AC power (kW)", "DC power (kW) OR SCB DC current + voltage"],
    formula: "Efficiency (%) = (AC / DC) × 100 on samples where DC > AC",
    steps: [
      "Build per-inverter DC: native dc_power_kw, or Σ(I_scb × avg V_scb) / 1000 from child SCBs.",
      "Compute efficiency only when DC exceeds AC (meaningful conversion sample).",
      "Integrate (DC − AC) × Δt for energy loss kWh.",
      "Rank inverters by loss; surface worst performers.",
    ],
    thresholds: ["Minimum efficiency %", "Minimum sample count per inverter"],
    outputs: ["Loss by inverter (kWh)", "Efficiency trend chart", "Per-inverter metrics"],
  },
  {
    id: "box_plot",
    title: "Inverter Efficiency Box Plot",
    version: "1.0-port",
    summary: "Distribution of per-sample inverter efficiency — min, Q1, median, Q3, max per inverter.",
    inputs: ["Same as inverter efficiency"],
    formula: "Box stats on efficiency % samples per inverter_id",
    steps: [
      "Reuse the shared efficiency frame (never disagrees with efficiency module).",
      "Compute quartiles per inverter; clamp to plausible 0–100% range.",
      "Render categorical box plot with whiskers = min/max.",
    ],
    thresholds: ["Plausible efficiency clamp range"],
    outputs: ["Box plot chart", "Distribution statistics table"],
  },
  {
    id: "clipping_power",
    title: "Inverter Clipping by Power",
    version: "1.0-port",
    summary: "Detects AC power saturation against a virtual irradiance curve (PIC clipping_derating engine).",
    inputs: ["AC power (kW)", "POA or GHI", "Inverter ratings (kW)"],
    formula: "Virtual curve k = median(P/GTI) on healthy samples; clip when AC ≈ rated and GTI supports higher",
    steps: [
      "Join irradiance to AC samples (merge_asof, local solar time).",
      "Calibrate virtual expected AC from irradiance per inverter.",
      "Classify clip vs derate vs healthy using rated-hit ratio + persistence.",
      "Skip inverters below ~40% expected daytime coverage.",
      "Integrate (expected − actual) × Δt for clip-only loss.",
    ],
    thresholds: ["min_coverage_frac (0.40)", "Rated hit ratio", "Persistence minutes", "Noise band"],
    outputs: ["Clip loss by inverter", "Loss trend", "Skipped inverter count"],
  },
  {
    id: "clipping_current",
    title: "Inverter Clipping by Current (v1)",
    version: "1.0-v1",
    summary: "Lite v1 DC-side clip heuristic — linear over-current vs estimated rated current per SCB/MPPT.",
    inputs: ["SCB DC current (A)", "POA or GHI", "Architecture (strings per SCB)"],
    formula: "Rated I_est from architecture; flag sustained over-current vs virtual irradiance curve",
    steps: [
      "Estimate rated DC current from strings × module Isc proxy.",
      "Calibrate expected current vs irradiance.",
      "Flag persistence windows where measured current exceeds expected clip threshold.",
    ],
    thresholds: ["v1 thresholds; validate against site operating data"],
    outputs: ["Clip events by SCB", "Recommendation to validate v1 thresholds"],
  },
  {
    id: "disconnected_strings",
    title: "Disconnected Strings",
    version: "1.0-port",
    summary: "PIC ds_detection SCB path: virtual reference current, persistence confirmation, energy loss.",
    inputs: ["SCB DC current (A)", "SCB DC voltage (V)", "POA or GHI", "Architecture (strings per SCB)"],
    formula: "Missing I = I_expected − I_measured; loss = V × I_missing × Δt",
    steps: [
      "Remove leakage-current days (low irradiance + high current all day).",
      "Gate on irradiance / time-of-day.",
      "Rolling-median smooth current & voltage per SCB.",
      "Normalize to per-string current; build virtual reference from top-quartile SCBs per inverter+timestamp.",
      "Candidate when drop ≥ threshold; confirm after persistence window (default 360 min).",
      "Exclude spare SCBs from architecture.",
    ],
    thresholds: ["persistence_minutes", "current_drop_pct", "missing_string_tolerance", "rolling_median_window"],
    outputs: ["Loss by SCB", "Investigate chart (expected vs measured + fault bands)", "Fault table"],
  },
  {
    id: "module_damage",
    title: "Module Damage / Bypass Diode",
    version: "1.0-port",
    summary: "Voltage deviation from plant reference — bypass diode (3–8%) vs module damage (8–30%).",
    inputs: ["SCB DC voltage (V)", "Architecture (strings × modules × Wp)"],
    formula: "pct_dev = (ref_V − measured_V) / ref_V; loss = dc_kW × pct_dev × forward_Δt",
    steps: [
      "Median inverter voltage per timestamp; plant reference = median of top-quartile inverter medians.",
      "Classify bypass vs module damage by pct_dev bands.",
      "Require minimum sustained fault samples.",
      "Integrate loss with per-SCB forward Δt (gap-aware, PIC parity).",
    ],
    thresholds: ["bypass_pct_lo/hi", "damage_pct_min/max", "min_persist_samples"],
    outputs: ["Loss by SCB", "Investigate chart (reference vs measured V + fault bands)", "Fault kind table"],
  },
  {
    id: "string_outlier",
    title: "String Current Outlier",
    version: "1.0-port",
    summary: "Flags strings/SCBs persistently below peer-group median current; estimates proxy loss.",
    inputs: ["SCB or string DC current (A)"],
    formula: "Deviation = group_median − measured; loss_proxy = deviation × V × Δt",
    steps: [
      "Group peers by inverter + timestamp.",
      "Flag samples below median × (1 − threshold) for min_persist_samples.",
      "Sum proxy energy loss (labeled as estimate, not confirmed balance).",
    ],
    thresholds: ["low_current_ratio", "min_persist_samples"],
    outputs: ["Outlier loss by equipment", "Recommendation text"],
  },
];
