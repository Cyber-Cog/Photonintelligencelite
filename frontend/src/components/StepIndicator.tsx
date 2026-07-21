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
    <ol className="mb-6 flex items-center gap-1.5 pb-1">
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
                "bg-brand-600 text-white shadow-sm shadow-brand-600/30 ring-2 ring-brand-400/35 ring-offset-2 ring-offset-stone-50 dark:ring-offset-stone-950",
              !isDone && !isActive && "border border-stone-300/90 text-stone-400 dark:border-stone-600",
              linkHref && "group-hover:ring-2 group-hover:ring-brand-400/40",
            )}
          >
            {isDone ? "✓" : stepNum}
          </div>
        );

        const label = (
          <span
            className={clsx(
              "hidden text-xs font-semibold sm:inline",
              isActive
                ? "text-stone-900 dark:text-stone-50"
                : isDone || earlySwap
                  ? "text-accent-700 dark:text-accent-400"
                  : "text-stone-400",
              linkHref && "group-hover:underline",
            )}
          >
            {step}
          </span>
        );

        return (
          <li key={step} className="flex flex-1 items-center gap-1.5">
            {linkHref ? (
              <Link
                to={linkHref}
                className="group flex items-center gap-1.5 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-brand-400/50"
                title={stepNum === 1 ? "Replace files / back to upload" : `Go to ${step}`}
              >
                {circle}
                {label}
              </Link>
            ) : (
              <div className="flex items-center gap-1.5">
                {circle}
                {label}
              </div>
            )}
            {stepNum < STEPS.length && (
              <div
                className={clsx(
                  "mx-0.5 h-px flex-1 transition-colors",
                  isDone ? "bg-accent-400/70 dark:bg-accent-700/60" : "bg-stone-200 dark:bg-stone-800",
                )}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
