import { useId, type ReactNode } from "react";
import { Link } from "react-router-dom";

const PRODUCT = "Photon Intelligence Center";
/** Shorter product name for footer and compact surfaces */
const PRODUCT_SHORT = "Photon Intelligence";

type BrandWordmarkProps = {
  /** header: compact nav; hero: landing display (text only); inline/footer: mark + name + badge */
  variant?: "header" | "hero" | "inline" | "footer";
  className?: string;
  /** When true (header), wrap in home Link */
  linkHome?: boolean;
};

function LiteBadge({ size }: { size: "sm" | "md" | "lg" }) {
  const sizeClass =
    size === "lg"
      ? "px-2.5 py-1 text-xs tracking-wide"
      : size === "md"
        ? "px-2 py-0.5 text-[10px] tracking-wide"
        : "px-1.5 py-0.5 text-[9px] tracking-wide";

  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full border border-stone-300/90 bg-stone-100/80 font-semibold text-stone-500 dark:border-stone-600 dark:bg-stone-800/80 dark:text-stone-400 ${sizeClass}`}
    >
      Lite
    </span>
  );
}

/**
 * PV panel grid + SCADA signal pulse — solar plant intelligence mark.
 * Amber cells (irradiance) + emerald telemetry on a dark field; crisp at 16px.
 */
function Mark({ compact }: { compact?: boolean }) {
  const uid = useId().replace(/:/g, "");
  const bgId = `picMarkBg-${uid}`;
  const cellId = `picMarkCell-${uid}`;
  const size = compact ? "h-8 w-8" : "h-10 w-10";
  return (
    <svg
      className={`shrink-0 ${size} rounded-lg shadow-sm shadow-brand-600/25`}
      viewBox="0 0 64 64"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <defs>
        <linearGradient id={bgId} x1="4" y1="4" x2="60" y2="60" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#292524" />
          <stop offset="100%" stopColor="#1c1917" />
        </linearGradient>
        <linearGradient id={cellId} x1="10" y1="10" x2="42" y2="48" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#fcd34d" />
          <stop offset="55%" stopColor="#f59e0b" />
          <stop offset="100%" stopColor="#d97706" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="14" fill={`url(#${bgId})`} />
      {/* Photovoltaic module — 3×2 cells (reads clean at 16px) */}
      <g fill={`url(#${cellId})`}>
        <rect x="9" y="10" width="14" height="14" rx="2" />
        <rect x="25" y="10" width="14" height="14" rx="2" />
        <rect x="41" y="10" width="14" height="14" rx="2" opacity="0.88" />
        <rect x="9" y="26" width="14" height="14" rx="2" />
        <rect x="25" y="26" width="14" height="14" rx="2" />
        <rect x="41" y="26" width="14" height="14" rx="2" opacity="0.88" />
      </g>
      {/* SCADA telemetry pulse + analytics node */}
      <path
        d="M8 52 L20 46 L30 50 L42 34 L50 40 L56 28"
        fill="none"
        stroke="#34d399"
        strokeWidth="3.25"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="56" cy="28" r="4" fill="#10b981" />
      <circle cx="56" cy="28" r="1.75" fill="#ecfdf5" />
    </svg>
  );
}

/**
 * Canonical product wordmark: “Photon Intelligence Center” primary,
 * with a quieter “Lite” suffix badge. Never split into competing display lines.
 * Hero is text-only (no Mark) so the nav mark is not duplicated in the first viewport.
 * Footer uses the shorter “Photon Intelligence” name.
 */
export function BrandWordmark({ variant = "header", className = "", linkHome = false }: BrandWordmarkProps) {
  let inner: ReactNode;

  if (variant === "hero") {
    inner = (
      <h1
        className={`landing-enter flex flex-wrap items-center gap-x-3 gap-y-2 font-display text-4xl font-bold tracking-tight text-stone-900 dark:text-stone-50 sm:text-5xl lg:text-[3.35rem] lg:leading-[1.08] ${className}`}
      >
        <span>{PRODUCT}</span>
        <LiteBadge size="lg" />
      </h1>
    );
  } else if (variant === "footer") {
    inner = (
      <span className={`inline-flex items-center gap-x-1.5 ${className}`}>
        <Mark compact />
        <span className="leading-none text-stone-500 dark:text-stone-400">{PRODUCT_SHORT}</span>
        <LiteBadge size="sm" />
      </span>
    );
  } else if (variant === "inline") {
    inner = (
      <span className={`inline-flex flex-wrap items-center gap-x-2 gap-y-1 ${className}`}>
        <Mark compact />
        <span className="font-display font-semibold tracking-tight text-stone-900 dark:text-stone-50">{PRODUCT}</span>
        <LiteBadge size="md" />
      </span>
    );
  } else {
    // header
    inner = (
      <span className={`group flex items-center gap-2.5 ${className}`}>
        <span className="transition-transform duration-300 group-hover:scale-105">
          <Mark compact />
        </span>
        <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 leading-tight">
          <span className="font-display text-sm font-semibold tracking-tight text-stone-900 dark:text-stone-50">
            {PRODUCT}
          </span>
          <LiteBadge size="sm" />
        </span>
      </span>
    );
  }

  if (linkHome) {
    return (
      <Link to="/" className="inline-flex h-full min-w-0 items-center" aria-label={`${PRODUCT} Lite`}>
        {inner}
      </Link>
    );
  }

  return inner;
}

export const PRODUCT_NAME = PRODUCT;
export const PRODUCT_NAME_SHORT = PRODUCT_SHORT;
export const PRODUCT_NAME_FULL = `${PRODUCT} Lite`;
