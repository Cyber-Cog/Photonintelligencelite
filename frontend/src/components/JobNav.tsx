import { NavLink, useParams } from "react-router-dom";

const TABS = [
  { to: "dashboard", label: "Results", tour: "nav-results" },
  { to: "data", label: "Raw data", tour: "nav-data" },
  { to: "architecture", label: "Architecture", tour: "nav-architecture" },
  { to: "explore", label: "Signal Explorer", tour: "nav-explore" },
] as const;

export function JobNav() {
  const { jobId } = useParams<{ jobId: string }>();
  if (!jobId) return null;

  return (
    <nav
      className="mb-4 flex w-full gap-0 overflow-x-auto overflow-y-hidden border-b border-stone-200/80 dark:border-stone-800"
      aria-label="Job views"
      data-tour="job-nav"
    >
      {TABS.map(({ to, label, tour }) => (
        <NavLink
          key={to}
          to={`/jobs/${jobId}/${to}`}
          data-tour={tour}
          className={({ isActive }) => (isActive ? "nav-tab-active" : "nav-tab")}
        >
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
