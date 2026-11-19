import { useEffect, useState, type ReactNode } from "react";
import { Button } from "./Button";
import styles from "./states.module.css";

/** Android waits this long before showing a spinner (android/.../ui/common/DelayedLoading.kt), so quick loads do not flash. */
export const LOADING_FEEDBACK_DELAY_MS = 500;

export function LoadingState({ message = "불러오고 있어요." }: { message?: string }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(true), LOADING_FEEDBACK_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, []);
  return (
    <div className={styles.state} role="status" aria-live="polite" aria-busy="true">
      {visible ? (
        <>
          <span className={styles.spinner} aria-hidden="true" />
          <p className={styles.message}>{message}</p>
        </>
      ) : (
        <span className={styles.srOnly}>{message}</span>
      )}
    </div>
  );
}

export function EmptyState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className={styles.state}>
      <p className={styles.title}>{title}</p>
      {description ? <p className={styles.message}>{description}</p> : null}
      {action ? <div className={styles.action}>{action}</div> : null}
    </div>
  );
}

interface ErrorStateProps {
  message: string;
  /** Shown as a "다시 시도" button; leave it out when retrying cannot help (e.g. no permission). */
  onRetry?: () => void;
  retrying?: boolean;
  action?: ReactNode;
}

export function ErrorState({ message, onRetry, retrying = false, action }: ErrorStateProps) {
  return (
    <div className={styles.state} role="alert">
      <p className={styles.title}>{message}</p>
      {onRetry || action ? (
        <div className={styles.action}>
          {onRetry ? (
            <Button variant="secondary" onClick={onRetry} busy={retrying}>
              다시 시도
            </Button>
          ) : null}
          {action}
        </div>
      ) : null}
    </div>
  );
}
