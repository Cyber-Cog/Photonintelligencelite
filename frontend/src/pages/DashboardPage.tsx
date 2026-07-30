import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, getResults, reportUrl } from "@/api/client";
import { BoxPlotAnalysisPanel } from "@/components/BoxPlotAnalysisPanel";
import { EvidenceInvestigateModal } from "@/components/EvidenceInvestigateModal";
import { FaultsTable } from "@/components/FaultsTable";
import { InverterComparisonPanel } from "@/components/InverterComparisonPanel";
import { JobStatusChip, JobWorkspace } from "@/components/JobWorkspace";
import { KpiStrip, type KpiStripItem } from "@/components/KpiStrip";
import { LossWaterfallBridge } from "@/components/LossWaterfallBridge";
import { OwnerActionCenter } from "@/components/OwnerActionCenter";
import { ResultCard } from "@/components/ResultCard";
import { SummaryInsightPanels } from "@/components/SummaryInsightPanels";
import { ErrorState } from "@/components/ui/ErrorState";
import { InfoBanner } from "@/components/ui/InfoBanner";
import { Spinner } from "@/components/ui/Spinner";
import { SubnavTabs } from "@/components/ui/SubnavTabs";
import { useJob } from "@/context/JobContext";
import {
  isAnalysisModule,
  moduleNavBadge,
  needsDataLine,
  orderDiagModules,
} from "@/lib/diagnosticsModules";
import { buildFaultRows, type FaultRow } from "@/lib/faultsTable";
import { diagnoseKpiGaps, fixHref } from "@/lib/missingReasons";
import { buildOwnerActions } from "@/lib/ownerActions";
import { stringHealthFromResults, worstInvertersFromResults } from "@/lib/summaryInsights";
import {
  RESULTS_SECTION_EVENT,
  RESULTS_SECTIONS,
  resolveResultsSectionId,
  type ResultsSectionId,
} from "@/lib/resultsNav";
import type { ResultObject, ResultsResponse } from "@/types";

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

/** Modules worth listing in Diagnostics folder (faults + analysis, preferred order). */
function relevantDiagModules(results: ResultObject[]): ResultObject[] {
  const { faults, analysis } = orderDiagModules(results.filter((r) => r.algorithm_id !== "kpis"));
  return [...faults, ...analysis];
}

function firstReadyModuleId(modules: ResultObject[]): string | null {
  return modules.find((r) => r.status === "ok")?.algorithm_id ?? modules[0]?.algorithm_id ?? null;
}

function DiagStatusBadge({ result }: { result: ResultObject }) {
  const meta = moduleNavBadge(result);
  return (
    <span
      className={`shrink-0 rounded-md px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${meta.className}`}
      title={meta.title}
    >
      {meta.label}
    </span>
  );
}

