/** First canonical field to highlight for each algorithm “Needs input” card. */
export const ALGORITHM_FIELD_HINTS: Record<string, string> = {
  kpis: "ac_power_kw",
  inverter_efficiency: "ac_power_kw",
  box_plot: "ac_power_kw",
  clipping_power: "ac_power_kw",
  clipping_current: "dc_current_a",
  module_damage: "dc_voltage_v",
  disconnected_strings: "dc_current_a",
  string_outlier: "dc_current_a",
};
