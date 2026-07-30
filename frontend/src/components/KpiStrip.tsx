import type { ReactNode } from "react";

type KpiTone = "neutral" | "good" | "bad";
type KpiIcon = "pr" | "yield" | "availability" | "loss" | "revenue" | "faults";

const ICON_PATHS: Record<KpiIcon, ReactNode> = {
  pr: (
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M2.25 18L9 11.25l4.5 4.5L21.75 6.75M16.5 6.75h5.25V12"
    />
  ),
  yield: (
    <>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636"
      />
      <circle cx="12" cy="12" r="3.25" />
    </>
  ),
  availability: (
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
    />
  ),
  loss: (
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M2.25 6L9 12.75l4.5-4.5L21.75 17.25M16.5 17.25h5.25V12"
    />
  ),
  revenue: (
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M12 6v12m-4.5-9.75h7.5a2.25 2.25 0 010 4.5h-7.5a2.25 2.25 0 000 4.5H16.5"
    />
  ),
  faults: (
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
    />
  ),
};

const TONE_VALUE: Record<KpiTone, string> = {
  neutral: "text-stone-900 dark:text-stone-50",
  good: "text-emerald-700 dark:text-emerald-300",
  bad: "text-rose-600 dark:text-rose-400",
};

const TONE_RULE: Record<KpiTone, string> = {
  neutral: "bg-gradient-to-r from-brand-500 to-accent-500",
  good: "bg-gradient-to-r from-accent-500 to-accent-400",
  bad: "bg-gradient-to-r from-rose-500 to-brand-500",
};

const TONE_MARK: Record<KpiTone, string> = {
  neutral: "text-brand-500/20 dark:text-brand-400/18",
  good: "text-accent-600/22 dark:text-accent-400/18",
  bad: "text-rose-500/20 dark:text-rose-400/16",
};

export type KpiStripItem = {
  label: string;
  value: number | string | null;
  unit?: string;
  tone?: KpiTone;
  icon?: KpiIcon;
  missingHint?: string | null;
  missingHref?: string | null;
};

function KpiCell({ item, index }: { item: KpiStripItem; index: number }) {
  const tone = item.tone ?? "neutral";
  const icon = item.icon ?? "pr";
  const unavailable = item.value === null || item.value === undefined;
  const display = unavailable ? "—" : item.value;
  const valueClass = unavailable ? "text-stone-400 dark:text-stone-500" : TONE_VALUE[tone];
  const rule = unavailable ? "bg-stone-300 dark:bg-stone-600" : TONE_RULE[tone];
  const mark = unavailable ? "text-stone-300/35 dark:text-stone-600/30" : TONE_MARK[tone];
  const delay = Math.min(index, 8) * 40;

  return (
    <div
      className="kpi-card group relative min-w-0 overflow-hidden px-3 py-2 sm:px-3.5"
      style={{ animationDelay: `${delay}ms` }}
    >
      <svg
        className={`pointer-events-none absolute -bottom-0.5 -right-0.5 h-9 w-9 ${mark}`}
        fill="none"
        viewBox="0 0 24 24"
        strokeWidth={1.15}
        stroke="currentColor"
        aria-hidden
      >
        {ICON_PATHS[icon]}
      </svg>

      <p className="truncate text-[9px] font-semibold uppercase tracking-[0.12em] text-stone-500 dark:text-stone-400">
        {item.label}
      </p>
      <p
        className={`mt-0.5 font-display text-lg font-bold leading-none tracking-tight tabular-nums sm:text-xl ${valueClass}`}
      >
        {display}
        {!unavailable && item.unit ? (
          <span className="ml-1 align-baseline text-[10px] font-semibold tracking-normal text-stone-400 dark:text-stone-500">
            {item.unit}
          </span>
        ) : null}
      </p>
      <div className={`mt-1 h-[2px] w-7 rounded-full ${rule} opacity-80`} aria-hidden />

      {unavailable && item.missingHint && item.missingHref ? (
        <a
          href={item.missingHref}
          className="mt-0.5 block truncate text-[10px] leading-snug text-amber-800 underline-offset-2 hover:underline dark:text-amber-200"
          title={item.missingHint}
        >
          {item.missingHint}
        </a>
      ) : unavailable && item.missingHint ? (
        <p className="mt-0.5 truncate text-[10px] leading-snug text-amber-800/90 dark:text-amber-200/90" title={item.missingHint}>
          {item.missingHint}
        </p>
      ) : null}
    </div>
  );
}

/**
 * Compact single-row plant KPI bar — sticky chrome for Results.
 * Dividers instead of per-card borders; amber/emerald tones preserved.
 */
export function KpiStrip({ items }: { items: KpiStripItem[] }) {
  return (
    <div
      className="overflow-hidden rounded-xl border border-stone-200/90 bg-white/95 shadow-sm shadow-stone-900/[0.03] dark:border-stone-700 dark:bg-stone-900 dark:shadow-none"
      data-tour="summary-kpis"
      role="group"
      aria-label="Plant KPIs"
    >
      <div className="h-0.5 w-full bg-gradient-to-r from-brand-400/80 via-accent-400/50 to-brand-500/20 dark:from-brand-500/50 dark:via-accent-500/35 dark:to-brand-800/15" aria-hidden />
      <div className="grid grid-cols-2 divide-x divide-y divide-stone-100 sm:grid-cols-3 xl:grid-cols-6 xl:divide-y-0 dark:divide-stone-800">
        {items.map((item, i) => (
          <KpiCell key={item.label} item={item} index={i} />
        ))}
      </div>
    </div>
  );
}
