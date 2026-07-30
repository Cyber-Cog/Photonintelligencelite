type KpiTone = "neutral" | "good" | "bad";
type KpiIcon = "pr" | "yield" | "availability" | "loss" | "revenue" | "faults";

const TONE_VALUE: Record<KpiTone, string> = {
  neutral: "text-[color:var(--pic-text)]",
  good: "text-emerald-700 dark:text-emerald-300",
  bad: "text-rose-600 dark:text-rose-400",
};

export type KpiStripItem = {
  label: string;
  value: number | string | null;
  unit?: string;
  tone?: KpiTone;
  /** Kept for call-site compatibility; strip is icon-free by design. */
  icon?: KpiIcon;
  missingHint?: string | null;
  missingHref?: string | null;
};

function KpiCell({ item, index }: { item: KpiStripItem; index: number }) {
  const tone = item.tone ?? "neutral";
  const unavailable = item.value === null || item.value === undefined;
  const display = unavailable ? "—" : item.value;
  const valueClass = unavailable ? "text-[color:var(--pic-text-muted)]" : TONE_VALUE[tone];
  const delay = Math.min(index, 8) * 30;

  return (
    <div
      className="kpi-metric flex min-w-[7.5rem] flex-1 items-baseline gap-2 px-3 py-1.5 sm:min-w-0 sm:px-3.5"
      style={{ animationDelay: `${delay}ms` }}
    >
      <span className="shrink-0 text-[10px] font-semibold uppercase tracking-[0.1em] text-[color:var(--pic-text-muted)]">
        {item.label}
      </span>
      <span className={`min-w-0 truncate font-display text-[15px] font-semibold leading-none tracking-tight tabular-nums ${valueClass}`}>
        {display}
        {!unavailable && item.unit ? (
          <span className="ml-0.5 text-[10px] font-semibold tracking-normal text-[color:var(--pic-text-muted)]">
            {item.unit}
          </span>
        ) : null}
      </span>
      {unavailable && item.missingHint && item.missingHref ? (
        <a
          href={item.missingHref}
          className="ml-auto hidden max-w-[9rem] truncate text-[10px] text-amber-800 underline-offset-2 hover:underline dark:text-amber-200 xl:inline"
          title={item.missingHint}
        >
          {item.missingHint}
        </a>
      ) : unavailable && item.missingHint ? (
        <span
          className="ml-auto hidden max-w-[9rem] truncate text-[10px] text-amber-800/90 dark:text-amber-200/90 xl:inline"
          title={item.missingHint}
        >
          {item.missingHint}
        </span>
      ) : null}
    </div>
  );
}

/**
 * Plant KPI bar — slim single-line metrics with quiet dividers (not a card grid).
 */
export function KpiStrip({ items, flush = false }: { items: KpiStripItem[]; flush?: boolean }) {
  const row = (
    <div
      className="flex divide-x divide-[color:var(--pic-border-subtle)] overflow-x-auto overscroll-x-contain"
      data-tour="summary-kpis"
      role="group"
      aria-label="Plant KPIs"
    >
      {items.map((item, i) => (
        <KpiCell key={item.label} item={item} index={i} />
      ))}
    </div>
  );

  if (flush) {
    return (
      <div className="border-t border-[color:var(--pic-border-subtle)] bg-[color:var(--pic-surface-inset)]">
        {row}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-pic-lg border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] shadow-pic">
      {row}
    </div>
  );
}
