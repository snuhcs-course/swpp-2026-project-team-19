import type { AuthGateway, CurrentSession } from "../auth/gateway";
import { networkError } from "./errors";

/**
 * fetch for the API client: adds the access token and handles 401 as spec 3.1.5 says.
 *
 * - The token is read from the session right before each request, never stored here.
 * - On 401 the session is refreshed once and the same request is sent once more with the new token.
 *   Requests that get 401 at the same time share that one refresh. A 401 that arrives after another request
 *   already refreshed (it was sent with the old token) is resent with the new token without refreshing again.
 * - A request is only ever resent for the account that sent it. If the session now belongs to someone else
 *   (another tab of the same origin signed in as another account), the request is dropped: its 401 is
 *   returned, and the session is left to the new account.
 * - When the refresh fails or the retried request gets 401 again, the session is over: `onSessionExpired`
 *   signs out and shows the sign-in screen, and the 401 is returned to the caller.
 * - 403 and 503 are returned as they are: the session stays (403 is a permission answer, 503 a server outage).
 * - A request that never reaches the server throws ApiError NETWORK_ERROR; a cancelled one rethrows its abort.
 */
export function createAuthFetch(
  gateway: AuthGateway,
  onSessionExpired: () => void,
  baseFetch: typeof fetch = (input, init) => globalThis.fetch(input, init),
): (request: Request) => Promise<Response> {
  let refreshing: Promise<boolean> | null = null;

  function refreshOnce(): Promise<boolean> {
    refreshing ??= gateway
      .refreshSession()
      .catch(() => false)
      .finally(() => {
        refreshing = null;
      });
    return refreshing;
  }

  /** Sends the request with the current session's token; returns the response and the session it used. */
  async function send(request: Request): Promise<{ response: Response; session: CurrentSession | null }> {
    const session = await gateway.currentSession();
    // Copied entry by entry: jsdom's Headers constructor drops a request's own headers (such as Idempotency-Key)
    // when the request has a body; browsers copy them either way.
    const headers = new Headers([...request.headers.entries()]);
    if (session) headers.set("Authorization", `Bearer ${session.accessToken}`);
    else headers.delete("Authorization");
    try {
      return { response: await baseFetch(new Request(request, { headers })), session };
    } catch (error) {
      // A cancelled request (the screen was left) is not a network failure; let the caller see the abort.
      if (request.signal.aborted) throw error;
      throw networkError();
    }
  }

  return async (request: Request) => {
    // Keep an unread copy: the first attempt consumes the body.
    const retryCopy = request.clone();
    const { response, session: sentWith } = await send(request);
    if (response.status !== 401) return response;

    const otherAccount = (session: CurrentSession | null) =>
      sentWith !== null && session !== null && session.userId !== sentWith.userId;

    // Refresh only when the session still holds the token that was refused; a newer one means another
    // request has refreshed in the meantime, so that refresh is reused.
    const current = await gateway.currentSession();
    if (otherAccount(current)) return response;
    const refreshed =
      current !== null && current.accessToken !== sentWith?.accessToken ? true : await refreshOnce();
    if (refreshed) {
      if (otherAccount(await gateway.currentSession())) return response;
      const { response: retried } = await send(retryCopy);
      if (retried.status !== 401) return retried;
    }
    onSessionExpired();
    return response;
  };
}
