import { LossWaterfallBridge } from "@/components/LossWaterfallBridge";
import { OwnerActionCenter } from "@/components/OwnerActionCenter";
import type { OwnerActionCenterModel } from "@/lib/ownerActions";
import { buildPlantHealth, type PlantHealthTone } from "@/lib/plantHealth";
import type { ResultsSectionId } from "@/lib/resultsNav";
import type { AiIntegrityCheck, KpiResponse, ResultObject } from "@/types";

function fmt(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

const TONE_RING: Record<PlantHealthTone, string> = {
  good: "stroke-accent-600 dark:stroke-accent-400",
  warn: "stroke-brand-500 dark:stroke-brand-400",
  bad: "stroke-rose-500 dark:stroke-rose-400",
  neutral: "stroke-stone-300 dark:stroke-stone-600",
};

const TONE_SCORE: Record<PlantHealthTone, string> = {
  good: "text-accent-800 dark:text-accent-300",
  warn: "text-brand-800 dark:text-brand-300",
  bad: "text-rose-700 dark:text-rose-300",
  neutral: "text-[color:var(--pic-text-muted)]",
};

const TONE_DOT: Record<PlantHealthTone, string> = {
  good: "bg-accent-500",
  warn: "bg-brand-500",
  bad: "bg-rose-500",
  neutral: "bg-stone-300 dark:bg-stone-600",
};

function HealthRing({
  score,
  unit,
  tone,
}: {
  score: number | null;
  unit: string;
  tone: PlantHealthTone;
}) {
  const pct = score == null ? 0 : Math.min(100, Math.max(0, score));
  const r = 54;
  const c = 2 * Math.PI * r;
  const dash = (pct / 100) * c;
  return (
    <div className="overview-health-ring" aria-hidden={score == null}>
      <svg viewBox="0 0 128 128" className="h-full w-full -rotate-90">
        <circle
          cx="64"
          cy="64"
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth="10"
          className="text-stone-200/90 dark:text-stone-700"
        />
        <circle
          cx="64"
          cy="64"
          r={r}
          fill="none"
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c - dash}`}
          className={`${TONE_RING[tone]} overview-health-ring-progress`}
        />
      </svg>
      <div className="overview-health-ring-label">
        <p className={`font-display text-3xl font-bold tabular-nums tracking-tight ${TONE_SCORE[tone]}`}>
          {score == null ? "—" : fmt(score, score >= 10 ? 0 : 1)}
          {score != null ? (
            <span className="ml-0.5 text-sm font-semibold text-[color:var(--pic-text-muted)]">{unit}</span>
          ) : null}
        </p>
      </div>
    </div>
  );
}

function StatPill({
  label,
  value,
  unit,
  tone,
}: {
  label: string;
  value: string;
  unit?: string;
  tone?: "neutral" | "good" | "bad";
}) {
  const valueCls =
    tone === "good"
      ? "text-accent-800 dark:text-accent-300"
      : tone === "bad"
        ? "text-rose-700 dark:text-rose-300"
        : "text-[color:var(--pic-text)]";
  return (
    <div className="overview-stat-pill">
      <p className="overview-stat-pill-label">{label}</p>
      <p className={`overview-stat-pill-value ${valueCls}`}>
        {value}
        {unit && value !== "—" ? <span className="overview-stat-pill-unit">{unit}</span> : null}
      </p>
    </div>
  );
}

type CategoryRow = {
  id: ResultsSectionId;
  label: string;
  detail: string;
  score: string;
  tone: PlantHealthTone;
};

function CategoryScoreList({
  rows,
  onOpen,
}: {
  rows: CategoryRow[];
  onOpen: (id: ResultsSectionId) => void;
}) {
  return (
    <section className="overview-categories" aria-label="Analysis categories">
      <div className="overview-panel-head">
        <div>
          <h3 className="overview-panel-title">Categories</h3>
          <p className="overview-panel-sub">Jump into Issues, Performance, Losses, Devices</p>
        </div>
      </div>
      <ul className="overview-category-list">
        {rows.map((row) => (
          <li key={row.id}>
            <button
              type="button"
              className="overview-category-row"
              onClick={() => onOpen(row.id)}
              data-tour={`overview-cat-${row.id}`}
            >
              <span className={`overview-category-dot ${TONE_DOT[row.tone]}`} aria-hidden />
              <span className="min-w-0 flex-1 text-left">
                <span className="overview-category-label">{row.label}</span>
                <span className="overview-category-detail">{row.detail}</span>
              </span>
              <span className={`overview-category-score ${TONE_SCORE[row.tone]}`}>{row.score}</span>
              <span className="overview-category-chevron" aria-hidden>
                ›
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ModuleReadiness({
  results,
  onOpenDevices,
}: {
  results: ResultObject[];
  onOpenDevices: () => void;
}) {
  const modules = results.filter((r) => r.algorithm_id !== "kpis");
  const ok = modules.filter((r) => r.status === "ok").length;
  const blocked = modules.filter((r) => r.status === "unavailable").length;
  const errored = modules.filter((r) => r.status === "error").length;
  const total = modules.length;

  return (
    <section className="overview-panel" aria-label="Module readiness">
      <div className="overview-panel-head">
        <div>
          <h3 className="overview-panel-title">Device readiness</h3>
          <p className="overview-panel-sub">Diagnostics status for this run</p>
        </div>
        <button type="button" className="overview-link-btn" onClick={onOpenDevices}>
          Devices
        </button>
      </div>
      {total === 0 ? (
        <p className="overview-empty">No diagnostic modules yet.</p>
      ) : (
        <div className="overview-readiness">
          <div className="overview-readiness-bar" role="img" aria-label={`${ok} of ${total} ready`}>
            <span className="overview-readiness-ok" style={{ width: `${(ok / total) * 100}%` }} />
            <span className="overview-readiness-warn" style={{ width: `${(errored / total) * 100}%` }} />
            <span className="overview-readiness-blocked" style={{ width: `${(blocked / total) * 100}%` }} />
          </div>
          <ul className="overview-readiness-legend">
            <li>
              <span className="dot bg-accent-500" /> Ready <strong>{ok}</strong>
            </li>
            <li>
              <span className="dot bg-rose-400" /> Error <strong>{errored}</strong>
            </li>
            <li>
              <span className="dot bg-stone-300 dark:bg-stone-600" /> Need data <strong>{blocked}</strong>
            </li>
          </ul>
        </div>
      )}
    </section>
  );
}

/**
 * Results Overview — hero scores, category rail targets, prioritized issues, loss bridge.
 */
export function OverviewDashboard({
  jobId,
  kpis,
  results,
  ownerActions,
  integrity,
  onInvestigate,
  onModule,
  onSection,
}: {
  jobId: string;
  kpis: KpiResponse;
  results: ResultObject[];
  ownerActions: OwnerActionCenterModel | null;
  integrity: AiIntegrityCheck | null;
  canRerunIntegrity?: boolean;
  onIntegrityUpdated?: (next: AiIntegrityCheck) => void;
  onInvestigate: (algorithmId: string) => void;
  onModule: (algorithmId: string) => void;
  onSection: (id: ResultsSectionId) => void;
}) {
  const health = buildPlantHealth({
    kpis,
    results,
    issueCount: ownerActions?.issueCount ?? 0,
  });

  const handleOwnerSection = (id: "faults" | "bridge" | "losses" | "diagnostics") => {
    if (id === "bridge") {
      onSection("losses");
      return;
    }
    onSection(id);
  };

  const integrityFlags =
    integrity?.findings?.filter((f) => f.severity !== "pass" && f.severity !== "info").length ?? 0;

  const categories: CategoryRow[] = [
    {
      id: "faults",
      label: "Issues",
      detail:
        health.issueCount > 0
          ? `${health.issueCount} prioritized · ${health.faultCount} faults`
          : health.faultCount > 0
            ? `${health.faultCount} fault${health.faultCount === 1 ? "" : "s"}`
            : "No urgent actions",
      score: String(Math.max(health.issueCount, health.faultCount)),
      tone: health.issueCount > 0 || health.faultCount > 0 ? "bad" : "good",
    },
    {
      id: "performance",
      label: "Performance",
      detail:
        health.score != null
          ? `${health.scoreLabel} ${fmt(health.score)}${health.scoreUnit}`
          : "Inverter & string health",
      score: health.score != null ? `${fmt(health.score, 0)}${health.scoreUnit}` : "—",
      tone: health.tone,
    },
    {
      id: "losses",
      label: "Losses",
      detail:
        health.lossKwh != null && health.lossKwh > 0
          ? `${fmt(health.lossKwh, 0)} kWh estimated loss`
          : "Expected → diagnosed → actual",
      score: health.lossKwh != null && health.lossKwh > 0 ? fmt(health.lossKwh, 0) : "—",
      tone: health.lossKwh && health.lossKwh > 0 ? "warn" : "good",
    },
    {
      id: "diagnostics",
      label: "Devices",
      detail: `${health.okModules} ready · ${health.blockedModules} need data`,
      score: `${health.readinessPct}%`,
      tone:
        health.readinessPct >= 70 ? "good" : health.readinessPct < 40 ? "bad" : "warn",
    },
    {
      id: "integrity",
      label: "Integrity",
      detail:
        integrityFlags > 0
          ? `${integrityFlags} finding${integrityFlags === 1 ? "" : "s"}`
          : integrity?.summary || "Run integrity checklist",
      score: integrityFlags > 0 ? String(integrityFlags) : "OK",
      tone: integrityFlags > 0 ? "warn" : "good",
    },
  ];

  return (
    <div
      id="results-actions"
      data-results-pane="overview"
      data-results-pane-alias="summary"
      className="overview-dashboard job-pane-tight pb-8"
    >
      <div className="overview-top-grid">
        <section className="overview-hero" data-tour="overview-health" aria-label="Plant health">
          <div className="overview-hero-grid">
            <div className="overview-hero-score">
              <HealthRing score={health.score} unit={health.scoreUnit} tone={health.tone} />
              <p className="overview-hero-score-caption">{health.scoreLabel}</p>
            </div>

            <div className="overview-hero-copy min-w-0">
              <p className="overview-eyebrow">Overview</p>
              <h2 className="overview-hero-title">{health.headline}</h2>
              <p className="overview-hero-detail">{health.detail}</p>

              <div className="overview-stat-row">
                <StatPill
                  label="Availability"
                  value={fmt(health.availabilityPct)}
                  unit="%"
                  tone={
                    health.availabilityPct == null
                      ? "neutral"
                      : health.availabilityPct >= 95
                        ? "good"
                        : health.availabilityPct < 85
                          ? "bad"
                          : "neutral"
                  }
                />
                <StatPill label="Yield" value={fmt(health.yieldKwhPerKwp)} unit="kWh/kWp" />
                <StatPill
                  label="Energy loss"
                  value={fmt(health.lossKwh, 0)}
                  unit="kWh"
                  tone={health.lossKwh && health.lossKwh > 0 ? "bad" : "neutral"}
                />
                <StatPill
                  label="Issues"
                  value={String(health.issueCount)}
                  tone={health.issueCount > 0 ? "bad" : "good"}
                />
              </div>
            </div>
          </div>
        </section>

        <CategoryScoreList rows={categories} onOpen={onSection} />
      </div>

      <div className="overview-main-grid">
        <div className="overview-issues-col">
          {ownerActions ? (
            <div className="overview-panel overview-panel-issues" data-tour="overview-issues">
              <OwnerActionCenter
                model={ownerActions}
                onInvestigate={onInvestigate}
                onModule={onModule}
                onSection={handleOwnerSection}
                compact
              />
            </div>
          ) : (
            <div className="overview-panel">
              <p className="overview-empty">No owner actions for this run.</p>
            </div>
          )}
        </div>

        <div className="overview-side-col">
          <section className="overview-panel" data-tour="summary-loss-preview" aria-label="Energy loss bridge">
            <div className="overview-panel-head">
              <div>
                <h3 className="overview-panel-title">Loss bridge</h3>
                <p className="overview-panel-sub">Expected → diagnosed → actual</p>
              </div>
              <button type="button" className="overview-link-btn" onClick={() => onSection("losses")}>
                Open Losses
              </button>
            </div>
            <div className="overview-bridge-body">
              <LossWaterfallBridge kpis={kpis} results={results} jobId={jobId} compact embedded />
            </div>
          </section>

          <ModuleReadiness results={results} onOpenDevices={() => onSection("diagnostics")} />
        </div>
      </div>
    </div>
  );
}
