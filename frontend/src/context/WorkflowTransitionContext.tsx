import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { TransitionOverlay } from "@/components/transition/TransitionOverlay";
import type { TransitionPhase } from "@/components/transition/transitionScripts";

/** Keep overlay brief — real work finishes on the next page (Validate polls). */
const MIN_VISIBLE_MS = 280;

type WorkflowTransitionContextValue = {
  active: boolean;
  phase: TransitionPhase | null;
  /** Show overlay for a phase while `work` runs; keeps a minimum visible time. */
  runWithTransition: <T>(phase: TransitionPhase, work: () => Promise<T> | T) => Promise<T>;
};

const WorkflowTransitionContext = createContext<WorkflowTransitionContextValue | null>(null);

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function WorkflowTransitionProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState<TransitionPhase | null>(null);
  const generation = useRef(0);

  const runWithTransition = useCallback(async <T,>(p: TransitionPhase, work: () => Promise<T> | T) => {
    const gen = ++generation.current;
    setPhase(p);
    setOpen(true);
    const started = Date.now();
    try {
      return await work();
    } finally {
      if (generation.current === gen) {
        const minMs = prefersReducedMotion() ? 0 : MIN_VISIBLE_MS;
        const elapsed = Date.now() - started;
        if (elapsed < minMs) await delay(minMs - elapsed);
        if (generation.current === gen) {
          setOpen(false);
          setPhase(null);
        }
      }
    }
  }, []);

  const value = useMemo(
    () => ({
      active: open,
      phase,
      runWithTransition,
    }),
    [open, phase, runWithTransition],
  );

  return (
    <WorkflowTransitionContext.Provider value={value}>
      {children}
      <TransitionOverlay open={open} phase={phase} />
    </WorkflowTransitionContext.Provider>
  );
}

export function useWorkflowTransition(): WorkflowTransitionContextValue {
  const ctx = useContext(WorkflowTransitionContext);
  if (!ctx) throw new Error("useWorkflowTransition must be used within WorkflowTransitionProvider");
  return ctx;
}
