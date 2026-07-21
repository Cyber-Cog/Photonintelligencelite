import type { ReactNode } from "react";

type Tone = "neutral" | "info" | "warning" | "danger" | "success";

/**
 * Dark mode: solid stone surfaces + readable text.
 * Do not rely on dark:from-*-950 gradient stops alone — custom brand/accent
 * palettes historically omitted 950, which left light cream gradients under
 * near-white text (unreadable).
 */
const TONE: Record<Tone, string> = {
  neutral:
    "border-stone-200/90 bg-stone-50/90 text-stone-800 dark:border-stone-600 dark:bg-stone-900 dark:text-stone-200",
  info: "border-brand-200/70 bg-gradient-to-br from-brand-50/80 to-white text-stone-800 dark:border-brand-700/45 dark:bg-stone-900 dark:bg-none dark:text-stone-200",
  warning:
    "border-amber-200/90 bg-gradient-to-br from-amber-50/95 to-white text-amber-950 dark:border-amber-700/50 dark:bg-stone-900 dark:bg-none dark:text-amber-100",
  danger:
    "border-rose-200/90 bg-gradient-to-br from-rose-50/95 to-white text-rose-950 dark:border-rose-800/55 dark:bg-stone-900 dark:bg-none dark:text-rose-100",
  success:
    "border-accent-200/80 bg-gradient-to-br from-accent-50/90 to-white text-accent-900 dark:border-accent-700/45 dark:bg-stone-900 dark:bg-none dark:text-accent-100",
};

/** Quiet informational callout for tool pages. */
export function InfoBanner({
  title,
  children,
  actions,
  tone = "info",
  className = "",
}: {
  title?: string;
  children: ReactNode;
  actions?: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <div
      className={`rounded-2xl border px-4 py-3.5 shadow-sm shadow-stone-900/[0.02] dark:shadow-none ${TONE[tone]} ${className}`}
    >
      {title ? (
        <p className="font-display text-sm font-semibold tracking-tight text-stone-900 dark:text-stone-50">
          {title}
        </p>
      ) : null}
      <div className={`text-sm leading-relaxed ${title ? "mt-1" : ""}`}>{children}</div>
      {actions ? <div className="mt-2.5 flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}
