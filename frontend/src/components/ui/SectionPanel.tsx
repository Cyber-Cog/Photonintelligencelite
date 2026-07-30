import type { ReactNode } from "react";

type Accent = "brand" | "accent" | "neutral" | "amber" | "rose";

const ACCENT_DOT: Record<Accent, string> = {
  brand: "bg-brand-500",
  accent: "bg-accent-500",
  neutral: "bg-stone-400",
  amber: "bg-amber-500",
  rose: "bg-rose-500",
};

/**
 * Soft content panel — one surface language; optional flush mode when nested in a workspace.
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
          : "overflow-hidden rounded-pic-lg border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] shadow-pic"
      } ${scrollMargin ? "scroll-mt-44" : ""} ${className}`}
    >
      {!embedded ? <div className="panel-rule shrink-0" aria-hidden /> : null}
      <div className="flex shrink-0 flex-wrap items-start justify-between gap-2 px-4 pb-0 pt-3 sm:px-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${ACCENT_DOT[accent]}`} aria-hidden />
            <h3 className="font-display text-pic-base font-semibold tracking-tight text-[color:var(--pic-text)]">
              {title}
            </h3>
          </div>
          {description ? (
            <div className="mt-1 pl-3.5 text-pic-xs leading-snug text-[color:var(--pic-text-muted)]">
              {description}
            </div>
          ) : null}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      <div className={bodyClassName || "p-4"}>{children}</div>
    </section>
  );
}
