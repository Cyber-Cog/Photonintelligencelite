import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  type OwnerActionCard,
  type OwnerActionCenterModel,
  type OwnerCta,
} from "@/lib/ownerActions";

type SeverityFilter = "all" | "high" | "medium" | "low";

const TONE_DOT: Record<OwnerActionCard["tone"], string> = {
  danger: "bg-rose-500",
  warning: "bg-amber-500",
  info: "bg-brand-500",
};

const TONE_BADGE: Record<OwnerActionCard["tone"], string> = {
  danger: "bg-rose-50 text-rose-800 ring-rose-200/80 dark:bg-rose-950/40 dark:text-rose-200 dark:ring-rose-900/50",
  warning:
    "bg-amber-50 text-amber-900 ring-amber-200/80 dark:bg-amber-950/35 dark:text-amber-100 dark:ring-amber-900/45",
  info: "bg-stone-100 text-stone-700 ring-stone-200/90 dark:bg-stone-800 dark:text-stone-200 dark:ring-stone-700",
};

function cardSeverity(card: OwnerActionCard): SeverityFilter {
  const s = (card.severity ?? "").toLowerCase();
  if (s === "critical" || s === "high" || card.tone === "danger") return "high";
  if (s === "medium" || card.tone === "warning") return "medium";
  return "low";
}

function severityLabel(card: OwnerActionCard): string {
  if (card.severity) return card.severity;
  if (card.tone === "danger") return "high";
  if (card.tone === "warning") return "medium";
  return "info";
}

function CtaButton({
  cta,
  onInvestigate,
  onModule,
  onSection,
  primary,
}: {
  cta: OwnerCta;
  onInvestigate: (algorithmId: string) => void;
  onModule: (algorithmId: string) => void;
  onSection: (sectionId: "faults" | "bridge" | "diagnostics") => void;
  primary?: boolean;
}) {
  const cls = primary ? "btn-primary text-xs" : "btn-secondary !px-2.5 !py-1 text-[11px]";
  if (cta.kind === "setup") {
    return (
      <Link to={cta.href} className={cls}>
        {cta.label}
      </Link>
    );
  }
  if (cta.kind === "investigate") {
    return (
      <button type="button" className={cls} onClick={() => onInvestigate(cta.algorithmId)}>
        {cta.label}
      </button>
    );
  }
  if (cta.kind === "module") {
    return (
      <button type="button" className={cls} onClick={() => onModule(cta.algorithmId)}>
        {cta.label}
      </button>
    );
  }
  return (
    <button type="button" className={cls} onClick={() => onSection(cta.sectionId)}>
      {cta.label}
    </button>
  );
}

function FilterChip({
  active,
  label,
  count,
  onClick,
}: {
  active: boolean;
  label: string;
  count: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px] font-semibold transition ${
        active
          ? "bg-brand-600 text-white shadow-sm dark:bg-brand-500 dark:text-stone-950"
          : "bg-stone-100 text-stone-600 hover:bg-stone-200/80 dark:bg-stone-800 dark:text-stone-300 dark:hover:bg-stone-700"
      }`}
    >
      {label}
      <span
        className={`tabular-nums rounded px-1 py-px text-[10px] font-bold ${
          active ? "bg-white/20 text-white dark:bg-stone-950/20 dark:text-stone-950" : "bg-white/80 text-stone-500 dark:bg-stone-900 dark:text-stone-400"
        }`}
      >
        {count}
      </span>
    </button>
  );
}

function ActionListItem({
  card,
  selected,
  onSelect,
}: {
  card: OwnerActionCard;
  selected: boolean;
  onSelect: () => void;
}) {
  const loss =
    card.lossKwh != null && card.lossKwh > 0
      ? `${card.lossKwh.toLocaleString(undefined, { maximumFractionDigits: 1 })} kWh`
      : null;

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected ? "true" : undefined}
      className={`flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2.5 text-left transition ${
        selected
          ? "bg-brand-50 ring-1 ring-brand-200/90 dark:bg-brand-950/45 dark:ring-brand-800/50"
          : "hover:bg-stone-50 dark:hover:bg-stone-800/50"
      }`}
      data-tour={card.cta.kind === "investigate" ? "owner-investigate" : undefined}
    >
      <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${TONE_DOT[card.tone]}`} aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-medium leading-snug text-stone-900 dark:text-stone-50 break-normal">
          {card.problem}
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px]">
          <span className={`rounded-md px-1.5 py-0.5 capitalize ring-1 ring-inset ${TONE_BADGE[card.tone]}`}>
            {severityLabel(card)}
          </span>
          {loss ? (
            <span className="font-semibold tabular-nums text-rose-700 dark:text-rose-300">{loss}</span>
          ) : (
            <span className="text-stone-500 dark:text-stone-400">{card.impact}</span>
          )}
        </div>
      </div>
    </button>
  );
}

