/** Actionable vs non-actionable fault module categorization (mirrors backend defaults). */

export type FaultCategory = "actionable" | "non_actionable";

export type FaultModuleMeta = {
  algorithm_id: string;
  label: string;
  hint: string;
  category: FaultCategory;
  is_default: boolean;
};

export type FaultCategoriesResponse = {
  actionable: string[];
  non_actionable: string[];
  categories: Record<string, FaultCategory>;
  modules: FaultModuleMeta[];
};

/** Product defaults when API is unreachable — keep in sync with backend fault_categories.py */
export const DEFAULT_FAULT_CATEGORIES: FaultCategoriesResponse = {
  actionable: ["disconnected_strings", "inverter_efficiency", "module_damage"],
  non_actionable: ["clipping_current", "clipping_power"],
  categories: {
    disconnected_strings: "actionable",
    module_damage: "actionable",
    inverter_efficiency: "actionable",
    clipping_power: "non_actionable",
    clipping_current: "non_actionable",
  },
  modules: [
    {
      algorithm_id: "disconnected_strings",
      label: "Disconnected Strings",
      hint: "String / SCB open-circuit — field repair",
      category: "actionable",
      is_default: true,
    },
    {
      algorithm_id: "module_damage",
      label: "Module Damage & Bypass Diode",
      hint: "Voltage deviation / damaged modules — field repair",
      category: "actionable",
      is_default: true,
    },
    {
      algorithm_id: "inverter_efficiency",
      label: "Inverter Efficiency Loss",
      hint: "Low conversion efficiency — maintenance / OEM",
      category: "actionable",
      is_default: true,
    },
    {
      algorithm_id: "clipping_power",
      label: "Inverter Clipping by Power",
      hint: "Design / irradiance limit — often non-actionable",
      category: "non_actionable",
      is_default: true,
    },
    {
      algorithm_id: "clipping_current",
      label: "Inverter Clipping by Current",
      hint: "DC current limit — often non-actionable",
      category: "non_actionable",
      is_default: true,
    },
  ],
};

export function categoryForAlgorithm(
  algorithmId: string,
  cats: FaultCategoriesResponse | null | undefined,
): FaultCategory {
  const map = cats?.categories ?? DEFAULT_FAULT_CATEGORIES.categories;
  return map[algorithmId] ?? "actionable";
}
