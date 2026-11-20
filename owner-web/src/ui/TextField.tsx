import { useId, type ComponentProps } from "react";
import styles from "./TextField.module.css";

interface TextFieldProps extends Omit<ComponentProps<"input">, "id"> {
  label: string;
  /** A hint under the field, shown while there is no error. */
  hint?: string;
  /** The field's error, e.g. from fieldErrorMessages(error)[path]. */
  error?: string;
}

/** A labelled input (android/.../ui/owner/OwnerV4Visual.kt V4FormField), with its hint or error announced. */
export function TextField({ label, hint, error, className, ...rest }: TextFieldProps) {
  const id = useId();
  const messageId = `${id}-message`;
  const message = error ?? hint;
  return (
    <div className={[styles.field, className].filter(Boolean).join(" ")}>
      <label className={styles.label} htmlFor={id}>
        {label}
      </label>
      <input
        {...rest}
        id={id}
        className={styles.input}
        aria-invalid={error ? true : undefined}
        aria-describedby={message ? messageId : undefined}
      />
      {message ? (
        <p id={messageId} className={error ? styles.error : styles.hint} role={error ? "alert" : undefined}>
          {message}
        </p>
      ) : null}
    </div>
  );
}
