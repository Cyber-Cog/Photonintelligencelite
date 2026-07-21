import type { ReactNode } from "react";

/** Page title row: clear hierarchy, Outfit display type, room for actions. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className = "",
}: {
  eyebrow?: ReactNode;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex flex-wrap items-start justify-between gap-3 ${className}`}>
      <div className="min-w-0">
        {eyebrow ? (
          <div className="mb-1.5">
            {typeof eyebrow === "string" ? <p className="tool-eyebrow">{eyebrow}</p> : eyebrow}
          </div>
        ) : null}
        <h2 className="font-display text-xl font-semibold tracking-tight text-stone-900 dark:text-stone-50 sm:text-2xl">
          {title}
        </h2>
        {description ? (
          <div className="mt-1.5 max-w-2xl text-sm leading-relaxed text-stone-500 dark:text-stone-400">
            {description}
          </div>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
