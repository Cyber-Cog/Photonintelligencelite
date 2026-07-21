import type { ReactNode } from "react";

type Accent = "brand" | "accent" | "neutral" | "amber" | "rose";

const ACCENT_DOT: Record<Accent, string> = {
  brand: "bg-brand-500",
  accent: "bg-accent-500",
  neutral: "bg-stone-400",
  amber: "bg-amber-500",
  rose: "bg-rose-500",
};

const ACCENT_BAR: Record<Accent, string> = {
  brand: "from-brand-400/80 to-brand-500/20 dark:from-brand-500/50 dark:to-brand-800/15",
  accent: "from-accent-400/80 to-accent-500/20 dark:from-accent-500/45 dark:to-accent-800/15",
  neutral: "from-stone-300 to-stone-200/40 dark:from-stone-600 dark:to-stone-700/40",
  amber: "from-amber-400/80 to-amber-500/20 dark:from-amber-500/50 dark:to-amber-700/15",
  rose: "from-rose-400/80 to-rose-500/20 dark:from-rose-500/45 dark:to-rose-800/15",
};

/**
 * Soft content panel for tool pages — readable hierarchy, landing-adjacent depth.
 */
export function SectionPanel({
  id,
  title,
  description,
  actions,
  children,
  accent = "brand",
  className = "",
  bodyClassName = "",
  scrollMargin = true,
  /** Flatten chrome when nested inside a shared shell (e.g. Setup step card). */
  embedded = false,
}: {
  id?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  accent?: Accent;
  className?: string;
  bodyClassName?: string;
  scrollMargin?: boolean;
  embedded?: boolean;
}) {
  return (
    <section
      id={id}
      className={`${
        embedded
          ? "bg-transparent"
          : "overflow-hidden rounded-2xl border border-stone-200/90 bg-white/95 dark:border-stone-700 dark:bg-stone-900"
      } ${scrollMargin ? "scroll-mt-44" : ""} ${className}`}
    >
      <div className={`h-0.5 w-full bg-gradient-to-r ${ACCENT_BAR[accent]}`} aria-hidden />
      <div className="flex flex-wrap items-start justify-between gap-3 px-4 pb-0 pt-4 sm:px-5 sm:pt-5">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${ACCENT_DOT[accent]}`} aria-hidden />
            <h3 className="font-display text-sm font-semibold tracking-tight text-stone-900 dark:text-stone-50">
              {title}
            </h3>
          </div>
          {description ? (
            <div className="mt-1 pl-3.5 text-xs leading-relaxed text-stone-500 dark:text-stone-400">
              {description}
            </div>
          ) : null}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-1.5">{actions}</div> : null}
      </div>
      <div className={bodyClassName || "p-4 sm:p-5"}>{children}</div>
    </section>
  );
}
