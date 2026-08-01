type KpiTone = "neutral" | "good" | "bad";

export type KpiStripItem = {
  label: string;
  value: number | string | null;
  unit?: string;
  tone?: KpiTone;
  missingHint?: string | null;
  missingHref?: string | null;
};

const TONE_VALUE: Record<KpiTone, string> = {
  neutral: "text-[color:var(--pic-text)]",
  good: "text-emerald-700 dark:text-emerald-300",
  bad: "text-rose-700 dark:text-rose-300",
};

/**
 * Dense plant KPI matrix — elevated metric strip for Results chrome.
 * Fits ~10 metrics in one viewport band (5×2 on desktop; wrap ≤2 rows on mobile).
 */
export function KpiStrip({
  items,
  flush = false,
}: {
  items: KpiStripItem[];
  flush?: boolean;
  /** @deprecated ignored — matrix is always compact */
  compact?: boolean;
}) {
  const board = (
    <dl
      className="kpi-matrix"
      data-tour="summary-kpis"
      aria-label="Plant KPIs"
    >
      {items.map((item, i) => {
        const unavailable = item.value === null || item.value === undefined;
        const tone = item.tone ?? "neutral";
        const valueClass = unavailable
          ? "text-[color:var(--pic-text-muted)]"
          : TONE_VALUE[tone];
        return (
          <div
            key={item.label}
            className="kpi-matrix-cell"
            style={{ animationDelay: `${Math.min(i, 9) * 30}ms` }}
          >
            <dt className="kpi-matrix-label">{item.label}</dt>
            <dd className={`kpi-matrix-value ${valueClass}`}>
              {unavailable ? "—" : item.value}
              {!unavailable && item.unit ? (
                <span className="kpi-matrix-unit">{item.unit}</span>
              ) : null}
            </dd>
            {unavailable && item.missingHint && item.missingHref ? (
              <a href={item.missingHref} className="kpi-matrix-hint" title={item.missingHint}>
                Fix
              </a>
            ) : null}
          </div>
        );
      })}
    </dl>
  );

  if (flush) {
    return <div className="kpi-matrix-flush">{board}</div>;
  }

  return board;
}
