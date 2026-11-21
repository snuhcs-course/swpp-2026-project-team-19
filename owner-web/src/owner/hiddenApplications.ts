/**
 * Rejected applications the owner removed from their list ("목록에서 지우기"), per account on this browser.
 * As in the app (android/.../data/owner/LocalOwnerMockRepository.kt `dismissRejectedForFixture`), this only
 * hides the card here: there is no API for it, and the application stays on the server.
 *
 * Only application IDs are kept, nothing personal, so they stay after sign-out (unlike the draft).
 */
const PREFIX = "bottlemap-owner-web-hidden-applications:";
const keyFor = (userId: string) => PREFIX + userId;

export function loadHiddenApplications(userId: string | undefined): ReadonlySet<string> {
  if (!userId) return new Set();
  try {
    const raw = localStorage.getItem(keyFor(userId));
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === "string") : []);
  } catch {
    return new Set();
  }
}

/** Adds `applicationId` and returns the new set; the set still changes for this visit when storage fails. */
export function hideApplication(userId: string, applicationId: string): ReadonlySet<string> {
  const next = new Set(loadHiddenApplications(userId));
  next.add(applicationId);
  try {
    localStorage.setItem(keyFor(userId), JSON.stringify([...next]));
  } catch {
    // Not kept (private mode, full or blocked storage): the card is hidden until the page is left.
  }
  return next;
}
