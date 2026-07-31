import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, getFaultCategories, getResults, reportUrl } from "@/api/client";
import { BoxPlotAnalysisPanel } from "@/components/BoxPlotAnalysisPanel";
import { EvidenceInvestigateModal } from "@/components/EvidenceInvestigateModal";
import { FaultsTable } from "@/components/FaultsTable";
import { InverterComparisonPanel } from "@/components/InverterComparisonPanel";
import { JobStatusChip, JobWorkspace } from "@/components/JobWorkspace";
import { KpiStrip, type KpiStripItem } from "@/components/KpiStrip";
import { LossWaterfallBridge } from "@/components/LossWaterfallBridge";
import { OwnerActionCenter } from "@/components/OwnerActionCenter";
import { ResultCard } from "@/components/ResultCard";
import { ResultsSidebar } from "@/components/ResultsSidebar";
import { RunIntegrityPanel } from "@/components/RunIntegrityPanel";
import { SummaryInsightPanels } from "@/components/SummaryInsightPanels";
import { ErrorState } from "@/components/ui/ErrorState";
import { InfoBanner } from "@/components/ui/InfoBanner";
import { Spinner } from "@/components/ui/Spinner";
import { SubnavTabs } from "@/components/ui/SubnavTabs";
import { useAuth } from "@/context/AuthContext";
import { useJob } from "@/context/JobContext";
import {
  isAnalysisModule,
  orderDiagModules,
} from "@/lib/diagnosticsModules";
import {
  DEFAULT_FAULT_CATEGORIES,
  type FaultCategoriesResponse,
} from "@/lib/faultCategories";
import { buildFaultRows, type FaultRow } from "@/lib/faultsTable";
import { diagnoseKpiGaps, fixHref } from "@/lib/missingReasons";
import { buildOwnerActions } from "@/lib/ownerActions";
import { stringHealthFromResults, worstInvertersFromResults } from "@/lib/summaryInsights";
import {
  RESULTS_SECTION_EVENT,
  RESULTS_SECTIONS,
  RESULTS_TOOL_LINKS,
  resolveResultsSectionId,
  type ResultsSectionId,
} from "@/lib/resultsNav";
import type { ResultObject, ResultsResponse, AiIntegrityCheck } from "@/types";

