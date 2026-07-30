import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError, dataExportUrl, getDataPreview } from "@/api/client";
import { JobNav } from "@/components/JobNav";
import { ErrorState } from "@/components/ui/ErrorState";
import { Spinner } from "@/components/ui/Spinner";
import type { DataPreviewResponse } from "@/types";

const PAGE = 75;

function useDebounced<T>(value: T, ms = 250): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

/** API stores UTC as `YYYY-MM-DDTHH:MM:SS` — datetime-local wants local-shaped string. */
function toInputValue(iso: string | null | undefined): string {
  if (!iso) return "";
  const cleaned = iso.replace(" ", "T").slice(0, 16);
  return cleaned;
}

function fromInputValue(local: string): string | null {
  if (!local.trim()) return null;
  // Treat datetime-local as UTC wall time for SCADA browsing (matches canonical timestamp_utc).
  return local.length === 16 ? `${local}:00` : local;
}

function isTsCol(name: string): boolean {
  const n = name.toLowerCase();
  return n.includes("time") || n.includes("date") || n === "timestamp_utc";
}

export function DataPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [data, setData] = useState<DataPreviewResponse | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [columnFilter, setColumnFilter] = useState("");
  const [valueSearch, setValueSearch] = useState("");
  const [hideEmpty, setHideEmpty] = useState(false);
  const [startInput, setStartInput] = useState("");
  const [endInput, setEndInput] = useState("");
  const [appliedStart, setAppliedStart] = useState<string | null>(null);
  const [appliedEnd, setAppliedEnd] = useState<string | null>(null);
  const [spanMin, setSpanMin] = useState<string | null>(null);
  const [spanMax, setSpanMax] = useState<string | null>(null);
  const debouncedSearch = useDebounced(valueSearch, 200);
  const debouncedColFilter = useDebounced(columnFilter, 200);

  const load = useCallback(
    (off: number, start: string | null, end: string | null) => {
      if (!jobId) return;
      setLoading(true);
      setError(null);
      getDataPreview(jobId, off, PAGE, { start, end })
        .then((res) => {
          setData(res);
          if (res.time_min) setSpanMin(res.time_min);
          if (res.time_max) setSpanMax(res.time_max);
          // Seed inputs once from dataset span
          if (!start && !end && res.time_min && res.time_max) {
            setStartInput((prev) => prev || toInputValue(res.time_min));
            setEndInput((prev) => prev || toInputValue(res.time_max));
          }
        })
        .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load data."))
        .finally(() => setLoading(false));
    },
    [jobId],
  );

  useEffect(() => {
    load(offset, appliedStart, appliedEnd);
  }, [load, offset, appliedStart, appliedEnd]);

  const applyDates = () => {
    setOffset(0);
    setAppliedStart(fromInputValue(startInput));
    setAppliedEnd(fromInputValue(endInput));
  };

  const fullRange = () => {
    setStartInput(toInputValue(spanMin));
    setEndInput(toInputValue(spanMax));
    setAppliedStart(null);
    setAppliedEnd(null);
    setOffset(0);
  };

  const visibleCols = useMemo(() => {
    if (!data) return [] as { name: string; index: number }[];
    const q = debouncedColFilter.trim().toLowerCase();
    let cols = data.columns.map((name, index) => ({ name, index }));
    if (q) cols = cols.filter((c) => c.name.toLowerCase().includes(q));
    if (hideEmpty && data.rows.length > 0) {
      cols = cols.filter((c) => data.rows.some((row) => String(row[c.index] ?? "").trim() !== ""));
    }
    // Keep timestamp columns first when present
    cols.sort((a, b) => {
      const at = isTsCol(a.name) ? 0 : 1;
      const bt = isTsCol(b.name) ? 0 : 1;
      return at - bt;
    });
    return cols;
  }, [data, debouncedColFilter, hideEmpty]);

  const visibleRows = useMemo(() => {
    if (!data) return [] as string[][];
    const q = debouncedSearch.trim().toLowerCase();
    if (!q) return data.rows;
    const idxs = visibleCols.map((c) => c.index);
    return data.rows.filter((row) => idxs.some((i) => String(row[i] ?? "").toLowerCase().includes(q)));
  }, [data, debouncedSearch, visibleCols]);

  const dateActive = Boolean(appliedStart || appliedEnd);
  const exportHref = jobId
    ? dataExportUrl(jobId, { start: appliedStart, end: appliedEnd })
    : "#";

  if (!jobId) return null;

  return (
    <div className="tool-enter flex h-[calc(100dvh-8.75rem)] max-h-[calc(100dvh-8.75rem)] flex-col gap-1.5 overflow-hidden">
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-2 [&_nav]:mb-0">
        <div className="min-w-0">
          <JobNav />
          <div className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-0">
            <h2 className="font-display text-base font-semibold tracking-tight text-stone-900 dark:text-stone-50">
              Raw data
            </h2>
            <p className="text-[11px] text-stone-500">
              {data?.source ?? "…"}
              {data?.upload_sources && data.upload_sources.length > 1
                ? ` · ${data.upload_sources.length} reports`
                : ""}
              {data?.original_filename ? ` · ${data.original_filename}` : ""}
            </p>
          </div>
        </div>
        <a className="btn-secondary shrink-0 !px-2.5 !py-1 text-[11px]" href={exportHref} download>
          {dateActive ? "CSV (filtered)" : "Download CSV"}
        </a>
      </div>

      {loading && !data && (
        <div className="flex items-center gap-2 text-sm text-stone-500">
          <Spinner className="h-4 w-4" /> Loading rows…
        </div>
      )}
      {!loading && error && !data && <ErrorState title="Data preview unavailable" message={error} />}

      {data && (
        <>
          <div
            data-tour="raw-data-filters"
            className="flex shrink-0 flex-wrap items-end gap-1.5 rounded-xl border border-stone-200/90 bg-white/90 px-2.5 py-1.5 dark:border-stone-800 dark:bg-stone-900/70"
          >
            <label className="min-w-[9rem] flex-1 sm:max-w-[12rem]">
              <span className="label mb-0 text-[10px]">From</span>
              <input
                type="datetime-local"
                className="input !py-1 text-[11px]"
                value={startInput}
                onChange={(e) => setStartInput(e.target.value)}
                max={endInput || undefined}
              />
            </label>
            <label className="min-w-[9rem] flex-1 sm:max-w-[12rem]">
              <span className="label mb-0 text-[10px]">To</span>
              <input
                type="datetime-local"
                className="input !py-1 text-[11px]"
                value={endInput}
                onChange={(e) => setEndInput(e.target.value)}
                min={startInput || undefined}
              />
            </label>
            <button type="button" className="btn-primary !py-1 text-[11px]" onClick={applyDates} disabled={loading}>
              Apply
            </button>
            <button type="button" className="btn-ghost !px-2 !py-1 text-[11px]" onClick={fullRange} disabled={loading}>
              Full
            </button>
            <label className="min-w-[8rem] flex-1 sm:max-w-[11rem]">
              <span className="label mb-0 text-[10px]">Columns</span>
              <input
                className="input !py-1 text-[11px]"
                placeholder="Filter cols…"
                value={columnFilter}
                onChange={(e) => setColumnFilter(e.target.value)}
              />
            </label>
            <label className="min-w-[8rem] flex-1 sm:max-w-[11rem]">
              <span className="label mb-0 text-[10px]">Search</span>
              <input
                className="input !py-1 text-[11px]"
                placeholder="Cell text…"
                value={valueSearch}
                onChange={(e) => setValueSearch(e.target.value)}
              />
            </label>
            <label className="flex cursor-pointer items-center gap-1.5 pb-1 text-[11px] text-stone-600 dark:text-stone-300">
              <input type="checkbox" checked={hideEmpty} onChange={(e) => setHideEmpty(e.target.checked)} />
              Hide empty
            </label>
            {!data.time_column && (
              <p className="basis-full text-[10px] text-amber-700 dark:text-amber-400">
                No timestamp column — date filter may not apply.
              </p>
            )}
          </div>

          <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 px-0.5">
            <p className="text-[11px] text-stone-600 dark:text-stone-300">
              {data.total_rows === 0 ? (
                <>No rows{dateActive ? " in this date range" : ""}</>
              ) : (
                <>
                  {(offset + 1).toLocaleString()}–
                  {Math.min(offset + PAGE, data.total_rows).toLocaleString()} of{" "}
                  <span className="font-semibold tabular-nums">{data.total_rows.toLocaleString()}</span>
                  {dateActive ? " in range" : ""}
                  {dateActive && data.unfiltered_rows != null && (
                    <span className="text-stone-400"> · {data.unfiltered_rows.toLocaleString()} total</span>
                  )}
                </>
              )}
              <span className="text-stone-400">
                {" "}
                · {visibleCols.length}/{data.columns.length} cols
              </span>
              {debouncedSearch && (
                <span className="text-stone-400"> · {visibleRows.length} match</span>
              )}
              {loading && <span className="ml-1 text-stone-400">Updating…</span>}
            </p>
            <div className="flex gap-1.5">
              <button
                type="button"
                className="btn-secondary !px-2 !py-0.5 text-[11px]"
                disabled={offset === 0 || loading}
                onClick={() => setOffset((o) => Math.max(0, o - PAGE))}
              >
                Prev
              </button>
              <button
                type="button"
                className="btn-secondary !px-2 !py-0.5 text-[11px]"
                disabled={offset + PAGE >= data.total_rows || loading}
                onClick={() => setOffset((o) => o + PAGE)}
              >
                Next
              </button>
            </div>
          </div>

          {visibleCols.length === 0 ? (
            <p className="text-sm text-stone-500">No columns to show. Adjust filters or uncheck “Hide empty”.</p>
          ) : (
            <div className="data-table-shell min-h-0 flex-1 !max-h-none !rounded-xl">
              <table className="data-table !min-w-[480px] text-[11px]">
                <thead className="sticky top-0 z-10">
                  <tr>
                    {visibleCols.map((c) => (
                      <th
                        key={c.name}
                        className={`!px-2 !py-1.5 whitespace-nowrap ${isTsCol(c.name) ? "min-w-[8.5rem]" : ""}`}
                        title={c.name}
                      >
                        {c.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.length === 0 ? (
                    <tr>
                      <td colSpan={visibleCols.length} className="px-3 py-5 text-center text-stone-400">
                        {dateActive
                          ? "No rows in this date range for the current page filters."
                          : "No rows on this page match the value search."}
                      </td>
                    </tr>
                  ) : (
                    visibleRows.map((row, ri) => (
                      <tr
                        key={ri}
                        className="border-b border-stone-100 odd:bg-white even:bg-stone-50/70 hover:bg-brand-50/40 dark:border-stone-800 dark:odd:bg-stone-950/40 dark:even:bg-stone-900/40 dark:hover:bg-stone-800/50"
                      >
                        {visibleCols.map((c) => {
                          const val = row[c.index];
                          const empty = val === "" || val == null;
                          return (
                            <td
                              key={c.name}
                              className={`whitespace-nowrap !px-2 !py-0.5 font-mono text-[10px] tabular-nums text-stone-700 dark:text-stone-300 ${
                                isTsCol(c.name) ? "text-stone-800 dark:text-stone-100" : "max-w-[10rem] truncate"
                              }`}
                              title={empty ? undefined : String(val)}
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
            </div>
          )}
        </>
      )}
    </div>
  );
}
