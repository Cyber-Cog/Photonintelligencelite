import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { TourStepDef } from "./tourSteps";

const PAD = 12;
const CARD_W = 400;
const CARD_H_EST = 260;

type Rect = { top: number; left: number; width: number; height: number };

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function measure(el: Element | null): Rect | null {
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (r.width < 2 && r.height < 2) return null;
  return {
    top: r.top,
    left: r.left,
    width: r.width,
    height: r.height,
  };
}

function placeCard(
  hole: Rect | null,
  placement: TourStepDef["placement"],
  cardH: number,
): { top: number; left: number } {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const margin = 16;

  if (!hole || placement === "center") {
    return {
      top: clamp(vh / 2 - cardH / 2, margin, vh - cardH - margin),
      left: clamp(vw / 2 - CARD_W / 2, margin, vw - CARD_W - margin),
    };
  }

  const prefer =
    placement && placement !== "auto"
      ? placement
      : hole.top > vh * 0.55
        ? "top"
        : hole.top + hole.height < vh * 0.4
          ? "bottom"
          : "bottom";

  let top = hole.top + hole.height + PAD + 10;
  let left = hole.left + hole.width / 2 - CARD_W / 2;

  if (prefer === "top") {
    top = hole.top - cardH - PAD - 10;
  } else if (prefer === "left") {
    top = hole.top + hole.height / 2 - cardH / 2;
    left = hole.left - CARD_W - PAD - 10;
  } else if (prefer === "right") {
    top = hole.top + hole.height / 2 - cardH / 2;
    left = hole.left + hole.width + PAD + 10;
  }

  if (top + cardH > vh - margin) top = hole.top - cardH - PAD - 10;
  if (top < margin) top = hole.top + hole.height + PAD + 10;
  if (left < margin) left = margin;
  if (left + CARD_W > vw - margin) left = vw - CARD_W - margin;

  return {
    top: clamp(top, margin, vh - cardH - margin),
    left: clamp(left, margin, vw - CARD_W - margin),
  };
}

export function TourOverlay({
  step,
  stepIndex,
  stepCount,
  onNext,
  onBack,
  onSkip,
  onTargetMissing,
}: {
  step: TourStepDef;
  stepIndex: number;
  stepCount: number;
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
  /** Called once when a selector was expected but the target is gone after settle. */
  onTargetMissing?: () => void;
}) {
  const [hole, setHole] = useState<Rect | null>(null);
  const [cardPos, setCardPos] = useState({ top: 80, left: 24 });
  const [ready, setReady] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const missingNotified = useRef(false);
  const isLast = stepIndex >= stepCount - 1;
  const isFirst = stepIndex <= 0;

  const applyMeasure = useCallback(() => {
    const el = step.selector ? document.querySelector(step.selector) : null;
    const next = measure(el);
    const cardH = cardRef.current?.offsetHeight || CARD_H_EST;
    setHole(next);
    setCardPos(placeCard(next, step.placement, cardH));
    setReady(true);

    if (step.selector && !next && !missingNotified.current) {
      missingNotified.current = true;
      onTargetMissing?.();
    }
  }, [step.selector, step.placement, onTargetMissing]);

  // Measure once per step — single rAF after paint. No per-frame layout reads.
  useLayoutEffect(() => {
    missingNotified.current = false;
    setReady(false);
    setHole(null);
    const id = requestAnimationFrame(() => {
      applyMeasure();
    });
    return () => cancelAnimationFrame(id);
  }, [applyMeasure, step.id]);

  // Resize only (throttled). Do NOT listen to scroll — body is locked during the tour.
  useEffect(() => {
    let raf = 0;
    const onResize = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        applyMeasure();
      });
    };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [applyMeasure]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onSkip();
      } else if (e.key === "ArrowRight" || e.key === "Enter") {
        e.preventDefault();
        onNext();
      } else if (e.key === "ArrowLeft" && !isFirst) {
        e.preventDefault();
        onBack();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onNext, onBack, onSkip, isFirst]);

  const cutout = useMemo(() => {
    if (!hole) return null;
    return {
      top: Math.max(0, hole.top - PAD),
      left: Math.max(0, hole.left - PAD),
      width: hole.width + PAD * 2,
      height: hole.height + PAD * 2,
    };
  }, [hole]);

  const dots = useMemo(() => Array.from({ length: stepCount }, (_, i) => i), [stepCount]);
  const reduced = prefersReducedMotion();

  const node = (
    <div
      className={`tour-root ${ready ? "tour-root-ready" : ""} ${reduced ? "tour-reduced" : ""}`}
      role="dialog"
      aria-modal="true"
      aria-labelledby="tour-title"
      aria-describedby="tour-body"
    >
      {/* Cutout dim via 4 opaque pads — no 9999px box-shadow, no backdrop-filter */}
      {cutout ? (
        <>
          <div className="tour-pad tour-pad-dim" style={{ top: 0, left: 0, right: 0, height: cutout.top }} aria-hidden />
          <div
            className="tour-pad tour-pad-dim"
            style={{
              top: cutout.top + cutout.height,
              left: 0,
              right: 0,
              bottom: 0,
            }}
            aria-hidden
          />
          <div
            className="tour-pad tour-pad-dim"
            style={{
              top: cutout.top,
              left: 0,
              width: cutout.left,
              height: cutout.height,
            }}
            aria-hidden
          />
          <div
            className="tour-pad tour-pad-dim"
            style={{
              top: cutout.top,
              left: cutout.left + cutout.width,
              right: 0,
              height: cutout.height,
            }}
            aria-hidden
          />
          <div
            className={`tour-spotlight-ring ${step.allowInteract ? "tour-spotlight-live" : ""}`}
            style={{
              top: cutout.top,
              left: cutout.left,
              width: cutout.width,
              height: cutout.height,
            }}
            aria-hidden
          />
          {!step.allowInteract ? (
            <div
              className="tour-hole-block"
              style={{
                top: cutout.top,
                left: cutout.left,
                width: cutout.width,
                height: cutout.height,
              }}
              aria-hidden
            />
          ) : null}
        </>
      ) : (
        <div className="tour-dim" aria-hidden />
      )}

      <div
        ref={cardRef}
        className="tour-card"
        style={{
          top: cardPos.top,
          left: cardPos.left,
          width: Math.min(CARD_W, window.innerWidth - 32),
        }}
      >
        <div className="tour-card-inner">
          <div className="flex items-center justify-between gap-2">
            <p className="tour-eyebrow">
              Demo tour · {stepIndex + 1}/{stepCount}
            </p>
            <button type="button" className="tour-skip" onClick={onSkip}>
              Skip
            </button>
          </div>

          <h2 id="tour-title" className="tour-title">
            {step.title}
          </h2>
          <p id="tour-body" className="tour-body">
            {step.body}
          </p>

          <div className="tour-dots" role="tablist" aria-label="Tour progress">
            {dots.map((i) => (
              <span
                key={i}
                className={`tour-dot ${i === stepIndex ? "tour-dot-active" : i < stepIndex ? "tour-dot-done" : ""}`}
                aria-hidden
              />
            ))}
          </div>

          <div className="tour-actions">
            {!isFirst ? (
              <button type="button" className="tour-btn-ghost" onClick={onBack}>
                Back
              </button>
            ) : (
              <span />
            )}
            <button type="button" className="tour-btn-next" onClick={onNext} autoFocus>
              {isLast ? "Finish" : "Next"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  return createPortal(node, document.body);
}
