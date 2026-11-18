import type { AuthGateway } from "../auth/gateway";
import { networkError } from "./errors";

/**
 * fetch for the API client: adds the access token and handles 401 as spec 3.1.5 says.
 *
 * - The token is read from the session right before each request, never stored here.
 * - On 401 the session is refreshed once and the same request is sent once more with the new token.
 *   Requests that get 401 at the same time share that one refresh.
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

  async function send(request: Request): Promise<Response> {
    const token = await gateway.accessToken();
    const headers = new Headers(request.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    else headers.delete("Authorization");
    try {
      return await baseFetch(new Request(request, { headers }));
    } catch (error) {
      // A cancelled request (the screen was left) is not a network failure; let the caller see the abort.
      if (request.signal.aborted) throw error;
      throw networkError();
    }
  }

  return async (request: Request) => {
    // Keep an unread copy: the first attempt consumes the body.
    const retryCopy = request.clone();
    const response = await send(request);
    if (response.status !== 401) return response;

    if (await refreshOnce()) {
      const retried = await send(retryCopy);
      if (retried.status !== 401) return retried;
    }
    onSessionExpired();
    return response;
  };
}