/** Flat Results section rail — lives in workspace aside (no nested card). */
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
    <nav className="p-2" aria-label="Results sections" data-tour="results-sidebar">
      <p className="px-2 pb-2 pt-1 text-[10px] font-bold uppercase tracking-[0.14em] text-[color:var(--pic-text-muted)]">
        Sections
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
                className={`flex w-full items-center justify-between gap-2 rounded-pic px-2.5 py-2 text-left text-[13px] font-semibold transition duration-150 ${
                  active
                    ? "bg-brand-50 text-stone-900 ring-1 ring-brand-200/80 dark:bg-brand-950/40 dark:text-amber-100 dark:ring-brand-800/50"
                    : "text-[color:var(--pic-text-secondary)] hover:bg-white/80 hover:text-[color:var(--pic-text)] dark:hover:bg-stone-800/60"
                }`}
              >
                <span>{item.label}</span>
                {badge != null ? (
                  <span
                    className={`tabular-nums rounded-pic-sm px-1.5 py-px text-[10px] font-bold ${
                      active
                        ? "bg-brand-600 text-white dark:bg-brand-500 dark:text-stone-950"
                        : "bg-[color:var(--pic-surface-muted)] text-[color:var(--pic-text-muted)]"
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
  faultModules,
  analysisModules,
  activeModuleId,
  onSelectModule,
  onCollapse,
}: {
  faultModules: ResultObject[];
  analysisModules: ResultObject[];
  activeModuleId: string | null;
  onSelectModule: (algorithmId: string) => void;
  onCollapse?: () => void;
}) {
  const total = faultModules.length + analysisModules.length;

  const renderItem = (m: ResultObject) => {
    const active = activeModuleId === m.algorithm_id;
    const tip =
      m.status === "unavailable"
        ? needsDataLine(m) ?? m.title
        : m.title + (m.summary ? ` — ${m.summary}` : "");
    return (
      <li key={m.algorithm_id} className="pl-1.5">
        <button
          type="button"
          data-results-section={m.algorithm_id}
          data-tour={`nav-diag-${m.algorithm_id}`}
          aria-current={active ? "page" : undefined}
          title={tip}
          onClick={() => onSelectModule(m.algorithm_id)}
          className={`flex w-full min-w-0 items-center gap-1.5 rounded-md px-1.5 py-1.5 text-left transition duration-150 ${
            active
              ? "bg-brand-50 text-stone-900 ring-1 ring-brand-300/90 dark:bg-brand-950/50 dark:text-amber-50 dark:ring-brand-700/60"
              : "text-stone-600 hover:bg-stone-50 hover:text-stone-900 dark:text-stone-300 dark:hover:bg-stone-800/70 dark:hover:text-amber-100"
          }`}
        >
          <span
            className={`shrink-0 ${active ? "text-brand-600 dark:text-brand-400" : "text-stone-400 dark:text-stone-500"}`}
          >
            <FileIcon />
          </span>
          {/* break-normal + truncate — no mid-word wraps in the modules list */}
          <span className="min-w-0 flex-1 truncate break-normal text-[12px] font-semibold leading-tight">
            {m.title}
          </span>
          <DiagStatusBadge result={m} />
        </button>
      </li>
    );
  };

  return (
    <nav
      className="flex h-full min-h-0 w-full flex-col overflow-hidden rounded-pic-lg border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)]"
      aria-label="Diagnostic modules"
      data-tour="diagnostics-folder-list"
    >
      <div className="flex shrink-0 items-center gap-2 border-b border-[color:var(--pic-border-subtle)] px-3 py-2.5">
        <span className="text-brand-600 dark:text-brand-400">
          <FolderIcon open />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[color:var(--pic-text-muted)]">
            Modules
          </p>
          <p className="text-[11px] font-medium text-[color:var(--pic-text-secondary)]">
            {total} {total === 1 ? "check" : "checks"}
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

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-2">
        {total === 0 ? (
          <p className="px-2 py-3 text-[11px] text-[color:var(--pic-text-muted)]">No modules for this run</p>
        ) : (
          <ul className="space-y-0.5">
            {faultModules.length > 0 && (
              <li className="pointer-events-none select-none px-2 pb-1 pt-1.5" aria-hidden="true">
                <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.1em] text-[color:var(--pic-text-muted)]">
                  <FolderIcon open />
                  <span>Faults</span>
                </div>
              </li>
            )}
            {faultModules.map(renderItem)}

            {analysisModules.length > 0 && (
              <li className="pointer-events-none select-none px-2 pb-1 pt-3" aria-hidden="true">
                <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.1em] text-[color:var(--pic-text-muted)]">
                  <FolderIcon open />
                  <span>Box plot analysis</span>
                </div>
              </li>
            )}
            {analysisModules.map(renderItem)}
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
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
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
    let timer: number | undefined;
    let attempts = 0;

    const load = () => {
      setLoading(true);
      setError(null);
      setErrorStatus(null);
      getResults(jobId)
        .then((res) => {
          if (cancelled) return;
          setData(res);
          setLoading(false);
        })
        .catch((err) => {
          if (cancelled) return;
          const status = err instanceof ApiError ? err.status : null;
          const msg = err instanceof ApiError ? err.message : "Could not load results.";
          // Analysis may still be finishing when Processing navigates early — retry briefly.
          if ((status === 404 || status === 409 || /not (ready|complete)|still running/i.test(msg)) && attempts < 40) {
            attempts += 1;
            timer = window.setTimeout(load, 1500);
            return;
          }
          setError(msg);
          setErrorStatus(status);
          setLoading(false);
        });
    };

    load();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [jobId]);

  const sortedResults = useMemo(() => {
    if (!data) return [];
    const rank: Record<string, number> = { ok: 0, error: 1, unavailable: 2 };
    return [...data.results].sort((a, b) => (rank[a.status] ?? 3) - (rank[b.status] ?? 3));
  }, [data]);

  const diagModules = useMemo(() => relevantDiagModules(sortedResults), [sortedResults]);
  const { faultModules, analysisModules } = useMemo(() => {
    const { faults, analysis } = orderDiagModules(diagModules);
    return { faultModules: faults, analysisModules: analysis };
  }, [diagModules]);
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

  const worstInverters = useMemo(
    () => (data ? worstInvertersFromResults(data.results) : []),
    [data],
  );
  const stringHealth = useMemo(() => {
    if (!data) return { rows: [], healthyNote: null as string | null };
    return stringHealthFromResults(data.results);
  }, [data]);

  const kpiItems = useMemo((): KpiStripItem[] => {
    if (!data || !jobId) return [];
    const gaps = kpiGaps;
    return [
      {
        label: "Performance ratio",
        value: fmt(data.kpis.performance_ratio_pct),
        unit: "%",
        icon: "pr",
        tone: "good",
        missingHint: gaps?.performance_ratio_pct?.message,
        missingHref: gaps?.performance_ratio_pct ? fixHref(jobId, gaps.performance_ratio_pct.fix) : null,
      },
      {
        label: "Specific yield",
        value: fmt(data.kpis.specific_yield_kwh_per_kwp),
        unit: "kWh/kWp",
        icon: "yield",
        missingHint: gaps?.specific_yield_kwh_per_kwp?.message,
        missingHref: gaps?.specific_yield_kwh_per_kwp
          ? fixHref(jobId, gaps.specific_yield_kwh_per_kwp.fix)
          : null,
      },
      {
        label: "Plant availability",
        value: fmt(data.kpis.plant_availability_pct),
        unit: "%",
        icon: "availability",
        tone: "good",
        missingHint: gaps?.plant_availability_pct?.message,
        missingHref: gaps?.plant_availability_pct
          ? fixHref(jobId, gaps.plant_availability_pct.fix)
          : null,
      },
      {
        label: "Energy loss",
        value: fmt(data.kpis.estimated_energy_loss_kwh, 0),
        unit: "kWh",
        icon: "loss",
        tone: data.kpis.estimated_energy_loss_kwh ? "bad" : "neutral",
      },
      {
        label: "Revenue loss",
        value: data.kpis.revenue_loss_available ? fmt(data.kpis.revenue_loss_inr, 0) : null,
        unit: "₹",
        icon: "revenue",
        tone: "bad",
        missingHint: gaps?.revenue_loss_inr?.message,
        missingHref: gaps?.revenue_loss_inr ? fixHref(jobId, gaps.revenue_loss_inr.fix) : null,
      },
      {
        label: "Faults",
        value: data.kpis.fault_count,
        icon: "faults",
        tone: data.kpis.fault_count > 0 ? "bad" : "neutral",
      },
    ];
  }, [data, kpiGaps, jobId]);

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

  if (loading) {
    return (
      <div className="tool-enter flex h-full min-h-0 flex-1 items-center justify-center gap-3 text-sm text-[color:var(--pic-text-muted)]">
        <Spinner className="h-5 w-5" /> Loading results…
      </div>
    );
  }

  if (error) {
    return (
      <div className="tool-enter mx-auto flex max-w-lg flex-col gap-3 py-10">
        <ErrorState
          title="Could not load results"
          message={error}
          hint={
            errorStatus === 410
              ? "Result files for this job were removed after the retention window, or lost when the server restarted (ephemeral disk). Start a new analysis with the same data to regenerate."
              : undefined
          }
        />
        {errorStatus === 410 || errorStatus === 404 ? (
          <button type="button" className="btn-primary text-sm" onClick={handleNewAnalysis}>
            Re-run analysis
          </button>
        ) : null}
      </div>
    );
  }

  if (!data) return null;

  const statusTone = blockedCount > 0 && okCount > 0 ? "warn" : okCount > 0 ? "ok" : "warn";

  return (
    <JobWorkspace
      title="Results"
      titleTour="results-welcome"
      subtitle={`${okCount} modules ready · ${blockedCount} need data`}
      status={
        <JobStatusChip tone={statusTone}>
          {thinResults ? "Limited coverage" : blockedCount > 0 ? "Partial mapping" : "Analysis ready"}
        </JobStatusChip>
      }
      actions={
        <div className="flex shrink-0 flex-wrap items-center gap-2" data-tour="download-reports">
          <a className="btn-secondary !px-3 !py-1.5 text-xs" href={reportUrl(jobId, "xlsx")}>
            Excel
          </a>
          <a className="btn-primary !px-3 !py-1.5 text-xs" href={reportUrl(jobId, "pdf")}>
            PDF
          </a>
        </div>
      }
      chromeExtra={
        <>
          <div className="tool-sticky-bar lg:hidden">
            <SubnavTabs
              items={mobileTabs}
              activeId={activeSection}
              onSelect={(id) => selectSection(id as ResultsSectionId)}
              ariaLabel="Results sections"
              inset
            />
          </div>
          <KpiStrip items={kpiItems} flush />
          {thinResults ? (
            <div className="border-t border-[color:var(--pic-border-subtle)] px-3 py-2 sm:px-4">
              <InfoBanner
                tone="warning"
                title="Limited module coverage"
                className="!rounded-pic-lg !px-3 !py-2 !shadow-none"
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
          ) : null}
        </>
      }
      aside={
        <ResultsSidebar
          activeSection={activeSection}
          onSelectSection={selectSection}
          faultCount={data.kpis.fault_count}
          issueCount={ownerActions?.issueCount ?? 0}
        />
      }
      flushMain={activeSection === "diagnostics" || activeSection === "bridge"}
      mainRef={mainPaneRef}
      footer={
        <button type="button" className="btn-ghost !px-2 !py-0.5 text-[11px]" onClick={handleNewAnalysis}>
          Start new analysis
        </button>
      }
    >
      {activeSection === "summary" && (
        <div id="results-actions" data-results-pane="summary" className="job-pane flex flex-col gap-5 pb-6">
          {ownerActions ? (
            <OwnerActionCenter
              model={ownerActions}
              onInvestigate={investigateFinding}
              onModule={jumpToModule}
              onSection={(id) => selectSection(id)}
            />
          ) : (
            <div className="rounded-pic-lg border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] px-4 py-6 text-sm text-[color:var(--pic-text-muted)]">
              No owner actions for this run.
            </div>
          )}

          <InverterComparisonPanel rows={data.kpis.inverter_pr ?? []} />

          <SummaryInsightPanels
            worstInverters={worstInverters}
            stringHealth={stringHealth.rows}
            stringHealthyNote={stringHealth.healthyNote}
            onModule={jumpToModule}
          />
        </div>
      )}

      {activeSection === "bridge" && (
        <div
          id="results-bridge"
          data-tour="loss-bridge"
          data-results-pane="bridge"
          className="flex min-h-0 flex-1 flex-col p-3"
        >
          <LossWaterfallBridge kpis={data.kpis} results={data.results} jobId={jobId} fillHeight />
        </div>
      )}

      {activeSection === "faults" && (
        <div id="results-faults" data-tour="faults-table" data-results-pane="faults" className="job-pane pb-6">
          <FaultsTable results={data.results} />
        </div>
      )}

      {activeSection === "diagnostics" && (
        <div
          className="flex min-h-0 flex-1 flex-col gap-3 p-3 lg:flex-row"
          data-tour="diagnostics"
          data-results-pane="diagnostics"
        >
          {folderCollapsed && (
            <div className="hidden shrink-0 lg:flex lg:h-full lg:w-10 lg:flex-col">
              <button
                type="button"
                className="flex h-full w-full flex-col items-center gap-2 rounded-pic-lg border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] px-1 py-3 text-[color:var(--pic-text-muted)] transition hover:border-brand-300 hover:bg-brand-50/40 hover:text-brand-700 dark:hover:border-brand-700 dark:hover:bg-brand-950/30 dark:hover:text-brand-300"
                onClick={() => setFolderCollapsed(false)}
                title="Expand module folder"
                aria-label="Expand module folder"
                data-tour="diagnostics-folder-expand"
              >
                <FolderIcon open={false} />
                <span
                  className="text-[9px] font-bold uppercase tracking-[0.14em]"
                  style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
                >
                  Modules
                </span>
              </button>
            </div>
          )}
          <div
            className={`max-h-[min(32vh,14rem)] min-w-0 shrink-0 overflow-hidden lg:max-h-none lg:h-full lg:w-[16rem] lg:max-w-[30%] lg:shrink-0 ${
              folderCollapsed ? "lg:hidden" : ""
            }`}
          >
            <DiagnosticsFolderList
              faultModules={faultModules}
              analysisModules={analysisModules}
              activeModuleId={activeModuleId}
              onSelectModule={selectModule}
              onCollapse={() => setFolderCollapsed(true)}
            />
          </div>

          <div className="min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain lg:h-full lg:min-w-[70%]">
            {!activeModule ? (
              <div
                className="flex h-full min-h-[12rem] flex-col items-center justify-center rounded-pic-lg border border-dashed border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] px-4 py-8 text-center"
                data-tour="diagnostics-empty"
              >
                <p className="font-display text-sm font-semibold text-[color:var(--pic-text)]">
                  Select a diagnostic module
                </p>
                <p className="mt-1 max-w-sm text-xs leading-relaxed text-[color:var(--pic-text-muted)]">
                  {diagModules.length === 0
                    ? "No diagnostic modules available for this run."
                    : "Choose a fault check or box plot analysis from the folder."}
                </p>
              </div>
            ) : (
              <div
                id={`module-${activeModule.algorithm_id}`}
                className={`transition ${
                  highlightId === activeModule.algorithm_id
                    ? "rounded-pic-lg ring-2 ring-brand-500 ring-offset-1 dark:ring-offset-stone-950"
                    : ""
                }`}
              >
                {activeModule.algorithm_id === "box_plot" &&
                activeModule.status === "ok" &&
                isAnalysisModule(activeModule.algorithm_id, activeModule) ? (
                  <BoxPlotAnalysisPanel result={activeModule} />
                ) : (
                  <ResultCard key={activeModule.algorithm_id} result={activeModule} standalone />
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {investigateRow && (
        <EvidenceInvestigateModal row={investigateRow} onClose={() => setInvestigateRow(null)} />
      )}
    </JobWorkspace>
  );
}
