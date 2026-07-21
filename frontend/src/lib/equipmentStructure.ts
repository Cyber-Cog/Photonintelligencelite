import type { ArchitectureEntry, InverterStructure } from "@/types";

/** Editable inverter node used by Setup — ratings are optional (null = not available). */
export interface EditableScb {
  scb_id: string;
  strings_per_scb: number | null;
  strings_detected: boolean;
}

export interface EditableInverter {
  inverter_id: string;
  rated_kw: number | null;
  scbs: EditableScb[];
}

export interface StructureSummary {
  inverterCount: number;
  scbCount: number;
  stringCount: number | null;
  ratedCount: number;
}

export function fromDetected(
  inverters: InverterStructure[],
  ratings?: Record<string, number | null | undefined>,
): EditableInverter[] {
  return inverters.map((inv) => ({
    inverter_id: inv.inverter_id,
    rated_kw: ratings?.[inv.inverter_id] ?? null,
    scbs: inv.scbs.map((s) => ({
      scb_id: s.scb_id,
      strings_per_scb: s.strings_per_scb,
      strings_detected: s.strings_detected,
    })),
  }));
}

export function fromPatternPayload(inverters: EditableInverter[]): EditableInverter[] {
  return inverters.map((inv) => ({
    inverter_id: inv.inverter_id,
    rated_kw: inv.rated_kw ?? null,
    scbs: (inv.scbs || []).map((s) => ({
      scb_id: s.scb_id,
      strings_per_scb: s.strings_per_scb ?? null,
      strings_detected: Boolean(s.strings_detected),
    })),
  }));
}

export function emptyInverter(index: number): EditableInverter {
  const n = String(index).padStart(2, "0");
  return {
    inverter_id: `INV-${n}`,
    rated_kw: null,
    scbs: [{ scb_id: `INV-${n}-SCB-01`, strings_per_scb: null, strings_detected: false }],
  };
}

export function summarizeEquipment(equipment: EditableInverter[]): StructureSummary {
  const inverterCount = equipment.filter((e) => e.inverter_id.trim()).length;
  let scbCount = 0;
  let stringSum = 0;
  let stringKnown = 0;
  let ratedCount = 0;
  for (const inv of equipment) {
    if (!inv.inverter_id.trim()) continue;
    if (inv.rated_kw != null && inv.rated_kw > 0) ratedCount += 1;
    for (const scb of inv.scbs) {
      if (!scb.scb_id.trim()) continue;
      scbCount += 1;
      if (scb.strings_per_scb != null && scb.strings_per_scb > 0) {
        stringSum += scb.strings_per_scb;
        stringKnown += 1;
      }
    }
  }
  return {
    inverterCount,
    scbCount,
    stringCount: stringKnown > 0 ? stringSum : null,
    ratedCount,
  };
}

/** Generate INV-01 … INV-N for pattern apply when none exist yet. */
export function generateInverterIds(count: number, prefix = "INV"): string[] {
  const n = Math.max(1, Math.min(count, 2000));
  return Array.from({ length: n }, (_, i) => `${prefix}-${String(i + 1).padStart(2, "0")}`);
}

/**
 * Short avatar label for equipment IDs (accordion badges, chips).
 * Prefer the last hyphen segment (`1` from INV-1, `01` from INV-01).
 * Never return a leading-hyphen fragment like `-1` from naive slice(-2).
 */
export function equipmentBadgeLabel(id: string, maxLen = 3): string {
  const trimmed = id.trim();
  if (!trimmed) return "?";

  const parts = trimmed.split("-").filter((p) => p.length > 0);
  const last = parts.length > 0 ? parts[parts.length - 1]! : trimmed;

  if (last.length > 0 && last.length <= maxLen) return last;
  if (/^\d+$/.test(last)) return last.slice(-maxLen);

  const first = parts[0] ?? trimmed;
  if (first.length > 0 && first.length <= maxLen) return first;

  const compact = trimmed.replace(/^-+/, "");
  return (compact || "?").slice(0, maxLen);
}

export function buildRatingsAndArchitecture(
  equipment: EditableInverter[],
  modulesPerString: number | null = null,
): {
  equipment_ratings: Record<string, number>;
  architecture: Record<string, ArchitectureEntry>;
  strings_per_scb_fallback: number | null;
} {
  const equipment_ratings: Record<string, number> = {};
  const architecture: Record<string, ArchitectureEntry> = {};
  const stringCounts: number[] = [];

  for (const inv of equipment) {
    const invId = inv.inverter_id.trim();
    if (!invId) continue;
    if (inv.rated_kw != null && inv.rated_kw > 0) {
      equipment_ratings[invId] = inv.rated_kw;
    }
    for (const scb of inv.scbs) {
      const scbId = scb.scb_id.trim();
      if (!scbId) continue;
      const entry: ArchitectureEntry = { inverter_id: invId };
      if (scb.strings_per_scb != null && scb.strings_per_scb > 0) {
        entry.strings_per_scb = scb.strings_per_scb;
        stringCounts.push(scb.strings_per_scb);
      }
      if (modulesPerString != null && modulesPerString > 0) {
        entry.modules_per_string = modulesPerString;
      }
      architecture[scbId] = entry;
    }
  }

  let strings_per_scb_fallback: number | null = null;
  if (stringCounts.length > 0) {
    const freq = new Map<number, number>();
    for (const c of stringCounts) freq.set(c, (freq.get(c) ?? 0) + 1);
    strings_per_scb_fallback = [...freq.entries()].sort((a, b) => b[1] - a[1])[0][0];
  }

  return { equipment_ratings, architecture, strings_per_scb_fallback };
}
