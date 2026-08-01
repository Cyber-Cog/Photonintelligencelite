import { useEffect, useMemo, useState } from "react";
import { ApiError, getDataPreview } from "@/api/client";
import { AppModal } from "@/components/ui/AppModal";
import { Badge } from "@/components/ui/Badge";
import { Spinner } from "@/components/ui/Spinner";
import { CANONICAL_FIELD_OPTIONS, inferMappingHierarchyLevel } from "@/lib/canonicalFields";
import {
  equipmentHintFromHeader,
  HIERARCHY_LEVEL_OPTIONS,
  similarColumnNames,
} from "@/lib/mappingExcel";
import type { ColumnMappingSuggestion, DataPreviewResponse } from "@/types";

const PREVIEW_LIMIT = 40;

type Props = {
  jobId: string;
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

function suggestionFor(suggestions: ColumnMappingSuggestion[], col: string): ColumnMappingSuggestion | undefined {
  return suggestions.find((s) => s.column_name === col);
}

export function ExcelMappingModal({
  jobId,
  suggestions,
  mapping,
  levels,
  onApply,
  onClose,
}: Props) {
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
  const [preview, setPreview] = useState<DataPreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(true);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [activeCol, setActiveCol] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setPreviewLoading(true);
    setPreviewError(null);
    getDataPreview(jobId, offset, PREVIEW_LIMIT)
      .then((res) => {
        if (cancelled) return;
        setPreview(res);
      })
      .catch((err) => {
        if (cancelled) return;
        setPreviewError(err instanceof ApiError ? err.message : "Could not load spreadsheet preview.");
      })
      .finally(() => {
        if (!cancelled) setPreviewLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, offset]);

  const companionFields = useMemo(
    () => new Set(Object.values(draftMap).filter((v) => v && v !== "ignore")),
    [draftMap],
  );

  const allNames = useMemo(() => {
    if (preview?.columns?.length) return preview.columns;
    return suggestions.map((s) => s.column_name);
  }, [preview, suggestions]);

  const filteredCols = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return allNames;
    return allNames.filter((name) => {
      const field = draftMap[name] ?? "";
      const hint = equipmentHintFromHeader(name);
      return (
        name.toLowerCase().includes(q) ||
        field.toLowerCase().includes(q) ||
        hint.toLowerCase().includes(q)
      );
    });
  }, [allNames, query, draftMap]);

  const colIndex = useMemo(() => {
    const map = new Map<string, number>();
    (preview?.columns ?? []).forEach((c, i) => map.set(c, i));
    return map;
  }, [preview]);

  const toggleSelect = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const selectFiltered = () => setSelected(new Set(filteredCols));
  const clearSelected = () => setSelected(new Set());

  const setField = (col: string, field: string) => {
    setDraftMap((m) => ({ ...m, [col]: field }));
    setActiveCol(col);
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
    setActiveCol(col);
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

  const activeSuggestion = activeCol ? suggestionFor(suggestions, activeCol) : undefined;
  const activeField = activeCol ? draftMap[activeCol] ?? "ignore" : "ignore";
  const activeLevel =
    activeCol && activeField !== "ignore"
      ? draftLevels[activeCol] ||
        inferMappingHierarchyLevel(activeField, companionFields, activeCol) ||
        ""
      : "";
  const similarCount = activeCol ? similarColumnNames(activeCol, allNames).length : 0;
  const totalRows = preview?.total_rows ?? 0;
  const pageEnd = Math.min(offset + PREVIEW_LIMIT, totalRows);

  return (
    <AppModal
      titleId="excel-mapping-title"
      eyebrow="Excel mapping"
      title="Spreadsheet mapping"
      description="Browse real cell values like Excel. Map each column header to a canonical field and hierarchy level, then Apply."
      onClose={onClose}
      maxWidthClass="max-w-[96vw] sm:max-w-7xl"
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
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
          <label className="min-w-[12rem] flex-1 text-xs">
            <span className="mb-1 block font-medium text-stone-500">Search columns</span>
            <input
              className="input w-full text-sm"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Header, field, ICR/INV/SCB…"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-ghost text-xs" onClick={selectFiltered}>
              Select filtered ({filteredCols.length})
            </button>
            <button type="button" className="btn-ghost text-xs" onClick={clearSelected}>
              Clear selection
            </button>
          </div>
          <p className="text-xs text-stone-500 sm:ml-auto">
            {previewLoading && !preview ? (
              <span className="inline-flex items-center gap-1.5">
                <Spinner className="h-3.5 w-3.5" /> Loading rows…
              </span>
            ) : totalRows > 0 ? (
              <>
                Rows {(offset + 1).toLocaleString()}–{pageEnd.toLocaleString()} of{" "}
                <span className="font-semibold tabular-nums">{totalRows.toLocaleString()}</span>
                {previewLoading ? <span className="ml-1 text-stone-400">Updating…</span> : null}
              </>
            ) : previewError ? null : (
              "No preview rows"
            )}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-secondary !px-2.5 !py-1 text-[11px]"
              disabled={offset === 0 || previewLoading}
              onClick={() => setOffset((o) => Math.max(0, o - PREVIEW_LIMIT))}
            >
              Prev
            </button>
            <button
              type="button"
              className="btn-secondary !px-2.5 !py-1 text-[11px]"
              disabled={offset + PREVIEW_LIMIT >= totalRows || previewLoading || totalRows === 0}
              onClick={() => setOffset((o) => o + PREVIEW_LIMIT)}
            >
              Next
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

        {activeCol ? (
          <div className="flex flex-col gap-2 rounded-lg border border-brand-200/80 bg-brand-50/40 p-3 dark:border-brand-900 dark:bg-brand-950/30 sm:flex-row sm:flex-wrap sm:items-end">
            <div className="min-w-0 flex-1">
              <p className="text-[10px] font-bold uppercase tracking-wide text-brand-700 dark:text-brand-300">
                Active column
              </p>
              <p className="truncate font-medium text-stone-800 dark:text-stone-100" title={activeCol}>
                {activeCol}
              </p>
              <p className="text-xs text-stone-500">{equipmentHintFromHeader(activeCol)}</p>
            </div>
            <label className="text-xs">
              <span className="mb-1 block text-stone-500">Canonical</span>
              <select
                className="input max-w-[12rem] text-sm"
                value={activeField}
                onChange={(e) => setField(activeCol, e.target.value)}
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
                className="input max-w-[9rem] text-sm"
                value={activeLevel}
                disabled={activeField === "ignore"}
                onChange={(e) => setLevel(activeCol, e.target.value)}
              >
                <option value="">—</option>
                {HIERARCHY_LEVEL_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            {activeSuggestion ? (
              <Badge
                tone={
                  activeField === "ignore"
                    ? "neutral"
                    : statusLabel(activeSuggestion, activeField) === "Auto"
                      ? "success"
                      : statusLabel(activeSuggestion, activeField) === "Needs mapping"
                        ? "danger"
                        : "warning"
                }
              >
                {statusLabel(activeSuggestion, activeField)}
              </Badge>
            ) : null}
            <button
              type="button"
              className="btn-ghost whitespace-nowrap px-1 py-0.5 text-[11px]"
              disabled={similarCount === 0}
              title="Apply this field + level to all similar metric columns"
              onClick={() => fillSimilar(activeCol)}
            >
              Fill similar ({similarCount})
            </button>
            <label className="flex cursor-pointer items-center gap-1.5 pb-1 text-xs text-stone-600 dark:text-stone-300">
              <input
                type="checkbox"
                checked={selected.has(activeCol)}
                onChange={() => toggleSelect(activeCol)}
              />
              Selected for bulk
            </label>
          </div>
        ) : (
          <p className="text-xs text-stone-500">Click a column header to edit its mapping.</p>
        )}

        {previewError ? (
          <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
            {previewError} You can still map from detected headers below.
          </p>
        ) : null}

        <div className="data-table-shell -mx-1 max-h-[min(52vh,28rem)] overflow-auto rounded-lg border border-stone-200 dark:border-stone-700">
          {filteredCols.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-stone-500">No columns match this search.</p>
          ) : (
            <table className="data-table !min-w-full text-[11px]">
              <thead className="sticky top-0 z-20">
                <tr>
                  <th className="sticky left-0 z-30 !w-10 !min-w-[2.5rem] !bg-stone-100 !px-1.5 dark:!bg-stone-800">
                    #
                  </th>
                  {filteredCols.map((col) => {
                    const field = draftMap[col] ?? "ignore";
                    const sug = suggestionFor(suggestions, col);
                    const mapped = field && field !== "ignore";
                    const isActive = activeCol === col;
                    return (
                      <th
                        key={col}
                        className={`!min-w-[9.5rem] !max-w-[14rem] cursor-pointer !whitespace-normal !px-1.5 !py-1.5 align-top ${
                          isActive
                            ? "!bg-brand-100 ring-1 ring-inset ring-brand-400 dark:!bg-brand-950/80"
                            : selected.has(col)
                              ? "!bg-amber-50 dark:!bg-amber-950/40"
                              : ""
                        }`}
                        title={col}
                        onClick={() => setActiveCol(col)}
                      >
                        <div className="flex items-start gap-1">
                          <input
                            type="checkbox"
                            className="mt-0.5"
                            checked={selected.has(col)}
                            onChange={(e) => {
                              e.stopPropagation();
                              toggleSelect(col);
                            }}
                            onClick={(e) => e.stopPropagation()}
                            aria-label={`Select ${col}`}
                          />
                          <div className="min-w-0 flex-1">
                            <p className="truncate font-semibold text-stone-800 dark:text-stone-100">{col}</p>
                            <select
                              className="input mt-1 w-full !py-0.5 text-[10px]"
                              value={field}
                              onClick={(e) => e.stopPropagation()}
                              onChange={(e) => {
                                e.stopPropagation();
                                setField(col, e.target.value);
                              }}
                            >
                              {CANONICAL_FIELD_OPTIONS.map((o) => (
                                <option key={o.value} value={o.value}>
                                  {o.label}
                                </option>
                              ))}
                            </select>
                            <select
                              className="input mt-1 w-full !py-0.5 text-[10px]"
                              value={
                                mapped
                                  ? draftLevels[col] ||
                                    inferMappingHierarchyLevel(field, companionFields, col) ||
                                    ""
                                  : ""
                              }
                              disabled={!mapped}
                              onClick={(e) => e.stopPropagation()}
                              onChange={(e) => {
                                e.stopPropagation();
                                setLevel(col, e.target.value);
                              }}
                            >
                              <option value="">Level —</option>
                              {HIERARCHY_LEVEL_OPTIONS.map((o) => (
                                <option key={o.value} value={o.value}>
                                  {o.label}
                                </option>
                              ))}
                            </select>
                            {sug ? (
                              <span className="mt-0.5 inline-block text-[9px] font-medium uppercase tracking-wide text-stone-400">
                                {statusLabel(sug, field)}
                              </span>
                            ) : null}
                          </div>
                        </div>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {(preview?.rows ?? []).length === 0 && !previewLoading ? (
                  <tr>
                    <td
                      colSpan={filteredCols.length + 1}
                      className="px-3 py-6 text-center text-stone-500"
                    >
                      {previewError
                        ? "Preview unavailable — map columns from headers above."
                        : "No data rows to show yet."}
                    </td>
                  </tr>
                ) : (
                  (preview?.rows ?? []).map((row, ri) => (
                    <tr
                      key={ri}
                      className="border-b border-stone-100 odd:bg-white even:bg-stone-50/80 hover:bg-brand-50/30 dark:border-stone-800 dark:odd:bg-stone-900 dark:even:bg-stone-950/60 dark:hover:bg-stone-800/50"
                    >
                      <td className="sticky left-0 z-10 !bg-inherit !px-1.5 !py-0.5 font-mono text-[10px] text-stone-400">
                        {offset + ri + 1}
                      </td>
                      {filteredCols.map((col) => {
                        const idx = colIndex.get(col);
                        const val = idx == null ? "" : row[idx];
                        const empty = val === "" || val == null;
                        const isActive = activeCol === col;
                        return (
                          <td
                            key={col}
                            className={`max-w-[14rem] truncate whitespace-nowrap !px-1.5 !py-0.5 font-mono text-[10px] tabular-nums text-stone-700 dark:text-stone-300 ${
                              isActive ? "bg-brand-50/60 dark:bg-brand-950/40" : ""
                            }`}
                            title={empty ? undefined : String(val)}
                            onClick={() => setActiveCol(col)}
                          >
                            {empty ? (
                              <span className="text-stone-300 dark:text-stone-600">–</span>
                            ) : (
                              String(val)
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </AppModal>
  );
}
