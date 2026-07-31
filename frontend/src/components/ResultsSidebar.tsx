import type { ReactNode } from "react";
import { NavLink, useParams } from "react-router-dom";
import {
  RESULTS_SECTION_GROUPS,
  RESULTS_SECTIONS,
  RESULTS_TOOL_LINKS,
  type ResultsSectionId,
} from "@/lib/resultsNav";
import { moduleNavBadge, needsDataLine } from "@/lib/diagnosticsModules";
import type { ResultObject } from "@/types";

function IconOverview() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <rect x="3" y="3" width="7" height="7" rx="1.2" />
      <rect x="14" y="3" width="7" height="7" rx="1.2" />
      <rect x="3" y="14" width="7" height="7" rx="1.2" />
      <rect x="14" y="14" width="7" height="7" rx="1.2" />
    </svg>
  );
}

function IconPerformance() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 17l6-6 4 4 7-8" />
      <path strokeLinecap="round" d="M14 7h7v7" />
    </svg>
  );
}

function IconFaults() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
    </svg>
  );
}

function IconLosses() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 3v18h18" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 14l4-4 3 3 6-7" />
    </svg>
  );
}

function IconDevices() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path strokeLinecap="round" d="M8 8h8M8 12h8M8 16h5" />
    </svg>
  );
}

function IconReports() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 3h7l5 5v13a1 1 0 01-1 1H7a1 1 0 01-1-1V4a1 1 0 011-1z" />
      <path strokeLinecap="round" d="M14 3v5h5M9 13h6M9 17h4" />
    </svg>
  );
}

function IconData() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h10" />
    </svg>
  );
}

function IconArchitecture() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v18M3 9h18M7 9v12M17 9v12M3 21h18" />
    </svg>
  );
}

function IconExplorer() {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <path strokeLinecap="round" d="M20 20l-3.5-3.5" />
    </svg>
  );
}

function IconChevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 16 16"
      className={`h-3.5 w-3.5 transition-transform duration-150 ${open ? "rotate-90" : ""}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      aria-hidden
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 3.5l5 4.5-5 4.5" />
    </svg>
  );
}

const SECTION_ICONS: Record<ResultsSectionId, () => ReactNode> = {
  overview: IconOverview,
  performance: IconPerformance,
  faults: IconFaults,
  losses: IconLosses,
  diagnostics: IconDevices,
  reports: IconReports,
};

const TOOL_ICONS: Record<(typeof RESULTS_TOOL_LINKS)[number]["to"], () => ReactNode> = {
  data: IconData,
  architecture: IconArchitecture,
  explore: IconExplorer,
};

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

/**
 * Results ops rail — section panes + tool routes (replaces top JobNav on Results).
 */
export function ResultsSidebar({
  activeSection,
  onSelectSection,
  faultCount,
  issueCount,
  faultModules = [],
  analysisModules = [],
  activeModuleId,
  onSelectModule,
  devicesOpen,
  onToggleDevices,
}: {
  activeSection: ResultsSectionId;
  onSelectSection: (id: ResultsSectionId) => void;
  faultCount: number | null | undefined;
  issueCount: number;
  faultModules?: ResultObject[];
  analysisModules?: ResultObject[];
  activeModuleId?: string | null;
  onSelectModule?: (algorithmId: string) => void;
  devicesOpen?: boolean;
  onToggleDevices?: () => void;
}) {
  const { jobId } = useParams<{ jobId: string }>();
  const modulesOpen = devicesOpen ?? activeSection === "diagnostics";
  const totalModules = faultModules.length + analysisModules.length;

  const badgeFor = (id: ResultsSectionId): number | null => {
    if (id === "faults" && faultCount != null && faultCount > 0) return faultCount;
    if (id === "overview" && issueCount > 0) return issueCount;
    if (id === "diagnostics" && totalModules > 0) return totalModules;
    return null;
  };

  const renderModule = (m: ResultObject) => {
    const active = activeSection === "diagnostics" && activeModuleId === m.algorithm_id;
    const tip =
      m.status === "unavailable"
        ? needsDataLine(m) ?? m.title
        : m.title + (m.summary ? ` — ${m.summary}` : "");
    return (
      <li key={m.algorithm_id}>
        <button
          type="button"
          data-results-section={m.algorithm_id}
          data-tour={`nav-diag-${m.algorithm_id}`}
          aria-current={active ? "page" : undefined}
          title={tip}
          onClick={() => onSelectModule?.(m.algorithm_id)}
          className={`results-nav-sub ${active ? "results-nav-sub-active" : ""}`}
        >
          <span className="min-w-0 flex-1 truncate">{m.title}</span>
          <DiagStatusBadge result={m} />
        </button>
      </li>
    );
  };

  return (
    <div className="results-shell-sidebar" data-tour="results-sidebar">
      <div className="results-shell-brand">
        <div className="results-shell-brand-mark" aria-hidden>
          <span />
        </div>
        <div className="min-w-0">
          <p className="results-shell-brand-title">Results</p>
          <p className="results-shell-brand-sub">Plant analysis</p>
        </div>
      </div>

      <nav className="results-shell-nav" aria-label="Results sections">
        {RESULTS_SECTION_GROUPS.filter((g) => g.id !== "tools").map((group) => {
          const items = RESULTS_SECTIONS.filter((s) => s.group === group.id);
          if (!items.length) return null;
          return (
            <div key={group.id} className="results-nav-group">
              <p className="results-nav-label">{group.label}</p>
              <ul className="space-y-0.5">
                {items.map((item) => {
                  const active = item.id === activeSection;
                  const Icon = SECTION_ICONS[item.id];
                  const badge = badgeFor(item.id);
                  const isDevices = item.id === "diagnostics";

                  if (isDevices) {
                    return (
                      <li key={item.id} className={modulesOpen ? "results-nav-devices results-nav-devices-open" : "results-nav-devices"}>
                        <div className={`results-nav-item-row ${active ? "results-nav-item-active" : ""}`}>
                          <button
                            type="button"
                            data-results-section={item.id}
                            data-tour={item.tour}
                            aria-current={active ? "page" : undefined}
                            aria-expanded={modulesOpen}
                            aria-controls="results-devices-subnav"
                            onClick={() => {
                              onSelectSection(item.id);
                              if (!modulesOpen) onToggleDevices?.();
                            }}
                            className="results-nav-item results-nav-item-flat"
                          >
                            <span className="results-nav-icon">
                              <Icon />
                            </span>
                            <span className="results-nav-item-label">{item.label}</span>
                            {badge != null ? (
                              <span className={`results-nav-badge ${active ? "results-nav-badge-active" : ""}`}>
                                {badge}
                              </span>
                            ) : null}
                          </button>
                          <button
                            type="button"
                            className="results-nav-chevron"
                            aria-label={modulesOpen ? "Collapse devices" : "Expand devices"}
                            onClick={() => onToggleDevices?.()}
                          >
                            <IconChevron open={modulesOpen} />
                          </button>
                        </div>

                        {modulesOpen ? (
                          <ul
                            id="results-devices-subnav"
                            className="results-nav-sublist"
                            role="group"
                            aria-label="Diagnostic modules"
                          >
                            {totalModules === 0 ? (
                              <li className="px-2 py-2 text-[11px] text-[color:var(--pic-text-muted)]">
                                No modules for this run
                              </li>
                            ) : (
                              <>
                                {faultModules.length > 0 ? (
                                  <li className="results-nav-subhead" aria-hidden>
                                    Faults
                                  </li>
                                ) : null}
                                {faultModules.map(renderModule)}
                                {analysisModules.length > 0 ? (
                                  <li className="results-nav-subhead" aria-hidden>
                                    Analysis
                                  </li>
                                ) : null}
                                {analysisModules.map(renderModule)}
                              </>
                            )}
                          </ul>
                        ) : null}
                      </li>
                    );
                  }

                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        data-results-section={item.id}
                        data-tour={item.tour}
                        aria-current={active ? "page" : undefined}
                        onClick={() => onSelectSection(item.id)}
                        className={`results-nav-item ${active ? "results-nav-item-active" : ""}`}
                      >
                        <span className="results-nav-icon">
                          <Icon />
                        </span>
                        <span className="results-nav-item-label">{item.label}</span>
                        {badge != null ? (
                          <span className={`results-nav-badge ${active ? "results-nav-badge-active" : ""}`}>
                            {badge}
                          </span>
                        ) : (
                          <span className="results-nav-trail" aria-hidden />
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}

        {jobId ? (
          <div className="results-nav-group">
            <p className="results-nav-label">Tools</p>
            <ul className="space-y-0.5">
              {RESULTS_TOOL_LINKS.map(({ to, label, tour }) => {
                const Icon = TOOL_ICONS[to];
                return (
                  <li key={to}>
                    <NavLink
                      to={`/jobs/${jobId}/${to}`}
                      data-tour={tour}
                      className={({ isActive }) =>
                        `results-nav-item ${isActive ? "results-nav-item-active" : ""}`
                      }
                    >
                      <span className="results-nav-icon">
                        <Icon />
                      </span>
                      <span className="results-nav-item-label">{label}</span>
                      <span className="results-nav-trail" aria-hidden />
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
      </nav>
    </div>
  );
}
