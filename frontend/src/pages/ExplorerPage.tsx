import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  ApiError,
  getExplorerEquipment,
  getExplorerSignals,
  getExplorerTimeseries,
} from "@/api/client";
import { ChartDownloadButton } from "@/components/ChartDownloadButton";
import { JobNav } from "@/components/JobNav";
import { Spinner } from "@/components/ui/Spinner";
import { useTheme } from "@/context/ThemeContext";
import { CHART_PALETTE, plotlyHoverLabel, plotlyUiConfig } from "@/lib/chartTheme";
import type { TimeseriesResponse } from "@/types";

const Plot = lazy(() => import("react-plotly.js"));

const LEVELS = [
  { id: "inverter", label: "Inverter" },
  { id: "scb", label: "SCB / SMB" },
  { id: "string", label: "String" },
  { id: "wms", label: "WMS / Meteo" },
] as const;

/** App chrome: header 3.5rem + main py-5 2.5rem + footer ~3.5rem */
const VIEWPORT_SHELL = "h-[calc(100dvh-9.5rem)] max-h-[calc(100dvh-9.5rem)]";

function useDebounced<T>(value: T, ms = 220): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

function useElementHeight(enabled: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(280);

  useEffect(() => {
    if (!enabled) return;
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const h = Math.floor(el.getBoundingClientRect().height);
      if (h > 80) setHeight(h);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [enabled]);

  return { ref, height };
}

export function ExplorerPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const { theme } = useTheme();
  const chartHostRef = useRef<HTMLDivElement>(null);
  /** Browse level only filters the picker — selections persist across levels. */
  const [browseLevel, setBrowseLevel] = useState<string>("inverter");
  const [equipment, setEquipment] = useState<string[]>([]);
  const [signals, setSignals] = useState<{ id: string; label: string }[]>([]);
  const [selectedEq, setSelectedEq] = useState<string[]>([]);
  const [selectedSig, setSelectedSig] = useState<string[]>([]);
  const [knownSigLabels, setKnownSigLabels] = useState<Record<string, string>>({});
  const [series, setSeries] = useState<TimeseriesResponse | null>(null);
  const [loadingMeta, setLoadingMeta] = useState(false);
  const [loading, setLoading] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [eqSearch, setEqSearch] = useState("");
  const [startInput, setStartInput] = useState("");
  const [endInput, setEndInput] = useState("");
  const debouncedEqSearch = useDebounced(eqSearch);

  const hasFigure = Boolean(series?.series.length);
  const { ref: plotAreaRef, height: plotHeight } = useElementHeight(hasFigure);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    setLoadingMeta(true);
    setError(null);
    Promise.all([getExplorerEquipment(jobId, browseLevel), getExplorerSignals(jobId, browseLevel)])
      .then(([eq, sig]) => {
        if (cancelled) return;
        setEquipment(eq.equipment_ids);
        setSignals(sig.signals);
        setKnownSigLabels((prev) => {
          const next = { ...prev };
          for (const s of sig.signals) next[s.id] = s.label;
          return next;
        });
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "Could not load explorer metadata.");
      })
      .finally(() => {
        if (!cancelled) setLoadingMeta(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, browseLevel]);

  const filteredEquipment = useMemo(() => {
    const q = debouncedEqSearch.trim().toLowerCase();
    if (!q) return equipment;
    return equipment.filter((id) => id.toLowerCase().includes(q));
  }, [equipment, debouncedEqSearch]);

  const plot = useCallback(async () => {
    if (!jobId || selectedEq.length === 0 || selectedSig.length === 0) return;
    setLoading(true);
    setError(null);
    try {
      const start = startInput.trim() ? (startInput.length === 16 ? `${startInput}:00` : startInput) : null;
      const end = endInput.trim() ? (endInput.length === 16 ? `${endInput}:00` : endInput) : null;
      const res = await getExplorerTimeseries(jobId, selectedEq, selectedSig, { start, end });
      setSeries(res);
      setNote(res.note ?? null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Plot failed.");
    } finally {
      setLoading(false);
    }
  }, [jobId, selectedEq, selectedSig, startInput, endInput]);

  const canPlot = selectedEq.length > 0 && selectedSig.length > 0;
  const dark = theme === "dark";

  const figure = useMemo(() => {
    if (!series?.series.length) return null;
    const fontColor = dark ? "#d6d3d1" : "#44403c";
    const muted = dark ? "#a8a29e" : "#78716c";
    const grid = dark ? "#44403c" : "#e7e5e4";
    return {
      data: series.series.map((s, i) => ({
        type: "scatter" as const,
        mode: "lines" as const,
        name: s.name,
        x: s.timestamps,
        y: s.values,
        line: { width: 1.5, color: CHART_PALETTE[i % CHART_PALETTE.length] },
        yaxis: s.signal.includes("poa") || s.signal.includes("ghi") || s.signal.includes("temp") ? "y2" : "y1",
      })),
      layout: {
        autosize: true,
        height: plotHeight,
        paper_bgcolor: "transparent",
        plot_bgcolor: dark ? "rgba(28,25,23,0.5)" : "rgba(250,250,249,0.8)",
        font: { color: fontColor, size: 11, family: "DM Sans, Segoe UI, system-ui, sans-serif" },
        margin: { t: 16, r: 52, b: 48, l: 48 },
        xaxis: { title: "Time", gridcolor: grid, automargin: true },
        yaxis: { title: "Electrical", gridcolor: grid, automargin: true },
        yaxis2: {
          title: "Irradiance / Temp",
          overlaying: "y" as const,
          side: "right" as const,
          gridcolor: "transparent",
          automargin: true,
        },
        legend: { orientation: "h" as const, y: -0.18, x: 0, xanchor: "left" as const, font: { size: 11, color: muted } },
        hoverlabel: plotlyHoverLabel(dark),
        title: undefined,
      },
    };
  }, [series, dark, plotHeight]);

  const toggleEq = (id: string, checked: boolean) => {
    setSelectedEq((prev) => (checked ? [...prev, id] : prev.filter((x) => x !== id)));
  };

  const toggleSig = (id: string, checked: boolean) => {
    setSelectedSig((prev) => (checked ? [...prev, id] : prev.filter((x) => x !== id)));
  };

  const selectAllEq = () => {
    setSelectedEq((prev) => Array.from(new Set([...prev, ...filteredEquipment])));
  };

  const clearVisibleEq = () => {
    const visible = new Set(filteredEquipment);
    setSelectedEq((prev) => prev.filter((id) => !visible.has(id)));
  };

  const selectAllSig = () => {
    setSelectedSig((prev) => Array.from(new Set([...prev, ...signals.map((s) => s.id)])));
  };

  const clearVisibleSig = () => {
    const visible = new Set(signals.map((s) => s.id));
    setSelectedSig((prev) => prev.filter((id) => !visible.has(id)));
  };

  const allVisibleEqSelected =
    filteredEquipment.length > 0 && filteredEquipment.every((id) => selectedEq.includes(id));
  const allVisibleSigSelected =
    signals.length > 0 && signals.every((s) => selectedSig.includes(s.id));

  if (!jobId) return null;

  return (
    <div className={`tool-enter flex ${VIEWPORT_SHELL} flex-col gap-2 overflow-y-auto xl:overflow-hidden`}>
      <div className="shrink-0 [&_nav]:mb-0">
        <JobNav />
      </div>

      <div className="shrink-0" data-tour="signal-explorer">
        <p className="tool-eyebrow mb-0.5">Telemetry</p>
        <h2 className="font-display text-lg font-semibold tracking-tight text-stone-900 dark:text-stone-50">
          Signal Explorer
        </h2>
        <p className="text-xs text-stone-500">Pick equipment and signals, then plot. Selections keep across tabs.</p>
      </div>

      {/* Range + plot controls — shrink-0, not sticky (no page scroll) */}
      <div className="shrink-0 rounded-2xl border border-stone-200/90 bg-gradient-to-br from-white/95 to-stone-50/80 px-3 py-2.5 shadow-sm shadow-stone-900/[0.03] dark:border-stone-800 dark:from-stone-900/70 dark:to-stone-950/50 dark:shadow-none">
        <div className="flex flex-wrap items-end gap-2">
          <label className="min-w-[10rem] flex-1 sm:max-w-[14rem]">
            <span className="label mb-0.5">From</span>
            <input
              type="datetime-local"
              className="input !py-1.5 text-xs"
              value={startInput}
              onChange={(e) => setStartInput(e.target.value)}
            />
          </label>
          <label className="min-w-[10rem] flex-1 sm:max-w-[14rem]">
            <span className="label mb-0.5">To</span>
            <input
              type="datetime-local"
              className="input !py-1.5 text-xs"
              value={endInput}
              onChange={(e) => setEndInput(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="btn-ghost !px-2 !py-1.5 text-xs"
            onClick={() => {
              setStartInput("");
              setEndInput("");
            }}
          >
            Full range
          </button>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="btn-primary !py-1.5 text-xs"
              onClick={plot}
              disabled={loading || !canPlot}
              title={!canPlot ? "Select at least one equipment and one signal" : undefined}
            >
              {loading ? <Spinner className="h-3.5 w-3.5" /> : null}
              Plot
            </button>
          </div>
        </div>
        {!canPlot && (
          <p className="mt-1 text-[11px] text-stone-400">Select equipment and a signal below, then Plot.</p>
        )}
      </div>

      <div className="grid min-h-0 flex-1 gap-2 overflow-hidden xl:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        {/* Dense picker column */}
        <div className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-stone-200/90 bg-white/95 shadow-sm shadow-stone-900/[0.03] dark:border-stone-800 dark:bg-stone-900/70 dark:shadow-none">
          <div className="flex shrink-0 flex-wrap gap-0 border-b border-stone-200/80 dark:border-stone-800">
            {LEVELS.map((l) => (
              <button
                key={l.id}
                type="button"
                className={`px-2.5 py-1.5 text-xs font-semibold transition-all duration-150 ${
                  browseLevel === l.id
                    ? "border-b-2 border-brand-600 text-stone-900 dark:border-brand-400 dark:text-stone-50"
                    : "border-b-2 border-transparent text-stone-500 hover:text-stone-800 dark:hover:text-stone-200"
                }`}
                onClick={() => setBrowseLevel(l.id)}
              >
                {l.label}
              </button>
            ))}
          </div>

          {(selectedEq.length > 0 || selectedSig.length > 0) && (
            <div className="flex shrink-0 flex-wrap items-center gap-1 border-b border-stone-100 px-2.5 py-1.5 dark:border-stone-800">
              <span className="mr-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-stone-400">
                Selected
              </span>
              {selectedEq.map((id) => (
                <button
                  key={id}
                  type="button"
                  className="rounded-md bg-brand-100 px-1.5 py-0.5 font-mono text-[10px] text-brand-900 transition hover:bg-brand-200 dark:bg-brand-900/40 dark:text-brand-100"
                  onClick={() => toggleEq(id, false)}
                  title="Remove"
                >
                  {id} ×
                </button>
              ))}
              {selectedSig.map((id) => (
                <button
                  key={id}
                  type="button"
                  className="rounded-md bg-accent-100 px-1.5 py-0.5 text-[10px] text-accent-900 transition hover:bg-accent-200 dark:bg-accent-900/40 dark:text-accent-100"
                  onClick={() => toggleSig(id, false)}
                  title="Remove"
                >
                  {knownSigLabels[id] ?? id} ×
                </button>
              ))}
              <button
                type="button"
                className="ml-auto text-[10px] text-stone-500 hover:underline"
                onClick={() => {
                  setSelectedEq([]);
                  setSelectedSig([]);
                  setSeries(null);
                }}
              >
                Clear
              </button>
            </div>
          )}

          <div className="grid min-h-0 flex-1 gap-0 overflow-hidden sm:grid-cols-2 sm:divide-x sm:divide-stone-200 xl:grid-cols-1 xl:grid-rows-2 xl:divide-x-0 xl:divide-y dark:sm:divide-stone-800">
            <div className="flex min-h-0 flex-col overflow-hidden p-2.5">
              <div className="mb-1 flex shrink-0 items-center justify-between gap-2">
                <p className="label mb-0 text-[11px]">
                  {LEVELS.find((l) => l.id === browseLevel)?.label} ({equipment.length})
                </p>
                <div className="flex items-center gap-2">
                  {loadingMeta && <Spinner className="h-3 w-3" />}
                  <button
                    type="button"
                    className="text-[10px] font-medium text-brand-700 hover:underline disabled:cursor-not-allowed disabled:opacity-40 dark:text-brand-300"
                    disabled={filteredEquipment.length === 0 || allVisibleEqSelected}
                    onClick={selectAllEq}
                  >
                    Select all
                  </button>
                  <button
                    type="button"
                    className="text-[10px] font-medium text-stone-500 hover:underline disabled:cursor-not-allowed disabled:opacity-40"
                    disabled={!filteredEquipment.some((id) => selectedEq.includes(id))}
                    onClick={clearVisibleEq}
                  >
                    Clear
                  </button>
                </div>
              </div>
              <input
                className="input mb-1.5 shrink-0 !py-1 text-xs"
                placeholder="Search…"
                value={eqSearch}
                onChange={(e) => setEqSearch(e.target.value)}
              />
              <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain rounded-lg border border-stone-200/90 bg-stone-50/40 p-1.5 pb-2.5 dark:border-stone-700 dark:bg-stone-950/30">
                {filteredEquipment.length === 0 && (
                  <p className="text-[11px] text-stone-400">
                    {equipment.length === 0 ? "No equipment at this level." : "No matches."}
                  </p>
                )}
                {filteredEquipment.map((id) => (
                  <label
                    key={id}
                    className="flex cursor-pointer items-center gap-1.5 rounded-md px-1 py-0.5 text-xs transition hover:bg-white dark:hover:bg-stone-800/60"
                  >
                    <input
                      type="checkbox"
                      checked={selectedEq.includes(id)}
                      onChange={(e) => toggleEq(id, e.target.checked)}
                    />
                    <span className="font-mono text-[11px]">{id}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="flex min-h-0 flex-col overflow-hidden p-2.5">
              <div className="mb-0.5 flex shrink-0 items-center justify-between gap-2">
                <p className="label mb-0 text-[11px]">Signals ({signals.length})</p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="text-[10px] font-medium text-brand-700 hover:underline disabled:cursor-not-allowed disabled:opacity-40 dark:text-brand-300"
                    disabled={signals.length === 0 || allVisibleSigSelected}
                    onClick={selectAllSig}
                  >
                    Select all
                  </button>
                  <button
                    type="button"
                    className="text-[10px] font-medium text-stone-500 hover:underline disabled:cursor-not-allowed disabled:opacity-40"
                    disabled={!signals.some((s) => selectedSig.includes(s.id))}
                    onClick={clearVisibleSig}
                  >
                    Clear
                  </button>
                </div>
              </div>
              <p className="mb-1 shrink-0 text-[10px] leading-snug text-stone-400">
                {browseLevel === "wms"
                  ? "Selections keep across tabs — plot INV + POA together."
                  : "Irradiance & temps are under WMS — switch tabs to add them."}
              </p>
              <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain rounded-lg border border-stone-200/90 bg-stone-50/40 p-1.5 pb-2.5 dark:border-stone-700 dark:bg-stone-950/30">
                {signals.length === 0 && <p className="text-[11px] text-stone-400">No signals at this level.</p>}
                {signals.map((s) => (
                  <label
                    key={s.id}
                    className="flex cursor-pointer items-center gap-1.5 rounded-md px-1 py-0.5 text-xs transition hover:bg-white dark:hover:bg-stone-800/60"
                  >
                    <input
                      type="checkbox"
                      checked={selectedSig.includes(s.id)}
                      onChange={(e) => toggleSig(s.id, e.target.checked)}
                    />
                    {s.label}
                  </label>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Plot column — fills remaining height */}
        <div className="flex min-h-0 min-w-0 flex-col overflow-hidden">
          {note && <p className="mb-1 shrink-0 text-xs text-amber-700 dark:text-amber-400">{note}</p>}
          {error && <p className="mb-1 shrink-0 text-xs text-rose-600">{error}</p>}

          {figure ? (
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-stone-200/90 bg-white/95 shadow-sm shadow-stone-900/[0.03] dark:border-stone-800 dark:bg-stone-900/70 dark:shadow-none">
              {/* Header row ABOVE the plot — never overlaid / sticky on the chart */}
              <div className="flex shrink-0 items-center justify-between gap-2 border-b border-stone-200/80 px-3 py-2 dark:border-stone-800">
                <div className="min-w-0">
                  <p className="font-display text-xs font-semibold text-stone-800 dark:text-stone-100">Timeseries</p>
                  <p className="text-[10px] text-stone-400">
                    {series?.point_count.toLocaleString()} points
                  </p>
                </div>
                <ChartDownloadButton hostRef={chartHostRef} filename="signal_explorer" />
              </div>
              <div ref={chartHostRef} className="plotly-chart-host min-h-0 flex-1 px-2 pb-2 pt-1">
                <div ref={plotAreaRef} className="h-full min-h-[12rem] w-full">
                  <Suspense
                    fallback={
                      <div className="flex h-full items-center justify-center gap-2 text-sm text-stone-500">
                        <Spinner className="h-4 w-4" /> Loading chart…
                      </div>
                    }
                  >
                    <Plot
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      data={figure.data as any[]}
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      layout={figure.layout as any}
                      config={plotlyUiConfig("signal_explorer")}
                      style={{ width: "100%", height: plotHeight }}
                      useResizeHandler
                    />
                  </Suspense>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex min-h-0 flex-1 items-center justify-center rounded-2xl border border-dashed border-stone-300/90 bg-gradient-to-br from-stone-50/80 to-brand-50/20 px-4 text-center dark:border-stone-600 dark:bg-stone-900/80 dark:bg-none">
              <p className="max-w-sm text-xs leading-relaxed text-stone-500">
                Select equipment and signals, then click{" "}
                <span className="font-semibold text-stone-700 dark:text-stone-200">Plot</span>.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
