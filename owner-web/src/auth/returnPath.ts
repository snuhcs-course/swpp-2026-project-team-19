/**
 * Where to go after Google sign-in. The sign-in leaves the page, and Supabase always returns to /owner/
 * (one registered Redirect URL), so the page the owner wanted is kept in sessionStorage meanwhile.
 * Storage may be unavailable (private mode, blocked site data): then the owner simply starts at /owner/.
 */
const KEY = "bottlemap-owner-web-return-path";

/** Only a path inside the app ("/bars/1"), never another origin ("//evil.example") or the sign-in page. */
export function isSafeReturnPath(path: unknown): path is string {
  return typeof path === "string" && path.startsWith("/") && !path.startsWith("//") && !path.startsWith("/\\") && path !== "/login";
}

export function saveReturnPath(path: string): void {
  if (!isSafeReturnPath(path)) return;
  try {
    sessionStorage.setItem(KEY, path);
  } catch {
    // Not kept: the owner starts at /owner/.
  }
}

export function takeReturnPath(): string | null {
  try {
    const path = sessionStorage.getItem(KEY);
    sessionStorage.removeItem(KEY);
    return isSafeReturnPath(path) ? path : null;
  } catch {
    return null;
  }
}
