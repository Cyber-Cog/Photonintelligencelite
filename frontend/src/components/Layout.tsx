import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { BrandWordmark } from "@/components/BrandWordmark";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/context/ThemeContext";

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4" aria-hidden>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4" aria-hidden>
      <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
    </svg>
  );
}

function ProfileMenu() {
  const { user, logout, isSuperadmin } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  if (!user) return null;

  const initials = (user.name || user.email)
    .split(/\s+/)
    .map((part: string) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="relative flex items-center" ref={ref}>
      <button
        type="button"
        className="inline-flex items-center gap-2 rounded-lg border border-stone-300/90 bg-white px-2 py-1 text-sm text-stone-700 shadow-sm transition hover:bg-stone-50 dark:border-stone-600 dark:bg-stone-900 dark:text-stone-200 dark:hover:bg-stone-800"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-600 text-[10px] font-bold text-white">
          {initials}
        </span>
        <span className="hidden max-w-[8rem] truncate sm:inline">{user.name || user.email}</span>
      </button>
      {open ? (
        <div
          role="menu"
          className="absolute right-0 top-full z-30 mt-1.5 min-w-[11rem] rounded-xl border border-stone-200 bg-white py-1 shadow-lg dark:border-stone-700 dark:bg-stone-900"
        >
          <Link
            to="/settings"
            role="menuitem"
            className="block px-3 py-2 text-sm text-stone-700 hover:bg-stone-50 dark:text-stone-200 dark:hover:bg-stone-800"
            onClick={() => setOpen(false)}
          >
            Settings
          </Link>
          {isSuperadmin ? (
            <Link
              to="/admin"
              role="menuitem"
              className="block px-3 py-2 text-sm text-stone-700 hover:bg-stone-50 dark:text-stone-200 dark:hover:bg-stone-800"
              onClick={() => setOpen(false)}
            >
              Admin
            </Link>
          ) : null}
          <button
            type="button"
            role="menuitem"
            className="block w-full px-3 py-2 text-left text-sm text-rose-700 hover:bg-stone-50 dark:text-rose-400 dark:hover:bg-stone-800"
            onClick={async () => {
              setOpen(false);
              await logout();
              navigate("/");
            }}
          >
            Log out
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const { theme, toggleTheme } = useTheme();
  const { user, loading, connecting, connectAttempt, apiUnreachable, refresh } = useAuth();
  const location = useLocation();
  const isLanding = location.pathname === "/";

  return (
    <div className="relative flex min-h-screen flex-col bg-stone-50 text-stone-900 dark:bg-stone-950 dark:text-stone-100">
      {!isLanding && <div className="hero-mesh" aria-hidden />}
      {connecting ? (
        <div
          className="border-b border-amber-200/80 bg-amber-50 px-4 py-2 text-center text-sm text-amber-950 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-100"
          role="status"
          aria-live="polite"
        >
          Connecting to API…{connectAttempt > 1 ? ` (attempt ${connectAttempt})` : ""}
        </div>
      ) : null}
      {!connecting && apiUnreachable ? (
        <div
          className="flex flex-wrap items-center justify-center gap-3 border-b border-rose-200/80 bg-rose-50 px-4 py-2 text-center text-sm text-rose-900 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-100"
          role="alert"
        >
          <span>Can't reach the API right now.</span>
          <button type="button" className="btn-secondary px-2.5 py-1 text-xs" onClick={() => void refresh()}>
            Retry
          </button>
        </div>
      ) : null}
      <header className={`app-header ${isLanding ? "app-header-landing" : ""}`}>
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4 sm:gap-4 sm:px-6">
          <div className="flex min-w-0 flex-1 items-center gap-3 sm:gap-5">
            <BrandWordmark variant="header" linkHome />
            <nav className="hidden items-center gap-0.5 sm:flex" aria-label="Primary">
              <Link to="/" className={location.pathname === "/" ? "nav-tab-active" : "nav-tab"}>
                Home
              </Link>
              <Link to="/docs" className={location.pathname === "/docs" ? "nav-tab-active" : "nav-tab"}>
                Algorithms
              </Link>
              <Link to="/upload" className={location.pathname === "/upload" ? "nav-tab-active" : "nav-tab"}>
                Analyze
              </Link>
            </nav>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {!loading && !user ? (
              <>
                <Link to="/login" className="btn-ghost hidden px-2.5 py-1.5 text-xs sm:inline-flex">
                  Log in
                </Link>
                <Link to="/signup" className="btn-secondary px-2.5 py-1.5 text-xs">
                  Sign up
                </Link>
              </>
            ) : null}
            {!loading && user ? <ProfileMenu /> : null}
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
              title={theme === "dark" ? "Light mode" : "Dark mode"}
              className="theme-toggle"
            >
              {theme === "dark" ? <SunIcon /> : <MoonIcon />}
            </button>
          </div>
        </div>
      </header>
      <main
        className={
          isLanding
            ? "relative flex w-full flex-1 flex-col"
            : "relative mx-auto flex w-full max-w-6xl flex-1 flex-col px-4 py-5 sm:px-6"
        }
      >
        {children}
      </main>
      <footer className={`app-footer ${isLanding ? "app-footer-landing" : ""}`}>
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-center gap-x-1.5 gap-y-1 px-4 sm:px-6">
          <BrandWordmark variant="footer" />
          <span className="leading-none text-stone-300 dark:text-stone-600" aria-hidden>
            ·
          </span>
          <span className="leading-none">Solar SCADA analytics</span>
          <span className="leading-none text-stone-300 dark:text-stone-600" aria-hidden>
            ·
          </span>
          <Link to="/docs" className="leading-none text-brand-700 hover:underline dark:text-brand-400">
            Algorithm documentation
          </Link>
        </div>
      </footer>
    </div>
  );
}