function ActionDetail({
  card,
  onInvestigate,
  onModule,
  onSection,
}: {
  card: OwnerActionCard;
  onInvestigate: (algorithmId: string) => void;
  onModule: (algorithmId: string) => void;
  onSection: (sectionId: "faults" | "bridge" | "diagnostics") => void;
}) {
  return (
    <div className="flex h-full flex-col gap-4 p-4 sm:p-5" data-tour="owner-action-detail">
      <div>
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-stone-400">Selected issue</p>
        <h4 className="mt-1.5 font-display text-base font-semibold leading-snug tracking-tight text-stone-900 dark:text-stone-50 break-normal">
          {card.problem}
        </h4>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-stone-100 bg-stone-50/70 px-3 py-2.5 dark:border-stone-800 dark:bg-stone-950/40">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-stone-400">Impact</p>
          <p className="mt-1 text-sm font-semibold tabular-nums leading-snug text-rose-700 dark:text-rose-300">
            {card.impact}
          </p>
        </div>
        <div className="rounded-lg border border-stone-100 bg-stone-50/70 px-3 py-2.5 dark:border-stone-800 dark:bg-stone-950/40">
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-stone-400">Severity</p>
          <p className="mt-1">
            <span className={`inline-flex rounded-md px-1.5 py-0.5 text-xs font-semibold capitalize ring-1 ring-inset ${TONE_BADGE[card.tone]}`}>
              {severityLabel(card)}
            </span>
          </p>
        </div>
      </div>

      <div>
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-stone-400">Next step</p>
        <p className="mt-1 text-sm leading-snug text-stone-600 dark:text-stone-300 break-normal">
          {card.nextStep}
        </p>
      </div>

      <div className="mt-auto flex flex-wrap items-center gap-2 border-t border-stone-100 pt-4 dark:border-stone-800">
        <CtaButton
          cta={card.cta}
          onInvestigate={onInvestigate}
          onModule={onModule}
          onSection={onSection}
          primary
        />
        {card.algorithmId && card.cta.kind !== "module" && (
          <button
            type="button"
            className="btn-ghost !px-2.5 !py-1 text-[11px]"
            onClick={() => onModule(card.algorithmId!)}
          >
            Go to module
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Owner-first Action Centre — severity filters, readable list, detail panel when selected.
 */
export function OwnerActionCenter({
  model,
  onInvestigate,
  onModule,
  onSection,
}: {
  model: OwnerActionCenterModel;
  onInvestigate: (algorithmId: string) => void;
  onModule: (algorithmId: string) => void;
  onSection: (sectionId: "faults" | "bridge" | "diagnostics") => void;
}) {
  const [filter, setFilter] = useState<SeverityFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(model.cards[0]?.id ?? null);

  const counts = useMemo(() => {
    let high = 0;
    let medium = 0;
    let low = 0;
    for (const c of model.cards) {
      const s = cardSeverity(c);
      if (s === "high") high += 1;
      else if (s === "medium") medium += 1;
      else low += 1;
    }
    return { all: model.cards.length, high, medium, low };
  }, [model.cards]);

  const filtered = useMemo(() => {
    if (filter === "all") return model.cards;
    return model.cards.filter((c) => cardSeverity(c) === filter);
  }, [model.cards, filter]);

  useEffect(() => {
    if (filtered.length === 0) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !filtered.some((c) => c.id === selectedId)) {
      setSelectedId(filtered[0].id);
    }
  }, [filtered, selectedId]);

  const selected = filtered.find((c) => c.id === selectedId) ?? filtered[0] ?? null;

  const summaryChip =
    model.issueCount > 0
      ? model.totalLossKwh != null && model.totalLossKwh > 0
        ? `${model.issueCount} issue${model.issueCount === 1 ? "" : "s"} · ${model.totalLossKwh.toLocaleString(undefined, { maximumFractionDigits: 1 })} kWh`
        : `${model.issueCount} issue${model.issueCount === 1 ? "" : "s"}`
      : null;

  return (
    <section
      className="flex min-h-[min(48vh,28rem)] flex-1 flex-col overflow-hidden rounded-pic-lg border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] shadow-pic"
      role="region"
      aria-label="Owner action center"
      data-tour="owner-actions"
    >
      <div className="panel-rule shrink-0" aria-hidden />

      <div className="flex shrink-0 flex-wrap items-start justify-between gap-3 border-b border-[color:var(--pic-border-subtle)] px-4 py-3.5 sm:px-5">
        <div className="min-w-0">
          <p className="tool-eyebrow">Action centre</p>
          <h3
            className={`mt-1 font-display text-lg font-semibold tracking-tight sm:text-xl ${
              model.healthy ? "text-accent-800 dark:text-accent-300" : "text-[color:var(--pic-text)]"
            }`}
          >
            {model.headline}
          </h3>
          <p className="mt-1 max-w-2xl text-xs text-[color:var(--pic-text-muted)]">{model.subline}</p>
        </div>
        {summaryChip ? (
          <span
            className="status-chip status-chip-warn shrink-0"
            data-tour="owner-actions-summary"
          >
            {summaryChip}
          </span>
        ) : null}
      </div>

      {model.cards.length === 0 ? (
        <p className="flex flex-1 items-center justify-center px-4 py-10 text-center text-sm text-[color:var(--pic-text-muted)] sm:px-5">
          No owner actions for this run. Use Loss bridge and Diagnostics for detail.
        </p>
      ) : (
        <>
          <div className="flex shrink-0 flex-wrap gap-2 border-b border-[color:var(--pic-border-subtle)] px-4 py-2.5 sm:px-5">
            <FilterChip active={filter === "all"} label="All" count={counts.all} onClick={() => setFilter("all")} />
            <FilterChip active={filter === "high"} label="High" count={counts.high} onClick={() => setFilter("high")} />
            <FilterChip
              active={filter === "medium"}
              label="Medium"
              count={counts.medium}
              onClick={() => setFilter("medium")}
            />
            <FilterChip active={filter === "low"} label="Low" count={counts.low} onClick={() => setFilter("low")} />
          </div>

          <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
            <div className="min-h-[16rem] space-y-0.5 overflow-y-auto overscroll-contain border-b border-[color:var(--pic-border-subtle)] p-2 lg:min-h-0 lg:border-b-0 lg:border-r">
              {filtered.length === 0 ? (
                <p className="px-2.5 py-6 text-center text-xs text-[color:var(--pic-text-muted)]">No issues in this severity band.</p>
              ) : (
                filtered.map((card) => (
                  <ActionListItem
                    key={card.id}
                    card={card}
                    selected={selected?.id === card.id}
                    onSelect={() => setSelectedId(card.id)}
                  />
                ))
              )}
            </div>

            <div className="min-h-[16rem] overflow-y-auto overscroll-contain bg-[color:var(--pic-surface-inset)] lg:min-h-0">
              {selected ? (
                <ActionDetail
                  card={selected}
                  onInvestigate={onInvestigate}
                  onModule={onModule}
                  onSection={onSection}
                />
              ) : (
                <p className="px-5 py-10 text-center text-sm text-[color:var(--pic-text-muted)]">Select an issue to see detail.</p>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
