import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, getResults, reportUrl } from "@/api/client";
import { EvidenceInvestigateModal } from "@/components/EvidenceInvestigateModal";
import { FaultsTable } from "@/components/FaultsTable";
import { JobNav } from "@/components/JobNav";
import { KpiCard } from "@/components/KpiCard";
import { LossWaterfallBridge } from "@/components/LossWaterfallBridge";
import { OwnerActionCenter } from "@/components/OwnerActionCenter";
import { ResultCard } from "@/components/ResultCard";
import { ErrorState } from "@/components/ui/ErrorState";
import { InfoBanner } from "@/components/ui/InfoBanner";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionPanel } from "@/components/ui/SectionPanel";
import { Spinner } from "@/components/ui/Spinner";
import { SubnavTabs } from "@/components/ui/SubnavTabs";
import { useJob } from "@/context/JobContext";
import { buildFaultRows, type FaultRow } from "@/lib/faultsTable";
import { diagnoseKpiGaps, fixHref } from "@/lib/missingReasons";
import { buildOwnerActions } from "@/lib/ownerActions";
import {
  RESULTS_SECTION_EVENT,
  RESULTS_SECTIONS,
  resolveResultsSectionId,
  type ResultsSectionId,
} from "@/lib/resultsNav";
import type { ResultObject, ResultsResponse } from "@/types";

/** Preferred Diagnostics module order (codex-like fault modules first). */
const DIAG_ORDER = [
  "disconnected_strings",
  "clipping_power",
  "clipping_current",
  "inverter_efficiency",
  "module_damage",
  "string_outlier",
  "box_plot",
];

/** Desktop shell: fill viewport below app header + main padding (JobNav/header sit inside). */
const RESULTS_SHELL =
  "lg:h-[calc(100dvh-6rem)] lg:max-h-[calc(100dvh-6rem)] lg:overflow-hidden";

