import { useMemo, useState } from "react";
import { AppModal } from "@/components/ui/AppModal";
import { Badge } from "@/components/ui/Badge";
import { CANONICAL_FIELD_OPTIONS, inferMappingHierarchyLevel } from "@/lib/canonicalFields";
import {
  equipmentHintFromHeader,
  HIERARCHY_LEVEL_OPTIONS,
  similarColumnNames,
} from "@/lib/mappingExcel";
import type { ColumnMappingSuggestion } from "@/types";

type Props = {
  suggestions: ColumnMappingSuggestion[];
  mapping: Record<string, string>;
  levels: Record<string, string>;
  onApply: (next: { mapping: Record<string, string>; levels: Record<string, string> }) => void;
  onClose: () => void;
};

function statusLabel(s: ColumnMappingSuggestion, field: string | undefined): string {
  if (!field || field === "ignore") return "Ignore";
  if (s.band === "auto" && s.canonical_field === field) return "Auto";
  if (s.band === "confirm") return "Confirm";
  return field ? "Mapped" : "Needs mapping";
}

export function ExcelMappingModal({ suggestions, mapping, levels, onApply, onClose }: Props) {
  const [draftMap, setDraftMap] = useState<Record<string, string>>(() => ({ ...mapping }));
  const [draftLevels, setDraftLevels] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = { ...levels };
    const companions = new Set(Object.values(mapping).filter((v) => v && v !== "ignore"));
    for (const s of suggestions) {
      if (init[s.column_name]) continue;
      const field = mapping[s.column_name] ?? s.canonical_field ?? "ignore";
      const inferred =
        inferMappingHierarchyLevel(field, companions, s.column_name) || s.hierarchy_level || "";
      if (inferred) init[s.column_name] = inferred;
    }
    return init;
  });
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkField, setBulkField] = useState("dc_current_a");
  const [bulkLevel, setBulkLevel] = useState("scb");
  const [sortKey, setSortKey] = useState<"name" | "status" | "level">("name");

  const companionFields = useMemo(
    () => new Set(Object.values(draftMap).filter((v) => v && v !== "ignore")),
    [draftMap],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let rows = suggestions;
    if (q) {
      rows = rows.filter(
        (s) =>
          s.column_name.toLowerCase().includes(q) ||
          (draftMap[s.column_name] ?? "").toLowerCase().includes(q) ||
          equipmentHintFromHeader(s.column_name).toLowerCase().includes(q),
      );
    }
    const sorted = [...rows];
    sorted.sort((a, b) => {
      if (sortKey === "level") {
        return (draftLevels[a.column_name] ?? "").localeCompare(draftLevels[b.column_name] ?? "");
      }
      if (sortKey === "status") {
        return statusLabel(a, draftMap[a.column_name]).localeCompare(
          statusLabel(b, draftMap[b.column_name]),
        );
      }
      return a.column_name.localeCompare(b.column_name);
    });
    return sorted;
  }, [suggestions, query, draftMap, draftLevels, sortKey]);

  const allNames = useMemo(() => suggestions.map((s) => s.column_name), [suggestions]);

  const toggleSelect = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const selectFiltered = () => {
    setSelected(new Set(filtered.map((s) => s.column_name)));
  };

  const clearSelected = () => setSelected(new Set());

  const setField = (col: string, field: string) => {
    setDraftMap((m) => ({ ...m, [col]: field }));
    if (field === "ignore") {
      setDraftLevels((lv) => {
        const next = { ...lv };
        delete next[col];
        return next;
      });
      return;
    }
    const inferred = inferMappingHierarchyLevel(field, companionFields, col);
    if (inferred) {
      setDraftLevels((lv) => ({ ...lv, [col]: inferred }));
    }
  };

  const setLevel = (col: string, level: string) => {
    setDraftLevels((lv) => ({ ...lv, [col]: level }));
  };

  const fillSimilar = (col: string) => {
    const field = draftMap[col] ?? "ignore";
    const level = draftLevels[col] ?? "";
    const siblings = similarColumnNames(col, allNames);
    setDraftMap((m) => {
      const next = { ...m };
      for (const s of siblings) next[s] = field;
      return next;
    });
    if (level) {
      setDraftLevels((lv) => {
        const next = { ...lv };
        for (const s of siblings) next[s] = level;
        return next;
      });
    }
  };

  const applyBulkToSelected = () => {
    if (selected.size === 0) return;
    setDraftMap((m) => {
      const next = { ...m };
      for (const col of selected) next[col] = bulkField;
      return next;
    });
    setDraftLevels((lv) => {
      const next = { ...lv };
      for (const col of selected) {
        if (bulkField === "ignore") delete next[col];
        else next[col] = bulkLevel;
      }
      return next;
    });
  };

  return (
    <AppModal
      titleId="excel-mapping-title"
      eyebrow="Excel mapping"
      title="Map headers by equipment"
      description="Spreadsheet view — set canonical field and hierarchy level. Fill similar columns like Excel. Saves into the job mapping the way rows land in the DB."
      onClose={onClose}
      maxWidthClass="max-w-6xl"
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={() => onApply({ mapping: draftMap, levels: draftLevels })}
          >
            Apply to mapping
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
        <label className="min-w-[12rem] flex-1 text-xs">
          <span className="mb-1 block font-medium text-stone-500">Search</span>
          <input
            className="input w-full text-sm"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Header, field, ICR/INV/SCB…"
          />
        </label>
        <label className="text-xs">
          <span className="mb-1 block font-medium text-stone-500">Sort</span>
          <select
            className="input text-sm"
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as typeof sortKey)}
          >
            <option value="name">Header</option>
            <option value="level">Level</option>
            <option value="status">Status</option>
          </select>
        </label>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-ghost text-xs" onClick={selectFiltered}>
            Select filtered ({filtered.length})
          </button>
          <button type="button" className="btn-ghost text-xs" onClick={clearSelected}>
            Clear selection
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-2 rounded-lg border border-stone-200 bg-stone-50/80 p-3 dark:border-stone-700 dark:bg-stone-800/40 sm:flex-row sm:flex-wrap sm:items-end">
        <p className="w-full text-[10px] font-bold uppercase tracking-wide text-stone-400">
          Bulk apply to {selected.size} selected
        </p>
        <label className="text-xs">
          <span className="mb-1 block text-stone-500">Canonical field</span>
          <select
            className="input text-sm"
            value={bulkField}
            onChange={(e) => setBulkField(e.target.value)}
          >
            {CANONICAL_FIELD_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs">
          <span className="mb-1 block text-stone-500">Level</span>
          <select
            className="input text-sm"
            value={bulkLevel}
            onChange={(e) => setBulkLevel(e.target.value)}
          >
            {HIERARCHY_LEVEL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="btn-secondary text-xs"
          disabled={selected.size === 0}
          onClick={applyBulkToSelected}
        >
          Apply to selected
        </button>
      </div>

      <div className="-mx-1 overflow-x-auto">
        <table className="w-full min-w-[56rem] border-collapse text-left text-xs">
          <thead>
            <tr className="border-b border-stone-200 text-[10px] uppercase tracking-wide text-stone-400 dark:border-stone-700">
              <th className="w-8 px-2 py-2">
                <span className="sr-only">Select</span>
              </th>
              <th className="px-2 py-2">Source header</th>
              <th className="px-2 py-2">Equipment → DB</th>
              <th className="px-2 py-2">Canonical</th>
              <th className="px-2 py-2">Level</th>
              <th className="px-2 py-2">Status</th>
              <th className="px-2 py-2">Fill</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s) => {
              const field = draftMap[s.column_name] ?? "ignore";
              const level =
                draftLevels[s.column_name] ||
                inferMappingHierarchyLevel(field, companionFields, s.column_name) ||
                "";
              const hint = equipmentHintFromHeader(s.column_name);
              const similarCount = similarColumnNames(s.column_name, allNames).length;
              return (
                <tr
                  key={s.column_name}
                  className="border-b border-stone-100 hover:bg-stone-50/80 dark:border-stone-800 dark:hover:bg-stone-800/40"
                >
                  <td className="px-2 py-1.5 align-middle">
                    <input
                      type="checkbox"
                      checked={selected.has(s.column_name)}
                      onChange={() => toggleSelect(s.column_name)}
                      aria-label={`Select ${s.column_name}`}
                    />
                  </td>
                  <td className="max-w-[18rem] px-2 py-1.5 align-middle">
                    <p className="truncate font-medium text-stone-800 dark:text-stone-100" title={s.column_name}>
                      {s.column_name}
                    </p>
                  </td>
                  <td className="px-2 py-1.5 align-middle text-stone-600 dark:text-stone-300">
                    {hint}
                  </td>
                  <td className="px-2 py-1.5 align-middle">
                    <select
                      className="input max-w-[11rem] py-1 text-xs"
                      value={field}
                      onChange={(e) => setField(s.column_name, e.target.value)}
                    >
                      {CANONICAL_FIELD_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-2 py-1.5 align-middle">
                    <select
                      className="input max-w-[9rem] py-1 text-xs"
                      value={level}
                      disabled={field === "ignore"}
                      onChange={(e) => setLevel(s.column_name, e.target.value)}
                    >
                      <option value="">—</option>
                      {HIERARCHY_LEVEL_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-2 py-1.5 align-middle">
                    <Badge
                      tone={
                        field === "ignore"
                          ? "neutral"
                          : statusLabel(s, field) === "Auto"
                            ? "success"
                            : statusLabel(s, field) === "Needs mapping"
                              ? "danger"
                              : "warning"
                      }
                    >
                      {statusLabel(s, field)}
                    </Badge>
                  </td>
                  <td className="px-2 py-1.5 align-middle">
                    <button
                      type="button"
                      className="btn-ghost whitespace-nowrap px-1 py-0.5 text-[11px]"
                      disabled={similarCount === 0}
                      title="Apply this field + level to all similar metric columns"
                      onClick={() => fillSimilar(s.column_name)}
                    >
                      Fill similar ({similarCount})
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 ? (
          <p className="px-2 py-6 text-center text-sm text-stone-500">No columns match this search.</p>
        ) : null}
      </div>
    </AppModal>
  );
}