function fmt(value: number | null, digits = 1): string | null {
  if (value === null || value === undefined) return null;
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

/** Modules worth listing in Devices folder (faults + analysis, preferred order). */
function relevantDiagModules(results: ResultObject[]): ResultObject[] {
  const { faults, analysis } = orderDiagModules(results.filter((r) => r.algorithm_id !== "kpis"));
  return [...faults, ...analysis];
}

function firstReadyModuleId(modules: ResultObject[]): string | null {
  return modules.find((r) => r.status === "ok")?.algorithm_id ?? modules[0]?.algorithm_id ?? null;
}

/** Compact mobile module picker when Devices is active. */
function MobileDevicesPicker({
  faultModules,
  analysisModules,
  activeModuleId,
  onSelectModule,
}: {
  faultModules: ResultObject[];
  analysisModules: ResultObject[];
  activeModuleId: string | null;
  onSelectModule: (algorithmId: string) => void;
}) {
  const modules = [...faultModules, ...analysisModules];
  if (modules.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5 border-b border-[color:var(--pic-border-subtle)] bg-[color:var(--pic-surface-raised)] px-3 py-2 lg:hidden">
      {modules.map((m) => {
        const active = m.algorithm_id === activeModuleId;
        return (
          <button
            key={m.algorithm_id}
            type="button"
            data-results-section={m.algorithm_id}
            data-tour={`nav-diag-${m.algorithm_id}`}
            onClick={() => onSelectModule(m.algorithm_id)}
            className={`max-w-[11rem] truncate rounded-pic px-2.5 py-1.5 text-[11px] font-semibold transition ${
              active
                ? "bg-brand-50 text-stone-900 ring-1 ring-brand-200/80 dark:bg-brand-950/40 dark:text-amber-100 dark:ring-brand-800/50"
                : "bg-[color:var(--pic-surface-muted)] text-[color:var(--pic-text-secondary)] hover:bg-brand-50/50 dark:hover:bg-stone-800"
            }`}
            title={m.title}
          >
            {m.title}
          </button>
        );
      })}
    </div>
  );
}

export function DashboardPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const { clearJob } = useJob();
  const { isSuperadmin } = useAuth();

  const [data, setData] = useState<ResultsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [activeSection, setActiveSection] = useState<ResultsSectionId>("overview");
  const [activeModuleId, setActiveModuleId] = useState<string | null>(null);
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const [investigateRow, setInvestigateRow] = useState<FaultRow | null>(null);
  const [devicesOpen, setDevicesOpen] = useState(false);
  const [faultCategories, setFaultCategories] = useState<FaultCategoriesResponse>(DEFAULT_FAULT_CATEGORIES);
  const [integrity, setIntegrity] = useState<AiIntegrityCheck | null>(null);
  const mainPaneRef = useRef<HTMLDivElement>(null);
  const modulesRef = useRef<ResultObject[]>([]);

  useEffect(() => {
    let cancelled = false;
    getFaultCategories()
      .then((res) => {
        if (!cancelled) setFaultCategories(res);
      })
      .catch(() => {
        /* keep defaults */
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
          setIntegrity(res.ai_integrity ?? null);
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
        setDevicesOpen(true);
        setActiveModuleId((cur) => cur ?? firstReadyModuleId(modulesRef.current));
      }
      scrollMainTop();
    },
    [scrollMainTop],
  );

  const selectModule = useCallback(
    (algorithmId: string) => {
      setActiveSection("diagnostics");
      setDevicesOpen(true);
      setActiveModuleId(algorithmId);
      scrollMainTop();
    },
    [scrollMainTop],
  );

  // Tour / deep-link: section id or algorithm_id (opens Devices module)
  useEffect(() => {
    const onSection = (ev: Event) => {
      const id = (ev as CustomEvent).detail;
      if (typeof id !== "string" || !id) return;

      const section = resolveResultsSectionId(id);
      if (section) {
        setActiveSection(section);
        if (section === "diagnostics") {
          setDevicesOpen(true);
          setActiveModuleId((cur) => cur ?? firstReadyModuleId(modulesRef.current));
        }
        scrollMainTop();
        return;
      }

      const modules = modulesRef.current;
      if (modules.some((m) => m.algorithm_id === id)) {
        setActiveSection("diagnostics");
        setDevicesOpen(true);
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
    const k = data.kpis;
    return [
      {
        label: "Total Generation",
        value: fmt(k.total_ac_energy_kwh, 0),
        unit: "kWh",
      },
      {
        label: "PR",
        value: fmt(k.performance_ratio_pct),
        unit: "%",
        tone: "good",
        missingHint: gaps?.performance_ratio_pct?.message,
        missingHref: gaps?.performance_ratio_pct ? fixHref(jobId, gaps.performance_ratio_pct.fix) : null,
      },
      {
        label: "CUF",
        value: fmt(k.cuf_pct ?? null),
        unit: "%",
      },
      {
        label: "PLF",
        value: fmt(k.plf_pct ?? null),
        unit: "%",
      },
      {
        label: "Yield",
        value: fmt(k.specific_yield_kwh_per_kwp),
        unit: "kWh/kWp",
        missingHint: gaps?.specific_yield_kwh_per_kwp?.message,
        missingHref: gaps?.specific_yield_kwh_per_kwp
          ? fixHref(jobId, gaps.specific_yield_kwh_per_kwp.fix)
          : null,
      },
      {
        label: "GHI",
        value: fmt(k.ghi_kwh_m2 ?? null, 2),
        unit: "kWh/m²",
      },
      {
        label: "GTI",
        value: fmt(k.gti_kwh_m2 ?? null, 2),
        unit: "kWh/m²",
      },
      {
        label: "Total Energy Loss",
        value: fmt(k.estimated_energy_loss_kwh, 0),
        unit: "kWh",
        tone: k.estimated_energy_loss_kwh ? "bad" : "neutral",
      },
      {
        label: "Total Revenue Loss",
        value: k.revenue_loss_available ? fmt(k.revenue_loss_inr, 0) : null,
        unit: "₹",
        tone: "bad",
        missingHint: gaps?.revenue_loss_inr?.message,
        missingHref: gaps?.revenue_loss_inr ? fixHref(jobId, gaps.revenue_loss_inr.fix) : null,
      },
      {
        label: "Total no of faults",
        value: k.fault_count,
        tone: k.fault_count > 0 ? "bad" : "neutral",
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

  const handleOwnerSection = useCallback(
    (id: "faults" | "bridge" | "losses" | "diagnostics") => {
      const resolved = resolveResultsSectionId(id) ?? (id as ResultsSectionId);
      selectSection(resolved);
    },
    [selectSection],
  );

  if (!jobId) return null;

  const handleNewAnalysis = () => {
    clearJob();
    navigate("/upload");
  };

  const mobileTabs = [
    ...RESULTS_SECTIONS.map(({ id, label }) => ({ id, label })),
    ...RESULTS_TOOL_LINKS.map(({ to, label }) => ({ id: `tool:${to}`, label })),
  ];

  if (loading) {
    return (
      <div className="tool-enter flex min-h-[40vh] flex-1 items-center justify-center gap-3 text-sm text-[color:var(--pic-text-muted)]">
        <Spinner className="h-5 w-5" /> Loading results…
      </div>
    );
  }

  if (error) {
    return (
      <div className="tool-enter mx-auto flex max-w-lg flex-col gap-3 py-10">
        <ErrorState
          title="Results no longer available"
          message={error}
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
      documentScroll
      hideJobNav
      className="results-shell"
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
              onSelect={(id) => {
                if (id.startsWith("tool:")) {
                  navigate(`/jobs/${jobId}/${id.slice(5)}`);
                  return;
                }
                selectSection(id as ResultsSectionId);
              }}
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
          faultModules={faultModules}
          analysisModules={analysisModules}
          activeModuleId={activeModuleId}
          onSelectModule={selectModule}
          devicesOpen={devicesOpen}
          onToggleDevices={() => setDevicesOpen((o) => !o)}
        />
      }
      mainRef={mainPaneRef}
      footer={
        <button type="button" className="btn-ghost !px-2 !py-0.5 text-[11px]" onClick={handleNewAnalysis}>
          Start new analysis
        </button>
      }
    >
      {activeSection === "overview" && (
        <div id="results-actions" data-results-pane="overview" data-results-pane-alias="summary" className="job-pane-tight flex flex-col gap-5 pb-6">
          {jobId ? (
            <RunIntegrityPanel
              jobId={jobId}
              check={integrity}
              canRerun={isSuperadmin}
              onUpdated={setIntegrity}
              quiet
            />
          ) : null}

          <div className="border-t border-[color:var(--pic-border-subtle)] pt-4" data-tour="summary-loss-preview">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div>
                <h3 className="font-display text-sm font-semibold tracking-tight text-[color:var(--pic-text)]">
                  Losses
                </h3>
                <p className="mt-0.5 text-[11px] text-[color:var(--pic-text-muted)]">
                  Expected → diagnosed losses → actual
                </p>
              </div>
              <button
                type="button"
                onClick={() => selectSection("losses")}
                className="text-xs font-medium text-[color:var(--pic-text-secondary)] underline-offset-2 hover:underline"
              >
                Open Losses
              </button>
            </div>
          </div>

          {ownerActions ? (
            <OwnerActionCenter
              model={ownerActions}
              onInvestigate={investigateFinding}
              onModule={jumpToModule}
              onSection={handleOwnerSection}
              compact
            />
          ) : (
            <p className="border-t border-[color:var(--pic-border-subtle)] pt-4 text-sm text-[color:var(--pic-text-muted)]">
              No owner actions for this run.
            </p>
          )}
        </div>
      )}

      {activeSection === "performance" && (
        <div data-results-pane="performance" className="job-pane-tight flex flex-col gap-4 pb-6">
          <div className="border-b border-[color:var(--pic-border-subtle)] pb-3">
            <h3 className="font-display text-sm font-semibold tracking-tight text-[color:var(--pic-text)]">
              Inverter &amp; string performance
            </h3>
            <p className="mt-0.5 text-[11px] text-[color:var(--pic-text-muted)]">
              Unit-level PR and string health for this run.
            </p>
          </div>
          <InverterComparisonPanel rows={data.kpis.inverter_pr ?? []} />
          <SummaryInsightPanels
            worstInverters={worstInverters}
            stringHealth={stringHealth.rows}
            stringHealthyNote={stringHealth.healthyNote}
            onModule={jumpToModule}
          />
        </div>
      )}

      {activeSection === "losses" && (
        <div
          id="results-bridge"
          data-tour="loss-bridge"
          data-results-pane="losses"
          data-results-pane-alias="bridge"
          className="job-pane-tight pb-6"
        >
          <LossWaterfallBridge kpis={data.kpis} results={data.results} jobId={jobId} />
        </div>
      )}

      {activeSection === "faults" && (
        <div id="results-faults" data-tour="faults-table" data-results-pane="faults" className="job-pane-tight pb-6">
          <FaultsTable results={data.results} categories={faultCategories} />
        </div>
      )}

      {activeSection === "diagnostics" && (
        <div
          className="flex flex-col pb-6"
          data-tour="diagnostics"
          data-results-pane="diagnostics"
        >
          <MobileDevicesPicker
            faultModules={faultModules}
            analysisModules={analysisModules}
            activeModuleId={activeModuleId}
            onSelectModule={selectModule}
          />
          <div className="job-pane-tight min-w-0 flex-1">
            {!activeModule ? (
              <div
                className="flex min-h-[12rem] flex-col items-center justify-center rounded-pic-lg border border-dashed border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] px-4 py-8 text-center"
                data-tour="diagnostics-empty"
              >
                <p className="font-display text-sm font-semibold text-[color:var(--pic-text)]">
                  Select a device module
                </p>
                <p className="mt-1 max-w-sm text-xs leading-relaxed text-[color:var(--pic-text-muted)]">
                  {diagModules.length === 0
                    ? "No diagnostic modules available for this run."
                    : "Choose a fault check or box plot analysis from Devices in the sidebar."}
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

      {activeSection === "reports" && (
        <div data-results-pane="reports" className="job-pane-tight flex flex-col gap-3 pb-6">
          <div className="border-b border-[color:var(--pic-border-subtle)] pb-3">
            <h3 className="font-display text-base font-semibold tracking-tight text-[color:var(--pic-text)]">
              Reports
            </h3>
            <p className="mt-1 max-w-lg text-xs leading-relaxed text-[color:var(--pic-text-muted)]">
              Excel for tables and segment detail; PDF for KPIs, faults, and loss summary.
            </p>
          </div>
          <div className="flex flex-wrap gap-2" data-tour="reports-downloads">
            <a className="btn-secondary text-sm" href={reportUrl(jobId, "xlsx")}>
              Download Excel
            </a>
            <a className="btn-primary text-sm" href={reportUrl(jobId, "pdf")}>
              Download PDF
            </a>
          </div>
        </div>
      )}

      {investigateRow && (
        <EvidenceInvestigateModal row={investigateRow} onClose={() => setInvestigateRow(null)} />
      )}
    </JobWorkspace>
  );
}
