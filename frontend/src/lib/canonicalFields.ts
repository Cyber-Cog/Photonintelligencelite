/** Mirrors analytics/config/aliases.yaml top-level keys + the "ignore" escape hatch. */
export const CANONICAL_FIELD_OPTIONS: { value: string; label: string }[] = [
  { value: "timestamp", label: "Timestamp" },
  { value: "device_id", label: "Device ID" },
  { value: "inverter_id", label: "Inverter ID" },
  { value: "scb_id", label: "SCB / MPPT ID" },
  { value: "string_id", label: "String ID" },
  { value: "ac_power_kw", label: "AC Power (kW)" },
  { value: "dc_power_kw", label: "DC Power (kW)" },
  { value: "dc_current_a", label: "DC Current (A)" },
  { value: "dc_voltage_v", label: "DC Voltage (V)" },
  { value: "poa_w_m2", label: "POA Irradiance (W/m\u00b2)" },
  { value: "ghi_w_m2", label: "GHI Irradiance (W/m\u00b2)" },
  { value: "module_temp_c", label: "Module Temperature (\u00b0C)" },
  { value: "ambient_temp_c", label: "Ambient Temperature (\u00b0C)" },
  { value: "energy_kwh", label: "Energy (kWh)" },
  { value: "ignore", label: "Ignore this column" },
];

export const PLANT_TYPE_OPTIONS = [
  { value: "fixed_tilt", label: "Fixed tilt" },
  { value: "tracker", label: "Single-axis tracker" },
];

export const MODULE_TECHNOLOGY_OPTIONS = [
  "Mono PERC",
  "Bifacial Mono PERC",
  "Polycrystalline",
  "TOPCon",
  "HJT",
  "Thin Film",
];