function fmt(value: number | null, digits = 1): string | null {
  if (value === null || value === undefined) return null;
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function FolderIcon({ open = false }: { open?: boolean }) {
  return (
    <svg
      viewBox="0 0 16 16"
      className="h-3.5 w-3.5 shrink-0"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {open ? (
        <>
          <path d="M1.5 6.5h13v5.25A1.75 1.75 0 0 1 12.75 13.5H3.25A1.75 1.75 0 0 1 1.5 11.75V6.5Z" />
          <path d="M1.5 6.5V4.25A1.75 1.75 0 0 1 3.25 2.5h2.2c.4 0 .78.16 1.06.44L7.5 4h5.25A1.75 1.75 0 0 1 14.5 5.75V6.5" />
        </>
      ) : (
        <path d="M1.5 4.25A1.75 1.75 0 0 1 3.25 2.5h2.2c.4 0 .78.16 1.06.44L7.5 4h5.25A1.75 1.75 0 0 1 14.5 5.75v6A1.75 1.75 0 0 1 12.75 13.5H3.25A1.75 1.75 0 0 1 1.5 11.75v-7.5Z" />
      )}
    </svg>
  );
}

function FileIcon() {
  return (
    <svg
      viewBox="0 0 16 16"
      className="h-3.5 w-3.5 shrink-0 opacity-90"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M4 1.75h4.5L12.5 5.75v8.5A1.25 1.25 0 0 1 11.25 15.5h-7.5A1.25 1.25 0 0 1 2.5 14.25v-11A1.25 1.25 0 0 1 3.75 2" />
      <path d="M8.5 1.75V5.5H12.25" />
    </svg>
  );
}

/** Modules worth listing in Diagnostics folder (preferred order, then the rest). */
function relevantDiagModules(results: ResultObject[]): ResultObject[] {
  const byId = new Map(results.map((r) => [r.algorithm_id, r]));
  const ordered: ResultObject[] = [];
  const placed = new Set<string>();

  for (const id of DIAG_ORDER) {
    const r = byId.get(id);
    if (!r) continue;
    ordered.push(r);
    placed.add(id);
  }
  for (const r of results) {
    if (placed.has(r.algorithm_id)) continue;
    ordered.push(r);
  }
  return ordered;
}

function firstReadyModuleId(modules: ResultObject[]): string | null {
  return modules.find((r) => r.status === "ok")?.algorithm_id ?? modules[0]?.algorithm_id ?? null;
}

function moduleNavBadge(r: ResultObject): {
  label: string;
  className: string;
} {
  if (r.status === "unavailable") {
    return {
      label: "Needs input",
      className:
        "bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200",
    };
  }
  if (r.status === "error") {
    return {
      label: "Error",
      className: "bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300",
    };
  }
  const hasFindings =
    (r.loss_energy_kwh ?? 0) > 0.5 ||
    (r.severity != null && ["critical", "high", "medium"].includes(r.severity)) ||
    r.tables.some((t) => t.rows.length > 0);
  if (hasFindings) {
    return {
      label: "Findings",
      className: "bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-200",
    };
  }
  return {
    label: "Ready",
    className:
      "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
  };
}

function DiagStatusBadge({ result }: { result: ResultObject }) {
  const meta = moduleNavBadge(result);
  return (
    <span
      className={`shrink-0 rounded-md px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${meta.className}`}
    >
      {meta.label}
    </span>
  );
}

/** Flat 4-item Results nav — no nested Diagnostics children. */
function ResultsSidebar({
  activeSection,
  onSelectSection,
  faultCount,
  issueCount,
}: {
  activeSection: ResultsSectionId;
  onSelectSection: (id: ResultsSectionId) => void;
  faultCount: number | null | undefined;
  issueCount: number;
}) {
  return (
    <nav
      className="hidden h-fit w-[220px] shrink-0 self-start rounded-2xl border border-stone-200/90 bg-white/95 p-2 dark:border-stone-700 dark:bg-stone-900 lg:block"
      aria-label="Results sections"
      data-tour="results-sidebar"
    >
      <p className="px-2.5 pb-2 pt-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-stone-400">
        Navigate
      </p>
      <ul className="space-y-0.5">
        {RESULTS_SECTIONS.map((item) => {
          const active = item.id === activeSection;
          const badge =
            item.id === "faults" && faultCount != null && faultCount > 0
              ? faultCount
              : item.id === "summary" && issueCount > 0
                ? issueCount
                : null;
          return (
            <li key={item.id}>
              <button
                type="button"
                data-results-section={item.id}
                data-tour={item.tour}
                aria-current={active ? "page" : undefined}
                onClick={() => onSelectSection(item.id)}
                className={`flex w-full items-center justify-between gap-2 rounded-xl px-2.5 py-2 text-left text-xs font-semibold transition duration-150 ${
                  active
                    ? "bg-brand-50 text-stone-900 ring-1 ring-brand-200/80 dark:bg-brand-950/40 dark:text-amber-100 dark:ring-brand-800/50"
                    : "text-stone-600 hover:bg-stone-50 hover:text-stone-900 dark:text-stone-300 dark:hover:bg-stone-800/60 dark:hover:text-amber-100"
                }`}
              >
                <span>{item.label}</span>
                {badge != null ? (
                  <span
                    className={`tabular-nums rounded-md px-1.5 py-0.5 text-[10px] font-bold ${
                      active
                        ? "bg-brand-600 text-white dark:bg-brand-500 dark:text-stone-950"
                        : "bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300"
                    }`}
                  >
                    {badge}
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** Vertical folder-style module list (lives inside Diagnostics pane only). */
function DiagnosticsFolderList({
  modules,
  activeModuleId,
  onSelectModule,
  onCollapse,
}: {
  modules: ResultObject[];
  activeModuleId: string | null;
  onSelectModule: (algorithmId: string) => void;
  onCollapse?: () => void;
}) {
  return (
    <nav
      className="flex h-full min-h-0 w-full flex-col rounded-2xl border border-stone-200/90 bg-white/95 dark:border-stone-700 dark:bg-stone-900"
      aria-label="Diagnostic modules"
      data-tour="diagnostics-folder-list"
    >
      <div className="flex shrink-0 items-center gap-1.5 border-b border-stone-100 px-2.5 py-2 dark:border-stone-800">
        <span className="text-brand-600 dark:text-brand-400">
          <FolderIcon open />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-stone-400">Modules</p>
          <p className="text-[11px] font-medium text-stone-500 dark:text-stone-400">
            {modules.length} {modules.length === 1 ? "check" : "checks"}
          </p>
        </div>
        {onCollapse && (
          <button
            type="button"
            className="btn-ghost hidden h-7 w-7 shrink-0 items-center justify-center p-0 text-stone-400 lg:inline-flex"
            onClick={onCollapse}
            title="Collapse folder"
            aria-label="Collapse module folder"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
            </svg>
          </button>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-1.5">
        {modules.length === 0 ? (
          <p className="px-2 py-3 text-[11px] text-stone-400">No modules for this run</p>
        ) : (
          <ul className="space-y-0.5">
            <li className="pointer-events-none select-none px-2 py-1" aria-hidden="true">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold text-stone-500 dark:text-stone-400">
                <span className="text-stone-400 dark:text-stone-500">
                  <FolderIcon open />
                </span>
                <span>Fault modules</span>
              </div>
            </li>
            {modules.map((m) => {
              const active = activeModuleId === m.algorithm_id;
              return (
                <li key={m.algorithm_id} className="pl-3">
                  <button
                    type="button"
                    data-results-section={m.algorithm_id}
                    data-tour={`nav-diag-${m.algorithm_id}`}
                    aria-current={active ? "page" : undefined}
                    onClick={() => onSelectModule(m.algorithm_id)}
                    className={`flex w-full items-start gap-1.5 rounded-lg px-2 py-1.5 text-left transition duration-150 ${
                      active
                        ? "bg-brand-50 text-stone-900 shadow-sm ring-1 ring-brand-300/90 dark:bg-brand-950/50 dark:text-amber-50 dark:ring-brand-700/60"
                        : "text-stone-600 hover:bg-stone-50 hover:text-stone-900 dark:text-stone-300 dark:hover:bg-stone-800/70 dark:hover:text-amber-100"
                    }`}
                  >
                    <span
                      className={`mt-0.5 ${active ? "text-brand-600 dark:text-brand-400" : "text-stone-400 dark:text-stone-500"}`}
                    >
                      <FileIcon />
                    </span>
                    <span className="min-w-0 flex-1 break-words text-[12px] font-semibold leading-snug">
                      {m.title}
                    </span>
                    <DiagStatusBadge result={m} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </nav>
  );
}

export function DashboardPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const { clearJob } = useJob();

  const [data, setData] = useState<ResultsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<ResultsSectionId>("summary");
  const [activeModuleId, setActiveModuleId] = useState<string | null>(null);
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const [investigateRow, setInvestigateRow] = useState<FaultRow | null>(null);
  const [folderCollapsed, setFolderCollapsed] = useState(false);
  const mainPaneRef = useRef<HTMLDivElement>(null);
  const modulesRef = useRef<ResultObject[]>([]);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    setLoading(true);
    getResults(jobId)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load results.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  const sortedResults = useMemo(() => {
    if (!data) return [];
    const rank: Record<string, number> = { ok: 0, error: 1, unavailable: 2 };
    return [...data.results].sort((a, b) => (rank[a.status] ?? 3) - (rank[b.status] ?? 3));
  }, [data]);

  const diagModules = useMemo(() => relevantDiagModules(sortedResults), [sortedResults]);
  modulesRef.current = diagModules;

  const activeModule = useMemo(
    () => diagModules.find((r) => r.algorithm_id === activeModuleId) ?? null,
    [diagModules, activeModuleId],
  );

  const scrollMainTop = useCallback(() => {
    mainPaneRef.current?.scrollTo({ top: 0, behavior: "auto" });
    window.scrollTo({ top: 0, behavior: "auto" });
  }, []);

  const selectSection = useCallback(
    (id: ResultsSectionId) => {
      setActiveSection(id);
      if (id === "diagnostics") {
        setActiveModuleId((cur) => cur ?? firstReadyModuleId(modulesRef.current));
      }
      scrollMainTop();
    },
    [scrollMainTop],
  );

  const selectModule = useCallback(
    (algorithmId: string) => {
      setActiveSection("diagnostics");
      setActiveModuleId(algorithmId);
      scrollMainTop();
    },
    [scrollMainTop],
  );

  // Tour / deep-link: section id or algorithm_id (opens Diagnostics module)
  useEffect(() => {
    const onSection = (ev: Event) => {
      const id = (ev as CustomEvent).detail;
      if (typeof id !== "string" || !id) return;

      const section = resolveResultsSectionId(id);
      if (section) {
        setActiveSection(section);
        if (section === "diagnostics") {
          setActiveModuleId((cur) => cur ?? firstReadyModuleId(modulesRef.current));
        }
        scrollMainTop();
        return;
      }

      const modules = modulesRef.current;
      if (modules.some((m) => m.algorithm_id === id)) {
        setActiveSection("diagnostics");
        setActiveModuleId(id);
        scrollMainTop();
      }
    };
    window.addEventListener(RESULTS_SECTION_EVENT, onSection);
    return () => window.removeEventListener(RESULTS_SECTION_EVENT, onSection);
  }, [scrollMainTop]);

  const okCount = sortedResults.filter((r) => r.status === "ok").length;
  const blockedCount = sortedResults.filter((r) => r.status === "unavailable").length;
  const thinResults =
    Boolean(data) &&
    okCount === 0 &&
    (data!.kpis.specific_yield_kwh_per_kwp == null || data!.kpis.specific_yield_kwh_per_kwp === 0) &&
    data!.kpis.performance_ratio_pct == null;

  const kpiGaps = useMemo(() => (data ? diagnoseKpiGaps(data.kpis) : null), [data]);

  const ownerActions = useMemo(
    () => (data && jobId ? buildOwnerActions(jobId, data.kpis, data.results) : null),
    [data, jobId],
  );

  const faultRows = useMemo(() => (data ? buildFaultRows(data.results) : []), [data]);

  const jumpToModule = useCallback(
    (algorithmId: string) => {
      selectModule(algorithmId);
      setHighlightId(algorithmId);
      window.setTimeout(() => setHighlightId(null), 1800);
    },
    [selectModule],
  );

  const investigateFinding = useCallback(
    (algorithmId: string) => {
      const row = faultRows.find((r) => r.algorithmId === algorithmId) ?? null;
      if (row) {
        setInvestigateRow(row);
        return;
      }
      selectSection("faults");
      setHighlightId(algorithmId);
      window.setTimeout(() => setHighlightId(null), 2200);
    },
    [faultRows, selectSection],
  );

  if (!jobId) return null;

  const handleNewAnalysis = () => {
    clearJob();
    navigate("/upload");
  };

  const mobileTabs = RESULTS_SECTIONS.map(({ id, label }) => ({ id, label }));

  return (
    <div className={`tool-enter flex flex-col pb-8 ${RESULTS_SHELL} lg:pb-0`}>
      <div className="shrink-0">
        <JobNav />

        <div className="mb-3" {...(data ? { "data-tour": "results-welcome" } : {})}>
          <PageHeader
            eyebrow="Analysis output"
            title="Results"
            description={
              data
                ? `${okCount} modules ready · ${blockedCount} need input · KPIs, actions, bridge, faults, diagnostics`
                : "Plant KPIs, owner actions, loss bridge, faults, and per-module diagnostics"
            }
            actions={
              data ? (
                <div className="flex flex-wrap items-center gap-2" data-tour="download-reports">
                  <a className="btn-secondary text-xs" href={reportUrl(jobId, "xlsx")}>
                    Download Excel
                  </a>
                  <a className="btn-primary text-xs" href={reportUrl(jobId, "pdf")}>
                    Download PDF
                  </a>
                </div>
              ) : undefined
            }
          />
        </div>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-stone-500">
          <Spinner className="h-4 w-4" /> Loading results…
        </div>
      )}

      {!loading && error && <ErrorState title="Could not load results" message={error} />}

      {!loading && data && (
        <>
          {/* Mobile: flat section tabs */}
          <div className="tool-sticky-bar sticky top-14 z-10 mb-3 w-full shrink-0 lg:hidden">
            <SubnavTabs
              items={mobileTabs}
              activeId={activeSection}
              onSelect={(id) => selectSection(id as ResultsSectionId)}
              ariaLabel="Results sections"
            />
          </div>

          {thinResults && (
            <div className="mb-3 shrink-0">
              <InfoBanner
                tone="warning"
                title="Limited module coverage"
                actions={
                  <Link
                    to={`/jobs/${jobId}/setup#mapping&field=ac_power_kw`}
                    className="text-xs font-semibold text-amber-900 underline dark:text-amber-200"
                  >
                    Open Setup: AC power mapping
                  </Link>
                }
              >
                With AC and weather signals only, plant KPIs and clipping-by-power can run once AC power and POA are
                mapped. String-level faults and inverter efficiency require additional DC and architecture inputs.
              </InfoBanner>
            </div>
          )}

          <div className="flex min-h-0 flex-1 items-stretch gap-4 lg:overflow-hidden">
            <ResultsSidebar
              activeSection={activeSection}
              onSelectSection={selectSection}
              faultCount={data.kpis.fault_count}
              issueCount={ownerActions?.issueCount ?? 0}
            />

            <div
              ref={mainPaneRef}
              className={`min-h-0 min-w-0 flex-1 pb-2 ${
                activeSection === "diagnostics"
                  ? "flex flex-col lg:overflow-hidden"
                  : "lg:overflow-y-auto lg:overscroll-contain"
              }`}
              data-tour="results-main"
            >
              {activeSection === "summary" && (
                <div className="space-y-4" data-results-pane="summary">
                  <SectionPanel
                    id="results-summary"
                    title="Summary"
                    description="Plant KPIs for this run"
                    scrollMargin={false}
                  >
                    <div
                      className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-3 xl:grid-cols-6"
                      data-tour="summary-kpis"
                    >
                      <KpiCard
                        label="Performance ratio"
                        value={fmt(data.kpis.performance_ratio_pct)}
                        unit="%"
                        icon="pr"
                        index={0}
                        tone="good"
                        missingHint={kpiGaps?.performance_ratio_pct?.message}
                        missingHref={
                          kpiGaps?.performance_ratio_pct ? fixHref(jobId, kpiGaps.performance_ratio_pct.fix) : null
                        }
                      />
                      <KpiCard
                        label="Specific yield"
                        value={fmt(data.kpis.specific_yield_kwh_per_kwp)}
                        unit="kWh/kWp"
                        icon="yield"
                        index={1}
                        missingHint={kpiGaps?.specific_yield_kwh_per_kwp?.message}
                        missingHref={
                          kpiGaps?.specific_yield_kwh_per_kwp
                            ? fixHref(jobId, kpiGaps.specific_yield_kwh_per_kwp.fix)
                            : null
                        }
                      />
                      <KpiCard
                        label="Plant availability"
                        value={fmt(data.kpis.plant_availability_pct)}
                        unit="%"
                        icon="availability"
                        index={2}
                        tone="good"
                        missingHint={kpiGaps?.plant_availability_pct?.message}
                        missingHref={
                          kpiGaps?.plant_availability_pct
                            ? fixHref(jobId, kpiGaps.plant_availability_pct.fix)
                            : null
                        }
                      />
                      <KpiCard
                        label="Estimated energy loss"
                        value={fmt(data.kpis.estimated_energy_loss_kwh, 0)}
                        unit="kWh"
                        icon="loss"
                        index={3}
                        tone={data.kpis.estimated_energy_loss_kwh ? "bad" : "neutral"}
                      />
                      <KpiCard
                        label="Revenue loss"
                        value={data.kpis.revenue_loss_available ? fmt(data.kpis.revenue_loss_inr, 0) : null}
                        unit="₹"
                        icon="revenue"
                        index={4}
                        tone="bad"
                        missingHint={kpiGaps?.revenue_loss_inr?.message}
                        missingHref={
                          kpiGaps?.revenue_loss_inr ? fixHref(jobId, kpiGaps.revenue_loss_inr.fix) : null
                        }
                      />
                      <KpiCard
                        label="Faults detected"
                        value={data.kpis.fault_count}
                        icon="faults"
                        index={5}
                        tone={data.kpis.fault_count > 0 ? "bad" : "neutral"}
                      />
                    </div>
                  </SectionPanel>

                  <div
                    id="results-actions"
                    data-results-pane="actions"
                    className="rounded-2xl border border-stone-200/90 bg-white/95 p-4 sm:p-5 dark:border-stone-700 dark:bg-stone-900"
                  >
                    {ownerActions ? (
                      <OwnerActionCenter
                        model={ownerActions}
                        onInvestigate={investigateFinding}
                        onModule={jumpToModule}
                        onSection={(id) => selectSection(id)}
                      />
                    ) : (
                      <p className="text-sm text-stone-500">No owner actions for this run.</p>
                    )}
                  </div>
                </div>
              )}

              {activeSection === "bridge" && (
                <div id="results-bridge" data-tour="loss-bridge" data-results-pane="bridge">
                  <LossWaterfallBridge kpis={data.kpis} results={data.results} jobId={jobId} />
                </div>
              )}

              {activeSection === "faults" && (
                <div id="results-faults" data-tour="faults-table" data-results-pane="faults">
                  <FaultsTable results={data.results} />
                </div>
              )}

              {activeSection === "diagnostics" && (
                <div
                  className="flex min-h-0 flex-1 flex-col gap-3 lg:flex-row lg:gap-3"
                  data-tour="diagnostics"
                  data-results-pane="diagnostics"
                >
                  {/* Mobile: always show folder; desktop: ~188px or collapsed rail so detail ≥70% */}
                  {folderCollapsed && (
                    <div className="hidden shrink-0 lg:flex lg:h-full lg:w-11 lg:flex-col">
                      <button
                        type="button"
                        className="flex h-full w-full flex-col items-center gap-2 rounded-2xl border border-stone-200/90 bg-white/95 px-1.5 py-3 text-stone-500 transition hover:border-brand-300 hover:bg-brand-50/40 hover:text-brand-700 dark:border-stone-700 dark:bg-stone-900 dark:hover:border-brand-700 dark:hover:bg-brand-950/30 dark:hover:text-brand-300"
                        onClick={() => setFolderCollapsed(false)}
                        title="Expand module folder"
                        aria-label="Expand module folder"
                        data-tour="diagnostics-folder-expand"
                      >
                        <FolderIcon open={false} />
                        <span
                          className="text-[10px] font-bold uppercase tracking-[0.14em]"
                          style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
                        >
                          Modules
                        </span>
                      </button>
                    </div>
                  )}
                  <div
                    className={`max-h-[min(36vh,16rem)] shrink-0 overflow-hidden lg:max-h-none lg:h-full lg:w-[188px] lg:max-w-[22%] lg:shrink-0 ${
                      folderCollapsed ? "lg:hidden" : ""
                    }`}
                  >
                    <DiagnosticsFolderList
                      modules={diagModules}
                      activeModuleId={activeModuleId}
                      onSelectModule={selectModule}
                      onCollapse={() => setFolderCollapsed(true)}
                    />
                  </div>

                  <div className="min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain lg:h-full lg:min-w-[70%]">
                    {!activeModule ? (
                      <div
                        className="flex min-h-[20rem] h-full flex-col items-center justify-center rounded-2xl border border-dashed border-stone-300/90 bg-stone-50/60 px-6 py-12 text-center dark:border-stone-700 dark:bg-stone-900/40"
                        data-tour="diagnostics-empty"
                      >
                        <p className="font-display text-sm font-semibold text-stone-800 dark:text-stone-100">
                          Select a diagnostic module
                        </p>
                        <p className="mt-1.5 max-w-sm text-xs leading-relaxed text-stone-500 dark:text-stone-400">
                          {diagModules.length === 0
                            ? "No diagnostic modules available for this run."
                            : "Choose a module from the folder — summary and findings open here; charts via Investigate."}
                        </p>
                      </div>
                    ) : (
                      <div
                        id={`module-${activeModule.algorithm_id}`}
                        className={`transition ${
                          highlightId === activeModule.algorithm_id
                            ? "rounded-2xl ring-2 ring-brand-500 ring-offset-2 dark:ring-offset-stone-950"
                            : ""
                        }`}
                      >
                        <ResultCard key={activeModule.algorithm_id} result={activeModule} standalone />
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          {investigateRow && (
            <EvidenceInvestigateModal row={investigateRow} onClose={() => setInvestigateRow(null)} />
          )}
        </>
      )}

      <div className="mt-4 flex shrink-0 justify-center border-t border-stone-200/80 pt-3 dark:border-stone-800/80 lg:mt-2 lg:pt-2">
        <button type="button" className="btn-ghost text-xs" onClick={handleNewAnalysis}>
          Start new analysis
        </button>
      </div>
    </div>
  );
}
