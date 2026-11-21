import fieldStyles from "../ui/TextField.module.css";
import styles from "./bar.module.css";

interface TimeSelectProps {
  /** Names the pair, e.g. "월요일 시작"; the lists are "<label> 시" and "<label> 분". */
  label: string;
  /** "HH:MM", or null for no time yet. */
  value: string | null;
  onChange: (value: string | null) => void;
  /** Offers "설정" (no time yet) as the first hour. */
  allowUnset?: boolean;
  error?: string;
  /** Shows the label only to screen readers, for compact rows. */
  compact?: boolean;
}

const HOURS = Array.from({ length: 24 }, (_, hour) => String(hour).padStart(2, "0"));
const MINUTES = Array.from({ length: 12 }, (_, step) => String(step * 5).padStart(2, "0"));
const HOUR_OPTIONS = HOURS.map((hour) => (
  <option key={hour} value={hour}>
    {hour}시
  </option>
));
const MINUTE_OPTIONS = MINUTES.map((minute) => (
  <option key={minute} value={minute}>
    {minute}분
  </option>
));

/**
 * A time in 5-minute steps, 00:00 to 23:55 (spec 3.15.1), as an hour list and a minute list like the app's
 * time wheel (android/.../ui/owner/OwnerOperatingQuickComponents.kt `OwnerQuickTimeWheel`). Choosing an hour
 * first takes minute 00; choosing "설정" for the hour clears the time.
 */
export function TimeSelect({ label, value, onChange, allowUnset = false, error, compact = false }: TimeSelectProps) {
  const hour = value?.slice(0, 2) ?? "";
  const minute = value?.slice(3, 5) ?? "";
  return (
    <div className={compact ? styles.timePair : fieldStyles.field}>
      <span className={compact ? fieldStyles.srOnly : fieldStyles.label} aria-hidden="true">
        {label}
      </span>
      <span role="group" aria-label={label} className={styles.timeLists}>
        <select
          aria-label={`${label} 시`}
          className={fieldStyles.input}
          value={hour}
          aria-invalid={error ? true : undefined}
          onChange={(event) => {
            const next = event.currentTarget.value;
            onChange(next ? `${next}:${minute || "00"}` : null);
          }}
        >
          {allowUnset ? <option value="">설정</option> : null}
          {HOUR_OPTIONS}
        </select>
        <select
          aria-label={`${label} 분`}
          className={fieldStyles.input}
          value={minute}
          disabled={hour === ""}
          aria-invalid={error ? true : undefined}
          onChange={(event) => onChange(`${hour}:${event.currentTarget.value}`)}
        >
          {hour === "" ? <option value="">--</option> : null}
          {MINUTE_OPTIONS}
        </select>
      </span>
      {error ? (
        <p className={fieldStyles.error} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
