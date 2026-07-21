import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { authApi } from "@/api/client";
import { TourOverlay } from "@/components/demoTour/TourOverlay";
import { DEMO_TOUR_STEPS, type TourRoute, type TourStepDef } from "@/components/demoTour/tourSteps";
import { useAuth } from "@/context/AuthContext";
import {
  clearAnonymousTourDone,
  clearTourPending,
  getTourPendingJobId,
  isTourCompleted,
  markAnonymousTourDone,
  setTourPending,
} from "@/lib/demoTour";
import { activateResultsSection, isMostlyInView } from "@/lib/resultsNav";

interface DemoTourContextValue {
  active: boolean;
  /** Call after Run demo succeeds — schedules tour when Results are ready. */
  armAfterDemo: (jobId: string) => void;
  /** Start immediately (e.g. Replay from settings). */
  startTour: (jobId: string) => void;
  /** True if this account/browser already finished the tour. */
  tourDone: boolean;
  /** Clear completion and arm for replay. */
  prepareReplay: (jobId?: string | null) => Promise<void>;
}

const DemoTourContext = createContext<DemoTourContextValue | null>(null);

function jobRoute(jobId: string, route: TourRoute): string {
  return `/jobs/${jobId}/${route}`;
}

function currentTourRoute(pathname: string): TourRoute | null {
  const m = pathname.match(/\/jobs\/[^/]+\/(dashboard|data|architecture|explore)/);
  return (m?.[1] as TourRoute) || null;
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function waitForSelector(selector: string, timeoutMs = 8000): Promise<Element | null> {
  return new Promise((resolve) => {
    const existing = document.querySelector(selector);
    if (existing && isTargetUsable(existing)) {
      resolve(existing);
      return;
    }
    const started = Date.now();
    const obs = new MutationObserver(() => {
      const el = document.querySelector(selector);
      if (el && isTargetUsable(el)) {
        obs.disconnect();
        resolve(el);
      } else if (Date.now() - started > timeoutMs) {
        obs.disconnect();
        resolve(null);
      }
    });
    obs.observe(document.body, { childList: true, subtree: true });
    window.setTimeout(() => {
      obs.disconnect();
      const el = document.querySelector(selector);
      resolve(el && isTargetUsable(el) ? el : null);
    }, timeoutMs);
  });
}

function isTargetUsable(el: Element): boolean {
  const r = el.getBoundingClientRect();
  return r.width >= 2 && r.height >= 2;
}

/** Wait until scroll events settle (or a short fallback). */
function waitForScrollEnd(timeoutMs = 120): Promise<void> {
  return new Promise((resolve) => {
    let settled: ReturnType<typeof setTimeout> | null = null;
    let finished = false;
    const done = () => {
      if (finished) return;
      finished = true;
      window.removeEventListener("scroll", onScroll, true);
      if (settled) clearTimeout(settled);
      resolve();
    };
    const onScroll = () => {
      if (settled) clearTimeout(settled);
      settled = setTimeout(done, 50);
    };
    window.addEventListener("scroll", onScroll, true);
    settled = setTimeout(done, timeoutMs);
  });
}

/**
 * Bring target into view once — instant only, and only if off-screen.
 * Sidebar layouts should already have the pane visible after section switch.
 */
async function ensureTargetInView(el: Element): Promise<void> {
  if (isMostlyInView(el)) return;
  el.scrollIntoView({ behavior: "auto", block: "center", inline: "nearest" });
  await waitForScrollEnd(prefersReducedMotion() ? 40 : 100);
}

/**
 * Switch Results section (sidebar/tabs) then wait for the spotlight target.
 * Missing targets return null so the step can be skipped gracefully.
 */
async function prepareStepTarget(step: TourStepDef): Promise<Element | null> {
  if (step.resultsSection) {
    try {
      await activateResultsSection(step.resultsSection);
    } catch {
      // never crash the tour on section switch
    }
  }

  if (!step.selector) return null;

  const waitMs = step.optional ? 1600 : 5000;
  const el = await waitForSelector(step.selector, waitMs);
  if (!el) return null;

  try {
    await ensureTargetInView(el);
  } catch {
    // ignore scroll failures
  }
  return el;
}

type ScrollLock = { y: number };

function lockBodyScroll(): ScrollLock {
  const y = window.scrollY;
  const body = document.body;
  body.dataset.tourScrollLock = "1";
  body.style.overflow = "hidden";
  body.style.position = "fixed";
  body.style.top = `-${y}px`;
  body.style.left = "0";
  body.style.right = "0";
  body.style.width = "100%";
  return { y };
}

function unlockBodyScroll(lock: ScrollLock | null) {
  const body = document.body;
  if (body.dataset.tourScrollLock !== "1") return;
  delete body.dataset.tourScrollLock;
  body.style.overflow = "";
  body.style.position = "";
  body.style.top = "";
  body.style.left = "";
  body.style.right = "";
  body.style.width = "";
  if (lock) {
    try {
      window.scrollTo(0, lock.y);
    } catch {
      // ignore
    }
  }
}

export function DemoTourProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, refresh } = useAuth();
  const [active, setActive] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [resolvedStep, setResolvedStep] = useState<TourStepDef | null>(null);
  const advancingRef = useRef(false);
  const completingRef = useRef(false);
  const scrollLockRef = useRef<ScrollLock | null>(null);
  const lastRouteRef = useRef<TourRoute | null>(null);
  const sessionRef = useRef(0);

  const tourDone = isTourCompleted(user?.tour_completed_at, Boolean(user));

  const persistComplete = useCallback(async () => {
    markAnonymousTourDone();
    clearTourPending();
    if (user) {
      try {
        await authApi.completeTour();
        await refresh();
      } catch {
        // localStorage already marked; server flag best-effort
      }
    }
  }, [user, refresh]);

  const finish = useCallback(async () => {
    if (completingRef.current) return;
    completingRef.current = true;
    unlockBodyScroll(scrollLockRef.current);
    scrollLockRef.current = null;
    lastRouteRef.current = null;
    setActive(false);
    setResolvedStep(null);
    setJobId(null);
    setStepIndex(0);
    await persistComplete();
    completingRef.current = false;
  }, [persistComplete]);

  const goToStep = useCallback(
    async (index: number, forJobId: string, direction: "forward" | "back" = "forward") => {
      if (advancingRef.current) return;
      advancingRef.current = true;
      const session = ++sessionRef.current;
      try {
        unlockBodyScroll(scrollLockRef.current);
        scrollLockRef.current = null;
        setActive(false);
        setResolvedStep(null);

        let i = index;
        while (i >= 0 && i < DEMO_TOUR_STEPS.length) {
          if (session !== sessionRef.current) return;

          const step = DEMO_TOUR_STEPS[i];
          const targetPath = jobRoute(forJobId, step.route);
          let onTargetPath = false;
          try {
            onTargetPath = window.location.pathname.includes(`/jobs/${forJobId}/${step.route}`);
          } catch {
            onTargetPath = false;
          }
          const routeChanged = lastRouteRef.current !== step.route || !onTargetPath;

          if (routeChanged) {
            try {
              navigate(targetPath);
            } catch {
              // route change failed — skip this step rather than crash
              i += direction === "forward" ? 1 : -1;
              continue;
            }
            await new Promise((r) => setTimeout(r, 100));
            if (session !== sessionRef.current) return;
          }
          lastRouteRef.current = step.route;

          if (step.selector) {
            const el = await prepareStepTarget(step);
            if (session !== sessionRef.current) return;
            if (!el) {
              i += direction === "forward" ? 1 : -1;
              continue;
            }
          } else {
            if (step.resultsSection) {
              try {
                await activateResultsSection(step.resultsSection);
              } catch {
                // ignore
              }
            }
            if (step.placement === "center") {
              try {
                window.scrollTo({ top: 0, behavior: "auto" });
                await waitForScrollEnd(40);
              } catch {
                // ignore
              }
            }
          }

          if (session !== sessionRef.current) return;

          scrollLockRef.current = lockBodyScroll();
          setStepIndex(i);
          setResolvedStep(step);
          setActive(true);
          return;
        }
        if (direction === "forward") {
          await finish();
        } else {
          setStepIndex(0);
          setResolvedStep(DEMO_TOUR_STEPS[0]);
          scrollLockRef.current = lockBodyScroll();
          setActive(true);
        }
      } catch {
        // Never leave the app in a broken tour state
        unlockBodyScroll(scrollLockRef.current);
        scrollLockRef.current = null;
        setActive(false);
        setResolvedStep(null);
      } finally {
        advancingRef.current = false;
      }
    },
    [navigate, finish],
  );

  const startTour = useCallback(
    (id: string) => {
      setJobId(id);
      setTourPending(id);
      lastRouteRef.current = null;
      void goToStep(0, id);
    },
    [goToStep],
  );

  const armAfterDemo = useCallback(
    (id: string) => {
      if (isTourCompleted(user?.tour_completed_at, Boolean(user))) {
        clearTourPending();
        return;
      }
      setTourPending(id);
    },
    [user],
  );

  const prepareReplay = useCallback(
    async (id?: string | null) => {
      clearAnonymousTourDone();
      if (user) {
        try {
          await authApi.resetTour();
          await refresh();
        } catch {
          // still allow local replay
        }
      }
      if (id) {
        setTourPending(id);
        startTour(id);
      } else {
        try {
          sessionStorage.setItem("pic_demo_tour_replay", "1");
        } catch {
          // ignore
        }
      }
    },
    [user, refresh, startTour],
  );

  // Auto-start when Results dashboard is ready and tour is armed
  useEffect(() => {
    if (active || tourDone || jobId || advancingRef.current) return;
    const pending = getTourPendingJobId();
    if (!pending) return;
    const onDashboard =
      location.pathname === `/jobs/${pending}/dashboard` ||
      (currentTourRoute(location.pathname) === "dashboard" &&
        location.pathname.includes(pending));
    if (!onDashboard) return;

    let cancelled = false;
    const tryStart = async () => {
      const el = await waitForSelector("[data-tour='results-welcome']", 20000);
      if (cancelled || !el) return;
      if (getTourPendingJobId() !== pending) return;
      if (isTourCompleted(user?.tour_completed_at, Boolean(user))) {
        clearTourPending();
        return;
      }
      setJobId(pending);
      void goToStep(0, pending);
    };
    void tryStart();
    return () => {
      cancelled = true;
    };
  }, [location.pathname, active, tourDone, jobId, user, goToStep]);

  // Replay from settings without a job: start when user lands on any job dashboard
  useEffect(() => {
    if (active || tourDone || jobId || advancingRef.current) return;
    let replay = false;
    try {
      replay = sessionStorage.getItem("pic_demo_tour_replay") === "1";
    } catch {
      replay = false;
    }
    if (!replay) return;
    const m = location.pathname.match(/\/jobs\/([^/]+)\/dashboard/);
    if (!m) return;
    try {
      sessionStorage.removeItem("pic_demo_tour_replay");
    } catch {
      // ignore
    }
    setTourPending(m[1]);
    setJobId(m[1]);
    void goToStep(0, m[1]);
  }, [location.pathname, active, tourDone, jobId, goToStep]);

  // Safety: unlock scroll if provider unmounts mid-tour
  useEffect(() => {
    return () => {
      sessionRef.current += 1;
      unlockBodyScroll(scrollLockRef.current);
      scrollLockRef.current = null;
    };
  }, []);

  const onNext = useCallback(() => {
    if (!jobId) return;
    if (stepIndex >= DEMO_TOUR_STEPS.length - 1) {
      void finish();
      return;
    }
    void goToStep(stepIndex + 1, jobId);
  }, [jobId, stepIndex, goToStep, finish]);

  const onBack = useCallback(() => {
    if (!jobId || stepIndex <= 0) return;
    void goToStep(stepIndex - 1, jobId, "back");
  }, [jobId, stepIndex, goToStep]);

  const onSkip = useCallback(() => {
    void finish();
  }, [finish]);

  const onTargetMissing = useCallback(() => {
    if (!jobId || advancingRef.current) return;
    if (stepIndex >= DEMO_TOUR_STEPS.length - 1) {
      void finish();
      return;
    }
    void goToStep(stepIndex + 1, jobId);
  }, [jobId, stepIndex, goToStep, finish]);

  const value = useMemo(
    () => ({
      active,
      armAfterDemo,
      startTour,
      tourDone,
      prepareReplay,
    }),
    [active, armAfterDemo, startTour, tourDone, prepareReplay],
  );

  return (
    <DemoTourContext.Provider value={value}>
      {children}
      {active && resolvedStep ? (
        <TourOverlay
          step={resolvedStep}
          stepIndex={stepIndex}
          stepCount={DEMO_TOUR_STEPS.length}
          onNext={onNext}
          onBack={onBack}
          onSkip={onSkip}
          onTargetMissing={onTargetMissing}
        />
      ) : null}
    </DemoTourContext.Provider>
  );
}

export function useDemoTour() {
  const ctx = useContext(DemoTourContext);
  if (!ctx) throw new Error("useDemoTour must be used within DemoTourProvider");
  return ctx;
}
