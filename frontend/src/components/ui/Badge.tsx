import clsx from "clsx";
import type { ReactNode } from "react";

type Tone = "success" | "warning" | "danger" | "info" | "neutral";

const TONE_CLASSES: Record<Tone, string> = {
  success: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  warning: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  danger: "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300",
  info: "bg-accent-100 text-accent-800 dark:bg-accent-900/40 dark:text-accent-200",
  neutral: "bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={clsx("badge", TONE_CLASSES[tone])}>{children}</span>;
}
