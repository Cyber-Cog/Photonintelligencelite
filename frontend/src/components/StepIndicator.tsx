import { Fragment } from "react";
import clsx from "clsx";
import { Link } from "react-router-dom";

const STEPS = ["Upload", "Setup", "Validate", "Analyze", "Results"] as const;

function hrefForStep(stepNum: number, jobId?: string | null): string | null {
  if (stepNum === 1) {
    return jobId ? `/upload?replace=${encodeURIComponent(jobId)}` : "/upload";
  }
  if (!jobId) return null;
  if (stepNum === 2) return `/jobs/${jobId}/setup`;
  if (stepNum === 3) return `/jobs/${jobId}/validate`;
  if (stepNum === 4) return `/jobs/${jobId}/processing`;
  if (stepNum === 5) return `/jobs/${jobId}/dashboard`;
  return null;
}

/** Completed steps (and Upload↔Setup) are clickable when a job id is known. */
export function StepIndicator({
  current,
  jobId,
}: {
  current: number;
  jobId?: string | null;
}) {
  return (
    <ol className="flex w-full items-center rounded-pic-xl border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)] px-2 py-2.5 shadow-pic sm:px-3">
      {STEPS.map((step, idx) => {
        const stepNum = idx + 1;
        const isDone = stepNum < current;
        const isActive = stepNum === current;
        const href = hrefForStep(stepNum, jobId);
        // Completed steps + Upload↔Setup when a job exists.
        const earlySwap =
          Boolean(jobId) && (stepNum === 1 || stepNum === 2) && stepNum !== current;
        const canNavigate = Boolean(href) && (isDone || earlySwap);
        const linkHref = canNavigate ? href : null;

        const circle = (
          <div
            className={clsx(
              "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-bold transition-all duration-200",
              isDone && "bg-accent-600 text-white shadow-sm shadow-accent-600/25",
              isActive &&
                "bg-brand-600 text-white shadow-sm shadow-brand-600/30 ring-2 ring-brand-400/35 ring-offset-2 ring-offset-[color:var(--pic-surface-raised)]",
              !isDone && !isActive && "border border-[color:var(--pic-border-strong)] text-[color:var(--pic-text-muted)]",
              linkHref && "group-hover:ring-2 group-hover:ring-brand-400/40",
            )}
          >
            {isDone ? "✓" : stepNum}
          </div>
        );

        const label = (
          <span
            className={clsx(
              "hidden truncate text-xs font-semibold sm:inline",
              isActive
                ? "text-[color:var(--pic-text)]"
                : isDone || earlySwap
                  ? "text-accent-700 dark:text-accent-400"
                  : "text-[color:var(--pic-text-muted)]",
              linkHref && "group-hover:underline",
            )}
          >
            {step}
          </span>
        );

        const node = linkHref ? (
          <Link
            to={linkHref}
            className="group flex items-center justify-center gap-2 rounded-pic outline-none focus-visible:ring-2 focus-visible:ring-brand-400/50"
            title={stepNum === 1 ? "Replace files / back to upload" : `Go to ${step}`}
          >
            {circle}
            {label}
          </Link>
        ) : (
          <div className="flex items-center justify-center gap-2">
            {circle}
            {label}
          </div>
        );

        return (
          <Fragment key={step}>
            {/* Equal-width step columns; connectors are separate fixed rails. */}
            <li className="flex min-w-0 flex-1 items-center justify-center px-0.5">{node}</li>
            {stepNum < STEPS.length ? (
              <li
                className={clsx(
                  "mx-0.5 h-px w-4 shrink-0 list-none sm:mx-1 sm:w-6 md:w-8",
                  isDone ? "bg-accent-400/70 dark:bg-accent-700/60" : "bg-[color:var(--pic-border)]",
                )}
                aria-hidden
              />
            ) : null}
          </Fragment>
        );
      })}
    </ol>
  );
}
