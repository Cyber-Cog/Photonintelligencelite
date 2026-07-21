import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, getArchitectureView } from "@/api/client";
import { JobNav } from "@/components/JobNav";
import { ErrorState } from "@/components/ui/ErrorState";
import { InfoBanner } from "@/components/ui/InfoBanner";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionPanel } from "@/components/ui/SectionPanel";
import { Spinner } from "@/components/ui/Spinner";
import { equipmentBadgeLabel } from "@/lib/equipmentStructure";
import type { ArchitectureViewResponse } from "@/types";

export function ArchitecturePage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [data, setData] = useState<ArchitectureViewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getArchitectureView(jobId)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "Could not load architecture.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = filter.trim().toLowerCase();
    if (!q) return data.inverters;
    return data.inverters.filter(
      (inv) =>
        inv.inverter_id.toLowerCase().includes(q) ||
        inv.scbs.some((s) => s.scb_id.toLowerCase().includes(q)),
    );
  }, [data, filter]);

  if (!jobId) return null;

  return (
    <div className="tool-enter" data-tour="architecture">
      <JobNav />
      <PageHeader
        className="mb-4"
        eyebrow="Plant structure"
        title="Plant architecture"
        description="Inverter → SCB/SMB → strings as configured during setup."
      />

      {loading && (
        <div className="flex items-center gap-2 text-sm text-stone-500">
          <Spinner className="h-4 w-4" /> Loading…
        </div>
      )}
      {!loading && error && (
        <ErrorState
          title="Architecture unavailable"
          message={error}
          hint="If this job was cleaned up, start a new analysis. Otherwise re-open Setup and save plant architecture."
        />
      )}
      {!loading && data && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
            <div className="stat-tile">
              <p className="text-xs font-medium text-stone-500">Plant</p>
              <p className="mt-1.5 text-sm font-semibold text-stone-900 dark:text-stone-50">{data.plant_name || "—"}</p>
            </div>
            <div className="stat-tile">
              <p className="text-xs font-medium text-stone-500">Inverters</p>
              <p className="mt-1 font-display text-xl font-semibold tabular-nums text-stone-900 dark:text-stone-50">
                {data.summary.inverter_count}
              </p>
            </div>
            <div className="stat-tile">
              <p className="text-xs font-medium text-stone-500">SCBs / SMBs</p>
              <p className="mt-1 font-display text-xl font-semibold tabular-nums text-stone-900 dark:text-stone-50">
                {data.summary.scb_count}
              </p>
            </div>
            <div className="stat-tile">
              <p className="text-xs font-medium text-stone-500">Strings (est.)</p>
              <p className="mt-1 font-display text-xl font-semibold tabular-nums text-stone-900 dark:text-stone-50">
                {data.summary.string_count ?? "—"}
              </p>
            </div>
          </div>

          {data.hint && (
            <InfoBanner
              className="mb-4"
              tone="warning"
              actions={
                <Link to={`/jobs/${jobId}/setup`} className="text-xs font-semibold underline">
                  Open Setup
                </Link>
              }
            >
              {data.hint}
            </InfoBanner>
          )}

          {data.inverters.length === 0 ? (
            <SectionPanel title="No architecture saved" scrollMargin={false}>
              <p className="text-xs text-stone-600 dark:text-stone-300">
                Complete Setup to define inverter → SCB mapping (Excel template, auto-detect, or pattern apply).
              </p>
              <Link to={`/jobs/${jobId}/setup`} className="btn-primary mt-3 inline-flex text-sm">
                Go to Setup
              </Link>
            </SectionPanel>
          ) : (
            <>
              <div className="mb-3">
                <input
                  className="input max-w-md"
                  placeholder="Search inverter or SCB…"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                />
              </div>
              <div className="space-y-2.5">
                {filtered.map((inv, idx) => (
                  <details
                    key={inv.inverter_id}
                    className="group overflow-hidden rounded-2xl border border-stone-200/90 bg-white/90 shadow-sm shadow-stone-900/[0.03] dark:border-stone-800 dark:bg-stone-900/60 dark:shadow-none"
                    open={idx === 0 && data.inverters.length <= 12}
                  >
                    <summary className="cursor-pointer list-none overflow-hidden bg-gradient-to-r from-stone-50/90 to-white px-3.5 py-2.5 font-semibold text-stone-800 transition hover:from-brand-50/40 dark:from-stone-900/80 dark:to-stone-900/40 dark:text-stone-100 dark:hover:from-brand-950/25">
                      <span className="flex w-full min-w-0 items-center gap-2.5 text-sm">
                        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand-100 text-[11px] font-bold text-brand-800 dark:bg-brand-900/50 dark:text-brand-200">
                          {equipmentBadgeLabel(inv.inverter_id)}
                        </span>
                        <span className="min-w-0 truncate font-display">{inv.inverter_id}</span>
                        {inv.rated_kw != null && (
                          <span className="shrink-0 text-xs font-normal text-stone-400">{inv.rated_kw} kW</span>
                        )}
                        <span className="ml-auto shrink-0 text-xs font-normal text-stone-400">{inv.scbs.length} SCB(s)</span>
                      </span>
                    </summary>
                    <div className="min-w-0 overflow-x-auto overflow-y-hidden border-t border-stone-200/90 px-3 py-2.5 [scrollbar-width:thin] dark:border-stone-800">
                      {inv.scbs.length === 0 ? (
                        <p className="text-xs text-stone-400">No SCBs mapped under this inverter.</p>
                      ) : (
                        <table className="data-table text-sm">
                          <thead>
                            <tr>
                              <th>SCB</th>
                              <th>Strings</th>
                              <th>Modules/string</th>
                              <th>Spare</th>
                            </tr>
                          </thead>
                          <tbody>
                            {inv.scbs.map((s) => (
                              <tr key={s.scb_id}>
                                <td className="font-mono text-xs">{s.scb_id}</td>
                                <td>{s.strings_per_scb ?? "—"}</td>
                                <td>{s.modules_per_string ?? "—"}</td>
                                <td>{s.spare_flag ? "Yes" : "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </div>
                  </details>
                ))}
                {filtered.length === 0 && (
                  <p className="text-sm text-stone-500">No inverters match “{filter}”.</p>
                )}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
