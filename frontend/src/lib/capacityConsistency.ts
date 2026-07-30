/** Client-side plant ↔ architecture capacity consistency (mirrors backend checks). */

import type { EditableInverter } from "@/lib/equipmentStructure";

export interface CapacityConsistencyWarning {
  code: string;
  message: string;
  field?: "inverter_capacity_kw" | "ac_capacity_mw" | "dc_capacity_mwp" | "architecture";
}

const RATING_ABS_TOLERANCE_KW = 0.5;
const CAPACITY_TOLERANCE_PCT = 5;

function ratingsDiffer(a: number, b: number): boolean {
  return Math.abs(a - b) > RATING_ABS_TOLERANCE_KW;
}

export function checkSetupCapacityConsistency(opts: {
  inverterCapacityKw: number;
  acCapacityMw: number;
  dcCapacityMwp: number;
  equipment: EditableInverter[];
  importedInverterCapacityKw?: number | null;
  importedAcCapacityMw?: number | null;
  importedDcCapacityMwp?: number | null;
}): CapacityConsistencyWarning[] {
  const warnings: CapacityConsistencyWarning[] = [];
  const { inverterCapacityKw, acCapacityMw, dcCapacityMwp, equipment } = opts;

  const ratings = equipment
    .filter((e) => e.inverter_id.trim() && e.rated_kw != null && e.rated_kw > 0)
    .map((e) => ({ id: e.inverter_id.trim(), kw: e.rated_kw as number }));

  if (inverterCapacityKw > 0 && ratings.length > 0) {
    const mismatched = ratings.filter((r) => ratingsDiffer(r.kw, inverterCapacityKw));
    if (mismatched.length > 0) {
      const sample = mismatched
        .slice(0, 4)
        .map((r) => `${r.id}=${r.kw} kW`)
        .join(", ");
      const more = mismatched.length > 4 ? ` (+${mismatched.length - 4} more)` : "";
      warnings.push({
        code: "inverter_rating_mismatch",
        field: "inverter_capacity_kw",
        message:
          `Default inverter rating is ${inverterCapacityKw} kW but architecture ratings differ (${sample}${more}). ` +
          `Clipping prefers per-inverter ratings — align values or use “Apply default rating to all”.`,
      });
    }
  }

  const importedDefault = opts.importedInverterCapacityKw;
  if (
    importedDefault != null &&
    importedDefault > 0 &&
    inverterCapacityKw > 0 &&
    ratingsDiffer(inverterCapacityKw, importedDefault)
  ) {
    warnings.push({
      code: "imported_inverter_rating_mismatch",
      field: "inverter_capacity_kw",
      message:
        `Architecture pack/Excel inverter rating was ${importedDefault} kW but Plant details default is now ${inverterCapacityKw} kW.`,
    });
  }

  if (ratings.length > 0 && acCapacityMw > 0) {
    const summedKw = ratings.reduce((s, r) => s + r.kw, 0);
    const declaredKw = acCapacityMw * 1000;
    const drift = (Math.abs(summedKw - declaredKw) / declaredKw) * 100;
    if (drift > CAPACITY_TOLERANCE_PCT) {
      warnings.push({
        code: "ac_capacity_mismatch",
        field: "ac_capacity_mw",
        message:
          `Summed inverter AC ${summedKw.toFixed(1)} kW differs from plant AC ${(declaredKw).toFixed(1)} kW ` +
          `by more than ${CAPACITY_TOLERANCE_PCT}%.`,
      });
    }
  }

  const importedAc = opts.importedAcCapacityMw;
  if (importedAc != null && importedAc > 0 && acCapacityMw > 0) {
    const drift = (Math.abs(acCapacityMw - importedAc) / importedAc) * 100;
    if (drift > CAPACITY_TOLERANCE_PCT) {
      warnings.push({
        code: "imported_ac_capacity_mismatch",
        field: "ac_capacity_mw",
        message: `Plant AC is ${acCapacityMw} MW but architecture pack/Excel had ${importedAc} MW.`,
      });
    }
  }

  const importedDc = opts.importedDcCapacityMwp;
  if (importedDc != null && importedDc > 0 && dcCapacityMwp > 0) {
    const drift = (Math.abs(dcCapacityMwp - importedDc) / importedDc) * 100;
    if (drift > CAPACITY_TOLERANCE_PCT) {
      warnings.push({
        code: "imported_dc_capacity_mismatch",
        field: "dc_capacity_mwp",
        message: `Plant DC is ${dcCapacityMwp} MWp but architecture pack/Excel had ${importedDc} MWp.`,
      });
    }
  }

  return warnings;
}
