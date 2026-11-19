import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createAuthFetch } from "../api/authFetch";
import { createApiClient, type ApiClient } from "../api/client";
import type { AuthGateway } from "./gateway";
import { saveReturnPath } from "./returnPath";

export type SessionStatus = "restoring" | "signedOut" | "signedIn";

export interface Session {
  status: SessionStatus;
  /** False when the server has no Google sign-in settings. */
  configured: boolean;
  /** Why the owner is on the sign-in screen (an expired session, a failed sign-in), if there is a reason. */
  notice: string | null;
  api: ApiClient;
  /** Leaves for Google sign-in; the owner comes back to `returnPath` (a path inside the app). */
  signIn(returnPath?: string): Promise<void>;
  signOut(): Promise<void>;
}

const SessionContext = createContext<Session | null>(null);

export const SESSION_EXPIRED_NOTICE = "로그인이 만료되었어요. 다시 로그인해 주세요.";
export const SIGN_IN_FAILED_NOTICE = "Google 로그인을 마치지 못했어요. 다시 시도해 주세요.";
export const SIGN_IN_START_FAILED_NOTICE = "Google 로그인을 시작하지 못했어요. 잠시 후 다시 시도해 주세요.";

// What a sign-in redirect leaves in the URL: the PKCE code, or an error from Supabase or Google.
const REDIRECT_PARAMS = ["code", "state", "error", "error_code", "error_description"];

/** Removes the sign-in redirect's parameters from the address bar; returns whether it carried an error. */
function clearRedirectParams(): boolean {
  const url = new URL(window.location.href);
  const failed = url.searchParams.has("error");
  if (!REDIRECT_PARAMS.some((name) => url.searchParams.has(name))) return false;
  for (const name of REDIRECT_PARAMS) url.searchParams.delete(name);
  window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
  return failed;
}

/**
 * The owner's session and the API client that carries it. Signing out, a session that ends (spec 3.1.5), or
 * another account signing in from another tab clears every cached server response, so nothing of one account
 * is shown to the next.
 */
export function SessionProvider({ gateway, children }: { gateway: AuthGateway; children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<SessionStatus>("restoring");
  const [notice, setNotice] = useState<string | null>(null);
  // Whose data the cache holds, to notice another account signing in without a sign-out here.
  const userId = useRef<string | null>(null);

  const endSession = useCallback(
    (reason: string | null) => {
      userId.current = null;
      queryClient.clear();
      setNotice(reason);
      setStatus("signedOut");
    },
    [queryClient],
  );

  // The API client lives as long as the gateway; expiry is reported through a ref to the latest handler.
  const onExpired = useRef<() => void>(() => undefined);
  useEffect(() => {
    onExpired.current = () => {
      endSession(SESSION_EXPIRED_NOTICE);
      void gateway.signOut();
    };
  }, [gateway, endSession]);
  const api = useMemo(() => createApiClient(createAuthFetch(gateway, () => onExpired.current())), [gateway]);

  useEffect(() => {
    let active = true;
    gateway
      .restoreSession()
      .catch(() => null)
      .then((restored) => {
        if (!active) return;
        const failed = clearRedirectParams();
        if (restored) {
          userId.current = restored;
          setStatus("signedIn");
        } else {
          setNotice(failed ? SIGN_IN_FAILED_NOTICE : null);
          setStatus("signedOut");
        }
      });
    const unsubscribe = gateway.onSessionChange((signedInAs) => {
      if (!active) return;
      if (signedInAs) {
        if (userId.current !== null && userId.current !== signedInAs) {
          // Another tab signed in as someone else: drop the previous account's data, cancel its requests,
          // and load the screen again for the new account.
          void queryClient.cancelQueries().then(() => queryClient.resetQueries());
        }
        userId.current = signedInAs;
        setStatus("signedIn");
        return;
      }
      // Our own sign-outs end in this event too (Supabase sends SIGNED_OUT for a local sign-out), after the
      // screen already has its reason, such as an expired session. Keep that reason; only the data goes.
      userId.current = null;
      queryClient.clear();
      setStatus("signedOut");
    });
    return () => {
      active = false;
      unsubscribe();
    };
  }, [gateway, queryClient]);

  const signIn = useCallback(
    async (returnPath?: string) => {
      if (returnPath) saveReturnPath(returnPath);
      setNotice(null);
      try {
        await gateway.signInWithGoogle(`${window.location.origin}/owner/`);
      } catch {
        setNotice(SIGN_IN_START_FAILED_NOTICE);
      }
    },
    [gateway],
  );

  const signOut = useCallback(async () => {
    await gateway.signOut();
    endSession(null);
  }, [gateway, endSession]);

  const value = useMemo<Session>(
    () => ({ status, configured: gateway.configured, notice, api, signIn, signOut }),
    [status, gateway.configured, notice, api, signIn, signOut],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession must be used inside SessionProvider.");
  return session;
}
