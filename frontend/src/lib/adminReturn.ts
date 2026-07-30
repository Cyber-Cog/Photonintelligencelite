/** Remember where to resume after a temporary Superadmin visit. */

const LAST_APP_PATH_KEY = "pic_lite_last_app_path";
const ADMIN_RETURN_KEY = "pic_lite_admin_return";
const ADMIN_CAN_BACK_KEY = "pic_lite_admin_can_back";

const AUTH_PREFIXES = ["/login", "/signup", "/verify-email", "/forgot-password", "/reset-password"];

function isAuthPath(pathname: string): boolean {
  return AUTH_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}?`));
}

/** Safe in-app path only (no open redirects). */
export function sanitizeReturnPath(raw: string | null | undefined): string | null {
  if (!raw) return null;
  let path = raw.trim();
  try {
    path = decodeURIComponent(path);
  } catch {
    /* keep raw */
  }
  if (!path.startsWith("/") || path.startsWith("//") || path.startsWith("/\\")) return null;
  if (path === "/admin" || path.startsWith("/admin?") || path.startsWith("/admin#")) return null;
  if (isAuthPath(path.split(/[?#]/)[0] || "")) return null;
  return path;
}

/** Track the latest non-admin app location for resume. */
export function rememberAppPath(fullPath: string): void {
  const safe = sanitizeReturnPath(fullPath);
  if (!safe) return;
  try {
    sessionStorage.setItem(LAST_APP_PATH_KEY, safe);
  } catch {
    /* ignore */
  }
}

export function getLastAppPath(): string | null {
  try {
    return sanitizeReturnPath(sessionStorage.getItem(LAST_APP_PATH_KEY));
  } catch {
    return null;
  }
}

/** Call when navigating into /admin from the in-app header/settings. */
export function stashAdminReturn(fullPath: string): void {
  const safe = sanitizeReturnPath(fullPath);
  if (!safe) return;
  try {
    sessionStorage.setItem(ADMIN_RETURN_KEY, safe);
    sessionStorage.setItem(ADMIN_CAN_BACK_KEY, "1");
    sessionStorage.setItem(LAST_APP_PATH_KEY, safe);
  } catch {
    /* ignore */
  }
}

function takeStashedReturn(): string | null {
  try {
    const v = sanitizeReturnPath(sessionStorage.getItem(ADMIN_RETURN_KEY));
    sessionStorage.removeItem(ADMIN_RETURN_KEY);
    return v;
  } catch {
    return null;
  }
}

function canUseHistoryBack(): boolean {
  try {
    if (sessionStorage.getItem(ADMIN_CAN_BACK_KEY) !== "1") return false;
    sessionStorage.removeItem(ADMIN_CAN_BACK_KEY);
    return typeof window !== "undefined" && window.history.length > 1;
  } catch {
    return false;
  }
}

export type ExitAdminResult =
  | { kind: "back" }
  | { kind: "path"; path: string };

/** After a full reload, history-back is unreliable — fall through to stored paths. */
export function clearAdminBackOnReload(): void {
  try {
    const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
    if (nav?.type === "reload") {
      sessionStorage.removeItem(ADMIN_CAN_BACK_KEY);
    }
  } catch {
    /* ignore */
  }
}

/**
 * Prefer browser back when we entered admin from an in-app route;
 * otherwise use returnTo / stashed path / last app path / Analyze hub.
 */
export function resolveExitAdmin(returnToQuery?: string | null): ExitAdminResult {
  if (canUseHistoryBack()) {
    return { kind: "back" };
  }
  const path =
    sanitizeReturnPath(returnToQuery) ?? takeStashedReturn() ?? getLastAppPath() ?? "/upload";
  return { kind: "path", path };
}

export function adminHrefFrom(currentFullPath: string): string {
  const safe = sanitizeReturnPath(currentFullPath);
  if (!safe) return "/admin";
  return `/admin?returnTo=${encodeURIComponent(safe)}`;
}
