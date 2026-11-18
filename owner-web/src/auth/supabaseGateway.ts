import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import type { OwnerWebConfig } from "../config";
import type { AuthGateway } from "./gateway";

/**
 * The owner web keeps its own session, under its own key: the operator dashboard (/admin) is on the same
 * origin and uses supabase-js's default key, so signing in or out of one never changes the other.
 */
export const OWNER_SESSION_STORAGE_KEY = "bottlemap-owner-web-auth";

/** Supabase Google login in the browser, as the operator dashboard does it (backend/app/admin/static/app.js). */
export function createSupabaseGateway(config: OwnerWebConfig): AuthGateway {
  const client: SupabaseClient | null =
    config.supabaseUrl && config.supabasePublishableKey
      ? createClient(config.supabaseUrl, config.supabasePublishableKey, {
          auth: {
            flowType: "pkce",
            persistSession: true,
            autoRefreshToken: true,
            detectSessionInUrl: true,
            storageKey: OWNER_SESSION_STORAGE_KEY,
          },
        })
      : null;

  async function session() {
    if (!client) return null;
    const { data } = await client.auth.getSession();
    return data.session;
  }

  return {
    configured: client !== null,
    // getSession waits for supabase-js to exchange the ?code of a sign-in redirect.
    restoreSession: async () => (await session()) !== null,
    accessToken: async () => (await session())?.access_token ?? null,
    refreshSession: async () => {
      if (!client) return false;
      const { data, error } = await client.auth.refreshSession();
      return !error && data.session !== null;
    },
    signInWithGoogle: async (redirectTo) => {
      if (!client) throw new Error("Google sign-in is not configured on the server.");
      const { error } = await client.auth.signInWithOAuth({ provider: "google", options: { redirectTo } });
      if (error) throw error;
    },
    signOut: async () => {
      // Drop the stored session even when Supabase cannot be reached (spec 3.1.2).
      await client?.auth.signOut({ scope: "local" }).catch(() => undefined);
    },
    onSessionChange: (listener) => {
      if (!client) return () => undefined;
      const { data } = client.auth.onAuthStateChange((event, current) => {
        if (event === "SIGNED_OUT") listener(false);
        else if (event === "SIGNED_IN" && current) listener(true);
      });
      return () => data.subscription.unsubscribe();
    },
  };
}
