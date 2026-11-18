/** The public settings the API hands the page in /owner/config.js (backend/app/owner_web). */
export interface OwnerWebConfig {
  supabaseUrl: string | null;
  supabasePublishableKey: string | null;
  kakaoJavascriptKey: string | null;
}

declare global {
  interface Window {
    BOTTLEMAP_OWNER_CONFIG?: Partial<OwnerWebConfig>;
  }
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

/** The settings, with `null` for each one the server did not set or the script did not load. */
export function readConfig(source: unknown = window.BOTTLEMAP_OWNER_CONFIG): OwnerWebConfig {
  const config = typeof source === "object" && source !== null ? (source as Record<string, unknown>) : {};
  return {
    supabaseUrl: text(config.supabaseUrl),
    supabasePublishableKey: text(config.supabasePublishableKey),
    kakaoJavascriptKey: text(config.kakaoJavascriptKey),
  };
}
