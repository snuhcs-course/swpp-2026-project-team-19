/**
 * The sign-in provider behind the owner web (Supabase Google login in production, a fake in tests), like the
 * Android app's AuthGateway (android/.../data/AuthRepository.kt). Nothing else talks to Supabase.
 */
export interface AuthGateway {
  /** False when the server hands out no Supabase settings (/owner/config.js); sign-in is then impossible. */
  readonly configured: boolean;
  /** Finishes a sign-in redirect if the URL carries one, then reports whether a session is stored. */
  restoreSession(): Promise<boolean>;
  /** The current access token, read right before each request; the SDK refreshes it ahead of expiry. */
  accessToken(): Promise<string | null>;
  /** Refreshes the session after a 401; false when the refresh token is no longer valid. */
  refreshSession(): Promise<boolean>;
  /** Leaves for Google sign-in and comes back to `redirectTo`. */
  signInWithGoogle(redirectTo: string): Promise<void>;
  /** Drops the stored session, even when the provider cannot be reached. */
  signOut(): Promise<void>;
  /** Calls back when the session ends or starts elsewhere (another tab, an expired refresh token). */
  onSessionChange(listener: (signedIn: boolean) => void): () => void;
}
