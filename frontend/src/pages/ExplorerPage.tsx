import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  ApiError,
  getExplorerEquipment,
  getExplorerSignals,
  getExplorerTimeseries,
} from "@/api/client";
import { SyncedDualCharts, classifySignal } from "@/components/explorer/SyncedDualCharts";
import { JobWorkspace } from "@/components/JobWorkspace";
import { Spinner } from "@/components/ui/Spinner";
import { useTheme } from "@/context/ThemeContext";
import type { TimeseriesResponse } from "@/types";

const LEVELS = [
  { id: "inverter", label: "Inverter" },
  { id: "scb", label: "SCB" },
  { id: "string", label: "String" },
  { id: "wms", label: "WMS" },
] as const;

function useDebounced<T>(value: T, ms = 220): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

export function ExplorerPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const { theme } = useTheme();
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
  const [forceSingle, setForceSingle] = useState(false);
  const debouncedEqSearch = useDebounced(eqSearch);

  const hasFigure = Boolean(series?.series.length);
  const dark = theme === "dark";

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

  const canDual =
    selectedSig.some((id) => classifySignal(id) === "current") &&
    selectedSig.some((id) => classifySignal(id) === "voltage");

  const plottedDual =
    !forceSingle &&
    Boolean(
      series?.series.some((s) => classifySignal(s.signal) === "current") &&
        series?.series.some((s) => classifySignal(s.signal) === "voltage"),
    );

  /** One-click Current + Voltage pair when both exist at this browse level (or already known). */
  const pairCurrentVoltage = () => {
    const ids = new Set(signals.map((s) => s.id));
    let currentId =
      [...ids].find((id) => classifySignal(id) === "current") ??
      (knownSigLabels["dc_current_a"] ? "dc_current_a" : null);
    let voltageId =
      [...ids].find((id) => classifySignal(id) === "voltage") ??
      (knownSigLabels["dc_voltage_v"] ? "dc_voltage_v" : null);

    // Inverter-level lists often only expose AC/DC power — jump to SCB for I/V.
    if ((!currentId || !voltageId) && browseLevel === "inverter") {
      setBrowseLevel("scb");
      return;
    }

    if (!currentId && !voltageId) return;
    // Prefer a clean I/V selection so dual panes activate immediately.
    const next = new Set<string>();
    if (currentId) next.add(currentId);
    if (voltageId) next.add(voltageId);
    setSelectedSig(Array.from(next));
    setForceSingle(false);
  };

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

  const hasCurrentHere = signals.some((s) => classifySignal(s.id) === "current");
  const hasVoltageHere = signals.some((s) => classifySignal(s.id) === "voltage");

  if (!jobId) return null;

  return (
    <JobWorkspace
      title="Signal Explorer"
      titleTour="signal-explorer"
      subtitle="Dual Current · Voltage when both selected · synced zoom"
      chromeExtra={
        <div className="flex flex-wrap items-end gap-2 border-t border-[color:var(--pic-border-subtle)] bg-[color:var(--pic-surface-inset)] px-3 py-2.5 sm:px-4">
          <label className="min-w-[9rem] flex-1 sm:max-w-[12rem]">
            <span className="label mb-0 text-[10px]">From</span>
            <input
              type="datetime-local"
              className="input !py-1.5 text-[11px]"
              value={startInput}
              onChange={(e) => setStartInput(e.target.value)}
            />
          </label>
          <label className="min-w-[9rem] flex-1 sm:max-w-[12rem]">
            <span className="label mb-0 text-[10px]">To</span>
            <input
              type="datetime-local"
              className="input !py-1.5 text-[11px]"
              value={endInput}
              onChange={(e) => setEndInput(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="btn-ghost !px-2 !py-1.5 text-[11px]"
            onClick={() => {
              setStartInput("");
              setEndInput("");
            }}
          >
            Full range
          </button>
          {(hasCurrentHere || hasVoltageHere || knownSigLabels["dc_current_a"] || knownSigLabels["dc_voltage_v"]) && (
            <button
              type="button"
              className="btn-ghost !px-2 !py-1.5 text-[11px]"
              onClick={pairCurrentVoltage}
              title="Add DC Current and DC Voltage to selection"
            >
              + I / V pair
            </button>
          )}
          {(canDual || plottedDual) && (
            <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-[color:var(--pic-text-secondary)]">
              <input
                type="checkbox"
                checked={forceSingle}
                onChange={(e) => setForceSingle(e.target.checked)}
              />
              Single chart
            </label>
          )}
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="btn-primary !py-1.5 text-[11px]"
              onClick={plot}
              disabled={loading || !canPlot}
              title={!canPlot ? "Select at least one equipment and one signal" : undefined}
            >
              {loading ? <Spinner className="h-3 w-3" /> : null}
              Plot
            </button>
          </div>
        </div>
      }
      flushMain
      className="xl:overflow-hidden"
    >
      <div className="grid min-h-0 flex-1 gap-0 overflow-y-auto xl:grid-cols-[minmax(0,15.5rem)_minmax(0,1fr)] xl:overflow-hidden">
        {/* Dense picker column */}
        <div className="flex min-h-0 flex-col overflow-hidden border-b border-[color:var(--pic-border-subtle)] xl:border-b-0 xl:border-r">
          <div className="flex shrink-0 flex-wrap gap-0 border-b border-[color:var(--pic-border-subtle)]">
            {LEVELS.map((l) => (
              <button
                key={l.id}
                type="button"
                className={`px-2.5 py-2 text-[11px] font-semibold transition-all duration-150 ${
                  browseLevel === l.id
                    ? "border-b-2 border-brand-600 text-[color:var(--pic-text)] dark:border-brand-400"
                    : "border-b-2 border-transparent text-[color:var(--pic-text-muted)] hover:text-[color:var(--pic-text)]"
                }`}
                onClick={() => setBrowseLevel(l.id)}
              >
                {l.label}
              </button>
            ))}
          </div>

          {(selectedEq.length > 0 || selectedSig.length > 0) && (
            <div className="flex shrink-0 flex-wrap items-center gap-1 border-b border-stone-100 px-2 py-1 dark:border-stone-800">
              <span className="mr-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-stone-400">
                Sel
              </span>
              {selectedEq.map((id) => (
                <button
                  key={id}
                  type="button"
                  className="rounded bg-brand-100 px-1 py-px font-mono text-[9px] text-brand-900 transition hover:bg-brand-200 dark:bg-brand-900/40 dark:text-brand-100"
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
                  className="rounded bg-accent-100 px-1 py-px text-[9px] text-accent-900 transition hover:bg-accent-200 dark:bg-accent-900/40 dark:text-accent-100"
                  onClick={() => toggleSig(id, false)}
                  title="Remove"
                >
                  {knownSigLabels[id] ?? id} ×
                </button>
              ))}
              <button
                type="button"
                className="ml-auto text-[9px] text-stone-500 hover:underline"
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
            <div className="flex min-h-0 flex-col overflow-hidden p-1.5">
              <div className="mb-0.5 flex shrink-0 items-center justify-between gap-1">
                <p className="label mb-0 text-[10px]">
                  {LEVELS.find((l) => l.id === browseLevel)?.label} ({equipment.length})
                </p>
                <div className="flex items-center gap-1.5">
                  {loadingMeta && <Spinner className="h-2.5 w-2.5" />}
                  <button
                    type="button"
                    className="text-[9px] font-medium text-brand-700 hover:underline disabled:cursor-not-allowed disabled:opacity-40 dark:text-brand-300"
                    disabled={filteredEquipment.length === 0 || allVisibleEqSelected}
                    onClick={selectAllEq}
                  >
                    All
                  </button>
                  <button
                    type="button"
                    className="text-[9px] font-medium text-stone-500 hover:underline disabled:cursor-not-allowed disabled:opacity-40"
                    disabled={!filteredEquipment.some((id) => selectedEq.includes(id))}
                    onClick={clearVisibleEq}
                  >
                    Clear
                  </button>
                </div>
              </div>
              <input
                className="input mb-1 shrink-0 !py-0.5 text-[11px]"
                placeholder="Search…"
                value={eqSearch}
                onChange={(e) => setEqSearch(e.target.value)}
              />
              <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain rounded-md border border-stone-200/90 bg-stone-50/40 p-1 dark:border-stone-700 dark:bg-stone-950/30">
                {filteredEquipment.length === 0 && (
                  <p className="text-[10px] text-stone-400">
                    {equipment.length === 0 ? "No equipment." : "No matches."}
                  </p>
                )}
                {filteredEquipment.map((id) => (
                  <label
                    key={id}
                    className="flex cursor-pointer items-center gap-1 rounded px-0.5 py-px text-[11px] transition hover:bg-white dark:hover:bg-stone-800/60"
                  >
                    <input
                      type="checkbox"
                      className="scale-90"
                      checked={selectedEq.includes(id)}
                      onChange={(e) => toggleEq(id, e.target.checked)}
                    />
                    <span className="font-mono text-[10px] leading-tight">{id}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="flex min-h-0 flex-col overflow-hidden p-1.5">
              <div className="mb-0.5 flex shrink-0 items-center justify-between gap-1">
                <p className="label mb-0 text-[10px]">Signals ({signals.length})</p>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    className="text-[9px] font-medium text-brand-700 hover:underline disabled:cursor-not-allowed disabled:opacity-40 dark:text-brand-300"
                    disabled={signals.length === 0 || allVisibleSigSelected}
                    onClick={selectAllSig}
                  >
                    All
                  </button>
                  <button
                    type="button"
                    className="text-[9px] font-medium text-stone-500 hover:underline disabled:cursor-not-allowed disabled:opacity-40"
                    disabled={!signals.some((s) => selectedSig.includes(s.id))}
                    onClick={clearVisibleSig}
                  >
                    Clear
                  </button>
                </div>
              </div>
              <p className="mb-0.5 shrink-0 text-[9px] leading-snug text-stone-400">
                {browseLevel === "wms"
                  ? "Keep INV + POA selected across tabs."
                  : "Irradiance under WMS. Prefer I + V for dual pane."}
              </p>
              <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain rounded-md border border-stone-200/90 bg-stone-50/40 p-1 dark:border-stone-700 dark:bg-stone-950/30">
                {signals.length === 0 && <p className="text-[10px] text-stone-400">No signals.</p>}
                {signals.map((s) => (
                  <label
                    key={s.id}
                    className="flex cursor-pointer items-center gap-1 rounded px-0.5 py-px text-[11px] leading-tight transition hover:bg-white dark:hover:bg-stone-800/60"
                  >
                    <input
                      type="checkbox"
                      className="scale-90"
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
        <div className="flex min-h-0 min-w-0 flex-col overflow-hidden bg-[color:var(--pic-surface-inset)] p-3">
          {note && <p className="mb-1 shrink-0 text-[11px] text-amber-700 dark:text-amber-400">{note}</p>}
          {error && <p className="mb-1 shrink-0 text-[11px] text-rose-600">{error}</p>}

          {hasFigure && series ? (
            <SyncedDualCharts
              series={series.series}
              dark={dark}
              pointCount={series.point_count}
              forceSingle={forceSingle}
            />
          ) : (
            <div className="flex min-h-0 flex-1 items-center justify-center rounded-pic-lg border border-dashed border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] px-4 text-center">
              <p className="max-w-sm text-[11px] leading-relaxed text-[color:var(--pic-text-muted)]">
                Select equipment + signals (try{" "}
                <span className="font-semibold text-[color:var(--pic-text)]">+ I / V pair</span>
                ), then <span className="font-semibold text-[color:var(--pic-text)]">Plot</span>.
              </p>
            </div>
          )}
        </div>
      </div>
    </JobWorkspace>
  );
}
