/** Helpers for Excel-mode column mapping (equipment hints + similar-column fill). */

export const HIERARCHY_LEVEL_OPTIONS: { value: string; label: string }[] = [
  { value: "plant", label: "Plant / WMS" },
  { value: "icr", label: "ICR" },
  { value: "inverter", label: "Inverter" },
  { value: "scb", label: "SCB / SMB" },
  { value: "string", label: "String" },
  { value: "equipment", label: "Equipment (row)" },
];

/** How a wide header will land in DB after melt / standardize. */
export function equipmentHintFromHeader(columnName: string): string {
  const n = columnName.trim();
  if (!n) return "—";
  const icr = n.match(/ICR[\s_\-]?(\d+)/i)?.[1];
  const inv = n.match(/(?:INV(?:ERTER)?[\s_\-\.]*)(\d+)/i)?.[1];
  const scb = n.match(/(?:SCB|SMB)[\s_\-]?(\d+)/i)?.[1];
  const str = n.match(/(?:STR(?:ING)?|CH(?:ANNEL)?)[\s_\-]?(\d+)/i)?.[1];
  const parts: string[] = [];
  if (icr) parts.push(`ICR${icr}`);
  if (inv) parts.push(`INV-${String(inv).padStart(2, "0")}`);
  if (scb) parts.push(`SCB-${String(scb).padStart(2, "0")}`);
  if (str) parts.push(`STR-${String(str).padStart(2, "0")}`);
  if (parts.length) return parts.join(" · ");
  if (/^(timestamp|planttimestamp|date|time)/i.test(n)) return "Plant time";
  if (/\b(poa|ghi|irradiance|wms)\b/i.test(n)) return "Plant / WMS";
  return "—";
}

/** Metric leaf used to group similar wide columns for fill-down. */
export function metricLeafKey(columnName: string): string {
  let n = columnName.trim().toLowerCase();
  n = n
    .replace(/essp[_\s]?\d*mw/gi, "")
    .replace(/icr[\s_\-]?\d+/gi, "")
    .replace(/inv(?:erter)?[\s_\-\.]*\d+/gi, "")
    .replace(/(?:scb|smb)[\s_\-]?\d+/gi, "")
    .replace(/(?:str(?:ing)?|ch(?:annel)?)[\s_\-]?\d+/gi, "")
    .replace(/\s+/g, " ")
    .trim();
  return n || columnName.trim().toLowerCase();
}

export function similarColumnNames(source: string, allNames: string[]): string[] {
  const key = metricLeafKey(source);
  return allNames.filter((n) => n !== source && metricLeafKey(n) === key);
}
