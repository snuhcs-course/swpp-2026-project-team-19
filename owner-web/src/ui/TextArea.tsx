import { useId, type ComponentProps } from "react";
import styles from "./TextField.module.css";

interface TextAreaProps extends Omit<ComponentProps<"textarea">, "id"> {
  label: string;
  hint?: string;
  error?: string;
}

/** TextField for several lines (android/.../ui/owner/OwnerV4Visual.kt V4FormField with singleLine = false). */
export function TextArea({ label, hint, error, className, ...rest }: TextAreaProps) {
  const id = useId();
  const messageId = `${id}-message`;
  const message = error ?? hint;
  return (
    <div className={[styles.field, className].filter(Boolean).join(" ")}>
      <label className={styles.label} htmlFor={id}>
        {label}
      </label>
      <textarea
        {...rest}
        id={id}
        className={[styles.input, styles.textarea].join(" ")}
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
