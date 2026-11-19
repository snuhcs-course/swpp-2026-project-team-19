import type { AuthGateway } from "../auth/gateway";

/** Stands in for Supabase in tests: tests never call Supabase (AGENTS.md). */
export class FakeGateway implements AuthGateway {
  configured = true;
  signedIn: boolean;
  token: string;
  userId: string;
  /** What the next refreshSession returns, and the token it sets on success. */
  refreshSucceeds = true;
  refreshedToken = "refreshed-token";
  calls = { refresh: 0, signIn: [] as string[], signOut: 0 };
  private listeners = new Set<(userId: string | null) => void>();

  constructor({ signedIn = true, token = "access-token", userId = "user-a" }: { signedIn?: boolean; token?: string; userId?: string } = {}) {
    this.signedIn = signedIn;
    this.token = token;
    this.userId = userId;
  }

  restoreSession = async () => (this.signedIn ? this.userId : null);
  currentSession = async () => (this.signedIn ? { accessToken: this.token, userId: this.userId } : null);
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
    this.notify(null);
  };
  onSessionChange = (listener: (userId: string | null) => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  /** Simulates the session ending elsewhere (another tab signed out, the refresh token was revoked). */
  endElsewhere() {
    this.signedIn = false;
    this.notify(null);
  }

  /** Simulates another tab of the same origin signing in as a different account, without a sign-out here. */
  switchAccount(userId: string, token: string) {
    this.signedIn = true;
    this.userId = userId;
    this.token = token;
    this.notify(userId);
  }

  private notify(userId: string | null) {
    for (const listener of this.listeners) listener(userId);
  }
}
