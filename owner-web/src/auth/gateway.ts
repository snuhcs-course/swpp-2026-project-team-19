/** The signed-in session as the API client needs it: the token to send, and whose it is. */
export interface CurrentSession {
  accessToken: string;
  /** The Supabase user id (the token's `sub`). It tells a refreshed token from another account's. */
  userId: string;
}

/**
 * The sign-in provider behind the owner web (Supabase Google login in production, a fake in tests), like the
 * Android app's AuthGateway (android/.../data/AuthRepository.kt). Nothing else talks to Supabase.
 */
export interface AuthGateway {
  /** False when the server hands out no Supabase settings (/owner/config.js); sign-in is then impossible. */
  readonly configured: boolean;
  /** Finishes a sign-in redirect if the URL carries one, then returns the stored session's user id, if any. */
  restoreSession(): Promise<string | null>;
  /** The current session, read right before each request; the SDK refreshes the token ahead of expiry. */
  currentSession(): Promise<CurrentSession | null>;
  /** Refreshes the session after a 401; false when the refresh token is no longer valid. */
  refreshSession(): Promise<boolean>;
  /** Leaves for Google sign-in and comes back to `redirectTo`. */
  signInWithGoogle(redirectTo: string): Promise<void>;
  /** Drops the stored session, even when the provider cannot be reached. */
  signOut(): Promise<void>;
  /**
   * Calls back when the session ends (null) or a user signs in (their id), including from another tab of the
   * same origin, which shares the stored session.
   */
  onSessionChange(listener: (userId: string | null) => void): () => void;
}
