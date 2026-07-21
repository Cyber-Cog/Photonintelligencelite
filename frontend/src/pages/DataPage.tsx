import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError, dataExportUrl, getDataPreview } from "@/api/client";
import { JobNav } from "@/components/JobNav";
import { ErrorState } from "@/components/ui/ErrorState";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionPanel } from "@/components/ui/SectionPanel";
import { Spinner } from "@/components/ui/Spinner";
import type { DataPreviewResponse } from "@/types";

const PAGE = 50;

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
    <div className="tool-enter">
      <JobNav />
      <PageHeader
        className="mb-4"
        eyebrow="Telemetry browse"
        title="Raw data"
        description={
          <>
            SCADA rows for this job · source{" "}
            <span className="font-medium text-stone-700 dark:text-stone-200">{data?.source ?? "…"}</span>
            {data?.upload_sources && data.upload_sources.length > 1 && (
              <> · merged from {data.upload_sources.length} reports</>
            )}
            {data?.original_filename ? (
              <span className="block text-stone-400">File: {data.original_filename}</span>
            ) : null}
          </>
        }
        actions={
          <a className="btn-secondary text-xs" href={exportHref} download>
            {dateActive ? "Download filtered CSV" : "Download CSV"}
          </a>
        }
      />

      {loading && !data && (
        <div className="flex items-center gap-2 text-sm text-stone-500">
          <Spinner className="h-4 w-4" /> Loading rows…
        </div>
      )}
      {!loading && error && !data && <ErrorState title="Data preview unavailable" message={error} />}

      {data && (
        <>
          <div data-tour="raw-data-filters">
          <SectionPanel
            className="mb-3"
            title="Filters"
            description={
              spanMin && spanMax
                ? `Dataset span: ${toInputValue(spanMin).replace("T", " ")} to ${toInputValue(spanMax).replace("T", " ")} UTC`
                : "Date range and column filters"
            }
            scrollMargin={false}
          >
            <div className="toolbar !border-0 !bg-transparent !p-0">
              <label className="block min-w-[11rem] flex-1">
                <span className="label">From</span>
                <input
                  type="datetime-local"
                  className="input"
                  value={startInput}
                  onChange={(e) => setStartInput(e.target.value)}
                  max={endInput || undefined}
                />
              </label>
              <label className="block min-w-[11rem] flex-1">
                <span className="label">To</span>
                <input
                  type="datetime-local"
                  className="input"
                  value={endInput}
                  onChange={(e) => setEndInput(e.target.value)}
                  min={startInput || undefined}
                />
              </label>
              <button type="button" className="btn-primary text-xs" onClick={applyDates} disabled={loading}>
                Apply range
              </button>
              <button type="button" className="btn-ghost text-xs" onClick={fullRange} disabled={loading}>
                Full range
              </button>
            </div>
            {!data.time_column && (
              <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
                No timestamp column detected. Date filter may not apply until analysis produces canonical data.
              </p>
            )}
            <div className="mt-3 grid gap-2 border-t border-stone-200 pt-3 dark:border-stone-800 sm:grid-cols-2 lg:grid-cols-3">
              <label className="block">
                <span className="label">Filter columns</span>
                <input
                  className="input"
                  placeholder="e.g. ac_power, inverter…"
                  value={columnFilter}
                  onChange={(e) => setColumnFilter(e.target.value)}
                />
              </label>
              <label className="block">
                <span className="label">Search values (this page)</span>
                <input
                  className="input"
                  placeholder="Filter rows by cell text…"
                  value={valueSearch}
                  onChange={(e) => setValueSearch(e.target.value)}
                />
              </label>
              <label className="flex cursor-pointer items-center gap-2 self-end pb-2 text-sm text-stone-600 dark:text-stone-300">
                <input type="checkbox" checked={hideEmpty} onChange={(e) => setHideEmpty(e.target.checked)} />
                Hide empty columns (this page)
              </label>
            </div>
          </SectionPanel>
          </div>

          <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-stone-200/80 bg-white/60 px-3 py-2 dark:border-stone-800/80 dark:bg-stone-900/40">
            <p className="text-xs text-stone-600 dark:text-stone-300">
              {data.total_rows === 0 ? (
                <>No rows{dateActive ? " in this date range" : ""}</>
              ) : (
                <>
                  Showing {(offset + 1).toLocaleString()}–
                  {Math.min(offset + PAGE, data.total_rows).toLocaleString()} of{" "}
                  <span className="font-semibold tabular-nums">{data.total_rows.toLocaleString()}</span>
                  {dateActive ? " in range" : " rows"}
                  {dateActive && data.unfiltered_rows != null && (
                    <span className="text-stone-400">
                      {" "}
                      · {data.unfiltered_rows.toLocaleString()} total unfiltered
                    </span>
                  )}
                </>
              )}
              <span className="text-stone-400">
                {" "}
                · {visibleCols.length}/{data.columns.length} columns
              </span>
              {debouncedSearch && (
                <span className="text-stone-400"> · {visibleRows.length} match on this page</span>
              )}
              {loading && <span className="ml-2 text-stone-400">Updating…</span>}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                className="btn-secondary text-xs"
                disabled={offset === 0 || loading}
                onClick={() => setOffset((o) => Math.max(0, o - PAGE))}
              >
                Previous
              </button>
              <button
                type="button"
                className="btn-secondary text-xs"
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
            <div className="data-table-shell">
              <table className="data-table text-xs">
                <thead className="sticky top-0 z-10">
                  <tr>
                    {visibleCols.map((c) => (
                      <th
                        key={c.name}
                        className={`whitespace-nowrap ${isTsCol(c.name) ? "min-w-[9.5rem]" : ""}`}
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
                      <td colSpan={visibleCols.length} className="px-3 py-6 text-center text-stone-400">
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
                              className={`whitespace-nowrap px-2.5 py-1.5 font-mono text-[11px] tabular-nums text-stone-700 dark:text-stone-300 ${
                                isTsCol(c.name) ? "text-stone-800 dark:text-stone-100" : "max-w-[12rem] truncate"
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
