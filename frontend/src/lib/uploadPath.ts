/** Remember which Upload path the user chose (recommendation only — not a pack assumption). */

export type UploadPathChoice = "template" | "own";

const KEY_PREFIX = "pic:uploadPath:";

export function rememberUploadPath(jobId: string, path: UploadPathChoice): void {
  try {
    sessionStorage.setItem(`${KEY_PREFIX}${jobId}`, path);
  } catch {
    // ignore quota / private mode
  }
}

export function readUploadPath(jobId: string): UploadPathChoice | null {
  try {
    const v = sessionStorage.getItem(`${KEY_PREFIX}${jobId}`);
    if (v === "template" || v === "own") return v;
  } catch {
    // ignore
  }
  return null;
}
