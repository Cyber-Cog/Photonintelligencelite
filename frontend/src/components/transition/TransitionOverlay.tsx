import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import clsx from "clsx";
import { Spinner } from "@/components/ui/Spinner";
import type { LogLevel } from "@/components/processing/useAnalysisLog";
import {
  TRANSITION_SCRIPTS,
  TRANSITION_SUBTITLES,
  TRANSITION_TITLES,
  type TransitionPhase,
} from "./transitionScripts";

const LEVEL_STYLE: Record<LogLevel, string> = {
  info: "text-stone-500 dark:text-stone-400",
  ok: "text-accent-700 dark:text-accent-400",
  run: "text-brand-800 dark:text-brand-300",
  wait: "text-amber-700 dark:text-amber-400",
  warn: "text-rose-700 dark:text-rose-400",
};

const LEVEL_TAG: Record<LogLevel, string> = {
  info: "INFO",
  ok: "DONE",
  run: "EXEC",
  wait: "WAIT",
  warn: "FAIL",
};

type VisibleLine = { id: number; level: LogLevel; text: string };

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Fullscreen soft overlay during workflow Continue transitions.
 * Portaled to body — covers the viewport; page content stays underneath.
 */
export function TransitionOverlay({
  open,
  phase,
}: {
  open: boolean;
  phase: TransitionPhase | null;
}) {
  const [lines, setLines] = useState<VisibleLine[]>([]);
  const [visible, setVisible] = useState(false);
  const [exiting, setExiting] = useState(false);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const timersRef = useRef<number[]>([]);
  const seqRef = useRef(0);

  // Enter / exit visibility so exit can animate briefly
  useEffect(() => {
    if (open && phase) {
      setExiting(false);
      setVisible(true);
      return;
    }
    if (!visible) return;
    setExiting(true);
    const id = window.setTimeout(() => {
      setVisible(false);
      setExiting(false);
      setLines([]);
    }, prefersReducedMotion() ? 0 : 180);
    return () => window.clearTimeout(id);
  }, [open, phase, visible]);

  // Stream script lines while open
  useEffect(() => {
    timersRef.current.forEach((t) => window.clearTimeout(t));
    timersRef.current = [];
    seqRef.current = 0;
    setLines([]);

    if (!open || !phase) return;

    const script = TRANSITION_SCRIPTS[phase];
    const reduced = prefersReducedMotion();

    script.forEach((row) => {
      const delay = reduced ? 0 : row.delayMs;
      const tid = window.setTimeout(() => {
        seqRef.current += 1;
        const id = seqRef.current;
        setLines((prev) => {
          const next = [...prev, { id, level: row.level, text: row.text }];
          return next.length > 12 ? next.slice(-12) : next;
        });
      }, delay);
      timersRef.current.push(tid);
    });

    return () => {
      timersRef.current.forEach((t) => window.clearTimeout(t));
      timersRef.current = [];
    };
  }, [open, phase]);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [lines]);

  // Lock body scroll while overlay is up
  useEffect(() => {
    if (!visible) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [visible]);

  if (!visible || !phase) return null;

  const node = (
    <div
      className={clsx(
        "fixed inset-0 z-[200] flex items-center justify-center p-4 sm:p-6",
        "bg-stone-950/45 backdrop-blur-[3px] dark:bg-stone-950/65",
        exiting ? "transition-overlay-exit" : "transition-overlay-enter",
      )}
      role="alertdialog"
      aria-modal="true"
      aria-busy="true"
      aria-labelledby="pic-transition-title"
      aria-describedby="pic-transition-desc"
    >
      <div className="transition-overlay-card w-full max-w-md overflow-hidden rounded-xl border border-stone-200/90 bg-[color:var(--pic-surface-raised)] shadow-pic dark:border-stone-700">
        <header className="flex items-start gap-3 border-b border-[color:var(--pic-border-subtle)] px-4 py-3">
          <Spinner className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="min-w-0">
            <p
              id="pic-transition-title"
              className="font-display text-sm font-semibold tracking-tight text-[color:var(--pic-text)]"
            >
              {TRANSITION_TITLES[phase]}
            </p>
            <p id="pic-transition-desc" className="mt-0.5 text-xs text-[color:var(--pic-text-muted)]">
              {TRANSITION_SUBTITLES[phase]}
            </p>
          </div>
          <span className="ml-auto inline-flex shrink-0 items-center gap-1 rounded-md bg-accent-50 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-accent-800 dark:bg-accent-950/50 dark:text-accent-300 proc-live-dot">
            <span className="h-1.5 w-1.5 rounded-full bg-accent-500" aria-hidden />
            Live
          </span>
        </header>

        <div
          ref={scrollerRef}
          className="proc-log-scroll max-h-[11rem] min-h-[7.5rem] overflow-y-auto bg-[color:var(--pic-surface-inset)] px-3.5 py-2.5"
          role="log"
          aria-live="polite"
          aria-relevant="additions"
        >
          {lines.length === 0 ? (
            <p className="font-mono text-[11px] text-stone-400">Starting…</p>
          ) : (
            <ul className="space-y-0.5">
              {lines.map((line) => (
                <li
                  key={line.id}
                  className="proc-log-line flex gap-1.5 font-mono text-[10px] leading-relaxed sm:text-[11px]"
                >
                  <span
                    className={clsx("w-8 shrink-0 font-semibold tracking-wide", LEVEL_STYLE[line.level])}
                  >
                    {LEVEL_TAG[line.level]}
                  </span>
                  <span className={clsx("min-w-0 break-words", LEVEL_STYLE[line.level])}>{line.text}</span>
                </li>
              ))}
            </ul>
          )}
          <div className="proc-log-cursor mt-1.5 flex items-center gap-1 font-mono text-[10px] text-brand-700 dark:text-brand-400">
            <span className="opacity-70">›</span>
            <span className="proc-caret h-3 w-1.5 bg-brand-500/80 dark:bg-brand-400/70" aria-hidden />
          </div>
        </div>

        <footer className="border-t border-[color:var(--pic-border-subtle)] px-4 py-2">
          <div className="h-1 overflow-hidden rounded-full bg-stone-200/90 dark:bg-stone-800">
            <div className="transition-overlay-bar h-full rounded-full bg-brand-500/90 dark:bg-brand-400/80" />
          </div>
        </footer>
      </div>
    </div>
  );

  return createPortal(node, document.body);
}
