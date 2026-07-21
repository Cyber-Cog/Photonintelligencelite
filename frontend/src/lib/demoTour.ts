/** Demo walkthrough persistence — account flag when logged in; localStorage for anonymous. */

export const DEMO_TOUR_DONE_KEY = "pic_demo_tour_done";
export const DEMO_TOUR_PENDING_KEY = "pic_demo_tour_pending";

export function isAnonymousTourDone(): boolean {
  try {
    return localStorage.getItem(DEMO_TOUR_DONE_KEY) === "1";
  } catch {
    return false;
  }
}

export function markAnonymousTourDone(): void {
  try {
    localStorage.setItem(DEMO_TOUR_DONE_KEY, "1");
  } catch {
    // ignore quota / private mode
  }
}

export function clearAnonymousTourDone(): void {
  try {
    localStorage.removeItem(DEMO_TOUR_DONE_KEY);
  } catch {
    // ignore
  }
}

export function setTourPending(jobId: string): void {
  try {
    sessionStorage.setItem(DEMO_TOUR_PENDING_KEY, jobId);
  } catch {
    // ignore
  }
}

export function getTourPendingJobId(): string | null {
  try {
    return sessionStorage.getItem(DEMO_TOUR_PENDING_KEY);
  } catch {
    return null;
  }
}

export function clearTourPending(): void {
  try {
    sessionStorage.removeItem(DEMO_TOUR_PENDING_KEY);
  } catch {
    // ignore
  }
}

/** Whether this user/device has already finished the tour. */
export function isTourCompleted(tourCompletedAt: string | null | undefined, loggedIn: boolean): boolean {
  if (loggedIn) return Boolean(tourCompletedAt);
  return isAnonymousTourDone();
}
