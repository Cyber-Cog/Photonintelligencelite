import { useState } from "react";
import { Link } from "react-router-dom";
import {
  OWNER_ACTION_EXPANDED_LIMIT,
  type OwnerActionCard,
  type OwnerActionCenterModel,
  type OwnerCta,
} from "@/lib/ownerActions";

const TONE_BORDER: Record<OwnerActionCard["tone"], string> = {
  danger: "border-rose-200/90 dark:border-rose-900/50",
  warning: "border-amber-200/90 dark:border-amber-900/45",
  info: "border-stone-200/90 dark:border-stone-700",
};

const TONE_ACCENT: Record<OwnerActionCard["tone"], string> = {
  danger: "bg-rose-500",
  warning: "bg-amber-500",
  info: "bg-brand-500",
};

function CtaButton({
  cta,
  onInvestigate,
  onModule,
  onSection,
  compact,
}: {
  cta: OwnerCta;
  onInvestigate: (algorithmId: string) => void;
  onModule: (algorithmId: string) => void;
  onSection: (sectionId: "faults" | "bridge" | "diagnostics") => void;
  compact?: boolean;
}) {
  const cls = compact ? "btn-secondary !px-2 !py-0.5 text-[11px]" : "btn-primary text-xs";
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

function ActionCard({
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
    <article
      className={`flex flex-col gap-3 rounded-xl border bg-white/90 p-3.5 dark:bg-stone-950/50 ${TONE_BORDER[card.tone]}`}
      data-tour={card.cta.kind === "investigate" ? "owner-investigate" : undefined}
    >
      <div className="flex items-start gap-2.5">
        <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${TONE_ACCENT[card.tone]}`} aria-hidden />
        <div className="min-w-0 flex-1 space-y-2">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-stone-400">Problem</p>
            <p className="mt-0.5 text-sm font-medium leading-snug text-stone-900 dark:text-stone-50">{card.problem}</p>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-stone-400">Impact</p>
              <p className="mt-0.5 text-xs font-semibold tabular-nums text-rose-700 dark:text-rose-300">{card.impact}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-stone-400">What to do next</p>
              <p className="mt-0.5 text-xs leading-relaxed text-stone-600 dark:text-stone-300">{card.nextStep}</p>
            </div>
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 pl-4">
        <CtaButton
          cta={card.cta}
          onInvestigate={onInvestigate}
          onModule={onModule}
          onSection={onSection}
        />
        {card.algorithmId && card.cta.kind !== "module" && (
          <button type="button" className="btn-ghost !px-2 !py-1 text-[11px]" onClick={() => onModule(card.algorithmId!)}>
            Go to module
          </button>
        )}
      </div>
    </article>
  );
}

function CompactActionRow({
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
  const severity =
    card.severity ??
    (card.tone === "danger" ? "high" : card.tone === "warning" ? "medium" : "info");

  return (
    <tr className="border-b border-stone-100 last:border-0 dark:border-stone-800/80">
      <td className="max-w-[14rem] py-1.5 pr-2 align-middle sm:max-w-none">
        <div className="flex items-start gap-1.5">
          <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${TONE_ACCENT[card.tone]}`} aria-hidden />
          <p className="line-clamp-2 text-xs font-medium leading-snug text-stone-800 dark:text-stone-100">
            {card.problem}
          </p>
        </div>
      </td>
      <td className="whitespace-nowrap py-1.5 pr-2 align-middle text-xs font-semibold tabular-nums text-rose-700 dark:text-rose-300">
        {card.lossKwh != null && card.lossKwh > 0
          ? `${card.lossKwh.toLocaleString(undefined, { maximumFractionDigits: 1 })} kWh`
          : card.impact}
      </td>
      <td className="whitespace-nowrap py-1.5 pr-2 align-middle text-[11px] capitalize text-stone-500 dark:text-stone-400">
        {severity}
      </td>
      <td className="py-1.5 text-right align-middle">
        <CtaButton
          cta={card.cta}
          onInvestigate={onInvestigate}
          onModule={onModule}
          onSection={onSection}
          compact
        />
      </td>
    </tr>
  );
}

