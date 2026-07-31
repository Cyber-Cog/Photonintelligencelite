/**
 * Pure helpers for Analysis Console progress classification.
 * Kept free of React so behavior is easy to reason about / mirror in backend tests.
 */

export type IntegrityProgressLevel = "info" | "ok" | "run" | "wait" | "warn";

export function classifyIntegrityProgressMessage(
  progressMessage: string,
): { show: true; level: IntegrityProgressLevel } | { show: false } {
  if (/^AI integrity check starting/i.test(progressMessage)) {
    return { show: true, level: "run" };
  }
  if (
    /^AI integrity\b/i.test(progressMessage) ||
    /^Analysis complete\s*·\s*AI integrity/i.test(progressMessage)
  ) {
    const failed = /failed|rejected/i.test(progressMessage);
    const soft = /skipped|not configured/i.test(progressMessage);
    return { show: true, level: failed ? "warn" : soft ? "info" : "ok" };
  }
  return { show: false };
}
