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

/**
 * Adds `applicationId` to `current` (what the screen hides now) and returns the new set. It builds on
 * `current`, not on storage, so earlier cards stay hidden for this visit when storage fails.
 */
export function hideApplication(userId: string, applicationId: string, current: ReadonlySet<string>): ReadonlySet<string> {
  const next = new Set([...loadHiddenApplications(userId), ...current]);
  next.add(applicationId);
  try {
    localStorage.setItem(keyFor(userId), JSON.stringify([...next]));
  } catch {
    // Not kept (private mode, full or blocked storage): the card is hidden until the page is left.
  }
  return next;
}