function summaryChipLabel(model: OwnerActionCenterModel): string {
  const n = model.issueCount > 0 ? model.issueCount : model.cards.length;
  const issues = `${n} issue${n === 1 ? "" : "s"}`;
  if (model.totalLossKwh != null && model.totalLossKwh > 0) {
    return `${issues} · ${model.totalLossKwh.toLocaleString(undefined, { maximumFractionDigits: 1 })} kWh`;
  }
  return issues;
}

/**
 * Owner-first action strip at the top of Results Summary.
 * Top N expanded PROBLEM cards; remainder in a compact accordion (no nested max-height scroll).
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
  const [moreOpen, setMoreOpen] = useState(false);
  const expanded = model.cards.slice(0, OWNER_ACTION_EXPANDED_LIMIT);
  const rest = model.cards.slice(OWNER_ACTION_EXPANDED_LIMIT);
  const showAccordion = rest.length > 0;

  return (
    <div
      className="space-y-0"
      role="region"
      aria-label="Owner action center"
      data-tour="owner-actions"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="tool-eyebrow">Owner action center</p>
          <h3
            className={`mt-1 font-display text-lg font-semibold tracking-tight sm:text-xl ${
              model.healthy
                ? "text-accent-800 dark:text-accent-300"
                : "text-stone-900 dark:text-stone-50"
            }`}
          >
            {model.headline}
          </h3>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-stone-500 dark:text-stone-400">{model.subline}</p>
        </div>
        {!model.healthy && model.cards.length > 0 && (
          <span
            className="shrink-0 rounded-lg border border-amber-200/80 bg-amber-50/80 px-2 py-1 text-[11px] font-semibold text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-100"
            data-tour="owner-actions-summary"
          >
            {summaryChipLabel(model)}
          </span>
        )}
      </div>

      {model.cards.length > 0 && (
        <div className="mt-3 space-y-2.5">
          {expanded.length > 0 && (
            <div className="grid gap-2.5 lg:grid-cols-2">
              {expanded.map((card) => (
                <ActionCard
                  key={card.id}
                  card={card}
                  onInvestigate={onInvestigate}
                  onModule={onModule}
                  onSection={onSection}
                />
              ))}
            </div>
          )}

          {showAccordion && (
            <div className="rounded-xl border border-stone-200/90 dark:border-stone-700">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs font-semibold text-stone-700 hover:bg-stone-50/80 dark:text-stone-200 dark:hover:bg-stone-900/50"
                aria-expanded={moreOpen}
                onClick={() => setMoreOpen((o) => !o)}
                data-tour="owner-actions-more"
              >
                <span>
                  {moreOpen ? "Hide" : "Show"} {rest.length} more issue{rest.length === 1 ? "" : "s"}
                </span>
                <span className="text-stone-400" aria-hidden>
                  {moreOpen ? "▴" : "▾"}
                </span>
              </button>
              {moreOpen && (
                <div className="overflow-x-auto border-t border-stone-100 px-2 pb-2 dark:border-stone-800">
                  <table className="w-full min-w-[20rem] border-collapse text-left">
                    <thead className="text-[10px] font-bold uppercase tracking-[0.1em] text-stone-400">
                      <tr>
                        <th className="py-1.5 pr-2 font-bold">Problem</th>
                        <th className="py-1.5 pr-2 font-bold">Impact</th>
                        <th className="py-1.5 pr-2 font-bold">Severity</th>
                        <th className="py-1.5 text-right font-bold">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rest.map((card) => (
                        <CompactActionRow
                          key={card.id}
                          card={card}
                          onInvestigate={onInvestigate}
                          onModule={onModule}
                          onSection={onSection}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
