/** Deep-link + inline-validation targets on Setup (SAP-style field pointing). */

export type SetupFieldKey =
  | "timestamp"
  | "plant_name"
  | "ac_capacity_mw"
  | "dc_capacity_mwp"
  | "inverter_capacity_kw"
  | "tariff_inr_per_kwh"
  | "architecture"
  | `canonical:${string}`;

export const SETUP_FIELD_LABELS: Record<string, string> = {
  timestamp: "Timestamp",
  plant_name: "Plant name",
  ac_capacity_mw: "AC capacity",
  dc_capacity_mwp: "DC capacity",
  inverter_capacity_kw: "Inverter rating",
  tariff_inr_per_kwh: "Tariff",
  architecture: "Architecture",
  "canonical:ac_power_kw": "AC power mapping",
  "canonical:poa_w_m2": "POA irradiance mapping",
  "canonical:ghi_w_m2": "GHI irradiance mapping",
  "canonical:dc_power_kw": "DC power mapping",
  "canonical:dc_current_a": "DC current mapping",
  "canonical:dc_voltage_v": "DC voltage mapping",
};

export function setupFieldDomId(key: SetupFieldKey | string): string {
  return `setup-field-${key.replace(/[^a-zA-Z0-9_:-]/g, "_")}`;
}

export function parseSetupFocus(hash: string, search: string): {
  section?: "mapping" | "plant" | "architecture";
  field?: string;
} {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const focus = params.get("focus");
  if (focus) {
    if (focus.startsWith("plant.")) {
      return { section: "plant", field: focus.slice("plant.".length) };
    }
    if (focus.startsWith("column:")) {
      return { section: "mapping", field: `column:${focus.slice("column:".length)}` };
    }
    if (focus.startsWith("canonical:")) {
      return { section: "mapping", field: focus };
    }
    if (focus === "architecture" || focus === "mapping" || focus === "plant") {
      return { section: focus };
    }
  }

  const raw = (hash || "").replace(/^#/, "");
  if (!raw) return {};
  const [sectionPart, ...rest] = raw.split("&");
  const section =
    sectionPart === "mapping" || sectionPart === "plant" || sectionPart === "architecture"
      ? sectionPart
      : undefined;
  let field: string | undefined;
  for (const part of rest) {
    const [k, v] = part.split("=");
    if (k === "field" && v) field = decodeURIComponent(v);
  }
  // Also support #mapping&field=ac_power_kw meaning canonical field
  if (field && !field.includes(":") && section === "mapping") {
    field = `canonical:${field}`;
  }
  if (field && !field.includes(":") && section === "plant") {
    // keep as plant field key
  }
  return { section, field };
}

export function focusSetupField(key: string, opts?: { flashMs?: number }) {
  const id = setupFieldDomId(key);
  const el = document.getElementById(id);
  if (!el) {
    // Fall back to section anchors
    const section =
      key.startsWith("canonical:") || key.startsWith("column:") || key === "timestamp"
        ? "mapping"
        : key === "architecture"
          ? "architecture"
          : "plant";
    document.getElementById(section)?.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("setup-field-flash");
  const focusable = el.querySelector<HTMLElement>("input, select, button, textarea");
  window.setTimeout(() => focusable?.focus({ preventScroll: true }), 120);
  window.setTimeout(() => el.classList.remove("setup-field-flash"), opts?.flashMs ?? 2200);
}
