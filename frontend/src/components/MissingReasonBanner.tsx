import { Link } from "react-router-dom";
import { fixHref, type MissingReason } from "@/lib/missingReasons";

export function MissingReasonBanner({
  reasons,
  jobId,
  className = "",
}: {
  reasons: MissingReason[];
  jobId: string;
  className?: string;
}) {
  if (!reasons.length) return null;

  return (
    <ul className={`space-y-1.5 ${className}`} role="list">
      {reasons.map((r) => (
        <li key={r.id}>
          <Link
            to={fixHref(jobId, r.fix)}
            className="group flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50/90 px-3 py-2 text-xs leading-relaxed text-amber-950 transition hover:bg-amber-100/90 dark:border-amber-900/50 dark:bg-amber-950/35 dark:text-amber-100 dark:hover:bg-amber-950/55"
          >
            <span className="min-w-0 flex-1">{r.message}</span>
            <span className="shrink-0 font-semibold text-amber-800 underline-offset-2 group-hover:underline dark:text-amber-200">
              Fix
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
