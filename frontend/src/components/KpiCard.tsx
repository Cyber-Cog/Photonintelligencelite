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

/** Soft craft washes — amber/emerald PIC, not left-stripe SaaS. */
const TONE_WASH: Record<KpiTone, string> = {
  neutral:
    "from-brand-400/25 via-transparent to-accent-400/15 dark:from-brand-500/20 dark:via-transparent dark:to-accent-500/12",
  good: "from-accent-400/30 via-transparent to-brand-300/10 dark:from-accent-500/22 dark:via-transparent dark:to-brand-500/10",
  bad: "from-rose-400/25 via-transparent to-brand-400/10 dark:from-rose-500/18 dark:via-transparent dark:to-brand-500/8",
};

const TONE_RULE: Record<KpiTone, string> = {
  neutral: "bg-gradient-to-r from-brand-500 to-accent-500 dark:from-brand-400 dark:to-accent-400",
  good: "bg-gradient-to-r from-accent-500 to-accent-400 dark:from-accent-400 dark:to-accent-300",
  bad: "bg-gradient-to-r from-rose-500 to-brand-500 dark:from-rose-400 dark:to-brand-400",
};

const TONE_VALUE: Record<KpiTone, string> = {
  neutral: "text-stone-900 dark:text-stone-50",
  good: "text-emerald-700 dark:text-emerald-300",
  bad: "text-rose-600 dark:text-rose-400",
};

const TONE_MARK: Record<KpiTone, string> = {
  neutral: "text-brand-500/25 dark:text-brand-400/20",
  good: "text-accent-600/30 dark:text-accent-400/22",
  bad: "text-rose-500/25 dark:text-rose-400/20",
};

export function KpiCard({
  label,
  value,
  unit,
  tone = "neutral",
  icon = "pr",
  index = 0,
  missingHint,
  missingHref,
}: {
  label: string;
  value: number | string | null;
  unit?: string;
  tone?: KpiTone;
  icon?: KpiIcon;
  /** Stagger index for enter motion (0-based). */
  index?: number;
  missingHint?: string | null;
  missingHref?: string | null;
}) {
  const unavailable = value === null || value === undefined;
  const display = unavailable ? "—" : value;
  const valueClass = unavailable ? "text-stone-400 dark:text-stone-500" : TONE_VALUE[tone];
  const delay = Math.min(index, 8) * 55;
  const wash = unavailable
    ? "from-stone-300/20 via-transparent to-stone-200/10 dark:from-stone-600/15 dark:via-transparent dark:to-stone-700/10"
    : TONE_WASH[tone];
  const rule = unavailable
    ? "bg-stone-300 dark:bg-stone-600"
    : TONE_RULE[tone];
  const mark = unavailable ? "text-stone-300/40 dark:text-stone-600/35" : TONE_MARK[tone];

  return (
    <div
      className="kpi-card group relative overflow-hidden rounded-2xl border border-stone-200/70 bg-white/80 shadow-sm shadow-stone-900/[0.03] backdrop-blur-[2px] transition duration-300 hover:-translate-y-0.5 hover:border-brand-300/60 hover:shadow-md hover:shadow-brand-900/[0.06] dark:border-stone-700/80 dark:bg-stone-900/85 dark:shadow-none dark:hover:border-brand-600/45 dark:hover:shadow-none"
      style={{ animationDelay: `${delay}ms` }}
    >
      {/* Ambient craft wash — corner bloom, not left stripe */}
      <div
        className={`pointer-events-none absolute -right-6 -top-10 h-28 w-28 rounded-full bg-gradient-to-br ${wash} blur-2xl transition duration-500 group-hover:scale-110`}
        aria-hidden
      />
      <div
        className={`pointer-events-none absolute -bottom-8 -left-4 h-20 w-24 rounded-full bg-gradient-to-tr ${wash} opacity-70 blur-2xl`}
        aria-hidden
      />

      {/* Faint technical corner ticks */}
      <span
        className="pointer-events-none absolute left-2.5 top-2.5 h-2 w-2 border-l border-t border-stone-300/80 dark:border-stone-600/80"
        aria-hidden
      />
      <span
        className="pointer-events-none absolute bottom-2.5 right-2.5 h-2 w-2 border-b border-r border-stone-300/80 dark:border-stone-600/80"
        aria-hidden
      />

      {/* Oversized watermark glyph — not an icon chip */}
      <svg
        className={`pointer-events-none absolute -bottom-1 -right-1 h-16 w-16 ${mark} transition duration-300 group-hover:opacity-80`}
        fill="none"
        viewBox="0 0 24 24"
        strokeWidth={1.15}
        stroke="currentColor"
        aria-hidden
      >
        {ICON_PATHS[icon]}
      </svg>

      <div className="relative flex flex-col gap-1.5 px-3.5 pb-3 pt-3.5">
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-stone-500 dark:text-stone-400">
          {label}
        </p>

        <p
          className={`font-display text-[1.75rem] font-bold leading-none tracking-tight tabular-nums ${valueClass}`}
        >
          {display}
          {!unavailable && unit ? (
            <span className="ml-1.5 align-baseline text-[11px] font-semibold tracking-normal text-stone-400 dark:text-stone-500">
              {unit}
            </span>
          ) : null}
        </p>

        <div className={`mt-1 h-[2px] w-10 rounded-full ${rule} opacity-80 transition group-hover:w-14`} aria-hidden />

        {unavailable && missingHint && missingHref ? (
          <a
            href={missingHref}
            className="mt-1 block text-[11px] leading-snug text-amber-800 underline-offset-2 hover:underline dark:text-amber-200"
          >
            {missingHint}
          </a>
        ) : unavailable && missingHint ? (
          <p className="mt-1 text-[11px] leading-snug text-amber-800/90 dark:text-amber-200/90">{missingHint}</p>
        ) : null}
      </div>
    </div>
  );
}
