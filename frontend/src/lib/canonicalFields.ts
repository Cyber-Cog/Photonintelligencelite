/** Mirrors analytics/config/aliases.yaml top-level keys + the "ignore" escape hatch. */
export const CANONICAL_FIELD_OPTIONS: { value: string; label: string }[] = [
  { value: "timestamp", label: "Timestamp" },
  { value: "device_id", label: "Device ID" },
  { value: "icr_id", label: "ICR ID" },
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

/** Short badge text for mapping row hierarchy (matches backend hierarchy_level). */
export const HIERARCHY_LEVEL_BADGE: Record<string, string> = {
  plant: "Plant",
  icr: "ICR",
  inverter: "Inverter",
  scb: "SCB",
  string: "String",
  equipment: "Equipment row",
  multi: "Multi-level",
};

const IDENTITY_LEVEL: Record<string, string> = {
  timestamp: "plant",
  icr_id: "icr",
  inverter_id: "inverter",
  scb_id: "scb",
  string_id: "string",
  device_id: "equipment",
  poa_w_m2: "plant",
  ghi_w_m2: "plant",
  module_temp_c: "plant",
  ambient_temp_c: "plant",
};

const MULTI_METRICS = new Set([
  "ac_power_kw",
  "dc_power_kw",
  "dc_current_a",
  "dc_voltage_v",
  "energy_kwh",
]);

/** Infer hierarchy badge from the live mapping dict (updates as the user edits selects). */
export function inferMappingHierarchyLevel(
  canonicalField: string | null | undefined,
  companionFields: Set<string>,
): string | null {
  if (!canonicalField || canonicalField === "ignore") return null;
  if (IDENTITY_LEVEL[canonicalField]) return IDENTITY_LEVEL[canonicalField];
  if (!MULTI_METRICS.has(canonicalField)) return null;
  if (companionFields.has("string_id")) return "string";
  if (companionFields.has("scb_id")) return "scb";
  if (companionFields.has("inverter_id")) return "inverter";
  if (companionFields.has("device_id")) return "equipment";
  return "multi";
}

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
