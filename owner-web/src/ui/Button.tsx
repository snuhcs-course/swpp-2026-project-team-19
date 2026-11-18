import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router";
import styles from "./Button.module.css";

type Variant = "primary" | "secondary" | "text";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  /** Shows that the action is running and blocks a second press. */
  busy?: boolean;
}

/** The app's buttons (android/.../ui/common/MinimalUxKit.kt UxMainButton): primary 56px, others 48px high. */
export function Button({ variant = "primary", busy = false, disabled, className, children, type, ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      type={type ?? "button"}
      className={[styles.button, styles[variant], className].filter(Boolean).join(" ")}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
    >
      {busy ? <span className={styles.spinner} aria-hidden="true" /> : null}
      {children}
    </button>
  );
}

/** A link that looks like a button, for moving to another screen (a <button> inside a link is invalid HTML). */
export function ButtonLink({ to, variant = "secondary", children }: { to: string; variant?: Variant; children: ReactNode }) {
  return (
    <Link to={to} className={[styles.button, styles[variant]].join(" ")}>
      {children}
    </Link>
  );
}
