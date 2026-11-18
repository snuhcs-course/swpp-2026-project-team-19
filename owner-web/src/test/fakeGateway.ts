import type { AuthGateway } from "../auth/gateway";

/** Stands in for Supabase in tests: tests never call Supabase (AGENTS.md). */
export class FakeGateway implements AuthGateway {
  configured = true;
  signedIn: boolean;
  token: string;
  /** What the next refreshSession returns, and the token it sets on success. */
  refreshSucceeds = true;
  refreshedToken = "refreshed-token";
  calls = { refresh: 0, signIn: [] as string[], signOut: 0 };
  private listeners = new Set<(signedIn: boolean) => void>();

  constructor({ signedIn = true, token = "access-token" }: { signedIn?: boolean; token?: string } = {}) {
    this.signedIn = signedIn;
    this.token = token;
  }

  restoreSession = async () => this.signedIn;
  accessToken = async () => (this.signedIn ? this.token : null);
  refreshSession = async () => {
    this.calls.refresh++;
    if (this.refreshSucceeds) this.token = this.refreshedToken;
    return this.refreshSucceeds;
  };
  signInWithGoogle = async (redirectTo: string) => {
    this.calls.signIn.push(redirectTo);
  };
  // Like Supabase, whose local sign-out also sends SIGNED_OUT to every listener.
  signOut = async () => {
    this.calls.signOut++;
    this.signedIn = false;
    await Promise.resolve();
    for (const listener of this.listeners) listener(false);
  };
  onSessionChange = (listener: (signedIn: boolean) => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  /** Simulates the session ending elsewhere (another tab signed out, the refresh token was revoked). */
  endElsewhere() {
    this.signedIn = false;
    for (const listener of this.listeners) listener(false);
  }
}
