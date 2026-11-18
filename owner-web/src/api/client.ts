import createClient from "openapi-fetch";
import { apiErrorFrom } from "./errors";
import type { paths } from "./schema";

/** The typed API client: paths, parameters and bodies come from src/api/schema.d.ts (`npm run gen:api`). */
export function createApiClient(fetchWithAuth: (request: Request) => Promise<Response>) {
  // The page's own origin: the API serves /owner/, so /api is on the same server. Never a fixed URL.
  return createClient<paths>({ baseUrl: window.location.origin, fetch: fetchWithAuth });
}

export type ApiClient = ReturnType<typeof createApiClient>;

/** The data of a successful call (undefined for 204), or the ApiError of a failed one. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.response.ok) return result.data as T;
  throw apiErrorFrom(result.response, result.error);
}
