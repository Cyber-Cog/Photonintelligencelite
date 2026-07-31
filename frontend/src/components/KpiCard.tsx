/**
 * Legacy standalone KPI tile — Results uses KpiStrip matrix.
 * Kept for Landing / docs demos that still import a single card.
 */
export function KpiCard({
  label,
  value,
  unit,
  tone = "neutral",
  missingHint,
  missingHref,
}: {
  label: string;
  value: number | string | null;
  unit?: string;
  tone?: "neutral" | "good" | "bad";
  icon?: string;
  index?: number;
  missingHint?: string | null;
  missingHref?: string | null;
  compact?: boolean;
}) {
  const unavailable = value === null || value === undefined;
  const valueClass = unavailable
    ? "text-[color:var(--pic-text-muted)]"
    : tone === "good"
      ? "text-emerald-700 dark:text-emerald-300"
      : tone === "bad"
        ? "text-rose-700 dark:text-rose-300"
        : "text-[color:var(--pic-text)]";

  return (
    <div className="kpi-matrix-cell border-r border-[color:var(--pic-border-subtle)] px-3 py-2 last:border-r-0">
      <p className="kpi-matrix-label">{label}</p>
      <p className={`kpi-matrix-value ${valueClass}`}>
        {unavailable ? "—" : value}
        {!unavailable && unit ? <span className="kpi-matrix-unit">{unit}</span> : null}
      </p>
      {unavailable && missingHint && missingHref ? (
        <a href={missingHref} className="kpi-matrix-hint">
          {missingHint}
        </a>
      ) : unavailable && missingHint ? (
        <p className="kpi-matrix-hint">{missingHint}</p>
      ) : null}
    </div>
  );
}
