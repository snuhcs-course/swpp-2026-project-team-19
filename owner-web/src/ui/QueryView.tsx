import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { ApiError, errorMessage } from "../api/errors";
import { Button } from "./Button";
import { ErrorState, LoadingState } from "./states";
import styles from "./states.module.css";

interface QueryViewProps<T> {
  query: Pick<UseQueryResult<T>, "data" | "error" | "isPending" | "isError" | "isFetching" | "refetch">;
  /** When the data counts as empty, `empty` is shown instead of `children`. */
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  loadingMessage?: string;
  /**
   * When a refetch fails after data arrived, keep showing that data under a small notice instead of the error
   * screen. For screens that hold unsaved input, which the error screen would throw away.
   */
  keepDataOnRefetchError?: boolean;
  children: (data: T) => ReactNode;
}

/**
 * The five states every screen that loads data handles (AGENTS.md): loading, success, empty, error, retry.
 * A permission answer (403) offers no retry, since asking again cannot change it (spec 3.1.5).
 */
export function QueryView<T>({ query, isEmpty, empty, loadingMessage, keepDataOnRefetchError = false, children }: QueryViewProps<T>) {
  if (query.isPending) return <LoadingState message={loadingMessage} />;
  const refetchFailed = query.isError && keepDataOnRefetchError && query.data !== undefined;
  if (query.isError && !refetchFailed) {
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
  // The notice takes the same place whether shown or not, so the content keeps its state (and any unsaved
  // input) when a refetch fails or recovers.
  const notice = refetchFailed ? (
    <RefetchErrorNotice error={query.error} retrying={query.isFetching} onRetry={() => void query.refetch()} />
  ) : null;
  if (isEmpty?.(data)) return <>{notice}{empty ?? null}</>;
  return (
    <>
      {notice}
      {children(data)}
    </>
  );
}

/** A refetch that failed while the earlier data stays on screen; retry unless it was a 403 (spec 3.1.5). */
function RefetchErrorNotice({ error, retrying, onRetry }: { error: unknown; retrying: boolean; onRetry: () => void }) {
  const forbidden = error instanceof ApiError && error.status === 403;
  return (
    <div className={styles.refetchError} role="alert">
      <p className={styles.refetchMessage}>최신 정보를 불러오지 못했어요. {errorMessage(error)}</p>
      {forbidden ? null : (
        <Button variant="text" busy={retrying} onClick={onRetry}>
          다시 시도
        </Button>
      )}
    </div>
  );
}
