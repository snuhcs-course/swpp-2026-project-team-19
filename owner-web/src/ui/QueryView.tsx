import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { ApiError, errorMessage } from "../api/errors";
import { ErrorState, LoadingState } from "./states";

interface QueryViewProps<T> {
  query: Pick<UseQueryResult<T>, "data" | "error" | "isPending" | "isError" | "isFetching" | "refetch">;
  /** When the data counts as empty, `empty` is shown instead of `children`. */
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  loadingMessage?: string;
  children: (data: T) => ReactNode;
}

/**
 * The five states every screen that loads data handles (AGENTS.md): loading, success, empty, error, retry.
 * A permission answer (403) offers no retry, since asking again cannot change it (spec 3.1.5).
 */
export function QueryView<T>({ query, isEmpty, empty, loadingMessage, children }: QueryViewProps<T>) {
  if (query.isPending) return <LoadingState message={loadingMessage} />;
  if (query.isError) {
    const forbidden = query.error instanceof ApiError && query.error.status === 403;
    return (
      <ErrorState
        message={errorMessage(query.error)}
        onRetry={forbidden ? undefined : () => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  }
  const data = query.data as T;
  if (isEmpty?.(data)) return <>{empty ?? null}</>;
  return <>{children(data)}</>;
}
