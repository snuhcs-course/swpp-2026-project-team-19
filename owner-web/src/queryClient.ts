import { QueryClient } from "@tanstack/react-query";
import { isRetryable } from "./api/errors";

/**
 * Server data for the whole app. A failed request is retried once only when retrying may help (no response,
 * or a 5xx); a 4xx answer is final. 401 is already handled by the API client (refresh and one retry).
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (failureCount, error) => failureCount < 1 && isRetryable(error),
        refetchOnWindowFocus: false,
      },
      mutations: { retry: false },
    },
  });
}
