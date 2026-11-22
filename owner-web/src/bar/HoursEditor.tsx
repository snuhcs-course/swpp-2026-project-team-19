import { memo } from "react";
import { Button } from "../ui/Button";
import { TimeSelect } from "./TimeSelect";
import { copyMondayToWeekdays, endsNextDay, toggleDayClosed, withDay, WEEKDAYS, type DayDraft } from "./weeklyHours";
import styles from "./bar.module.css";

interface HoursEditorProps {
  hours: DayDraft[];
  onChange: (hours: DayDraft[]) => void;
  /** The form's message for the whole list (`weeklyHoursError`). */
  error?: string;
  /** The server's messages by weekday (from `weeklyHours[i]` field errors). */
  dayErrors: Partial<Record<number, string>>;
}

/**
 * The regular hours rows of android/.../ui/owner/OwnerInfoHtmlV4Screen.kt: per weekday "휴무", the opening
 * and closing times, and "평일에 복사". "익일" is shown when the closing time is earlier (spec 3.15.1).
 *
 * Memoized: its 14 time lists hold about 4,000 options, which should not be drawn again on every key typed
 * in the form's other fields.
 */
export const HoursEditor = memo(function HoursEditor({ hours, onChange, error, dayErrors }: HoursEditorProps) {
  return (
    <section className={styles.section} aria-labelledby="bar-hours-title">
      <div className={styles.sectionHead}>
        <h2 id="bar-hours-title" className={styles.sectionTitle}>
          정규 영업시간
        </h2>
        <Button variant="text" onClick={() => onChange(copyMondayToWeekdays(hours))}>
          평일에 복사
        </Button>
      </div>
      <p className={styles.hint}>비워 둔 요일은 영업시간 정보 없음으로 보여요.</p>
      <ul className={styles.hoursList}>
        {WEEKDAYS.map((name, index) => {
          const dayOfWeek = index + 1;
          const setting = hours.find((day) => day.dayOfWeek === dayOfWeek);
          const set = (value: DayDraft | null) => onChange(withDay(hours, dayOfWeek, value));
          const times = setting ?? { dayOfWeek, closed: false, open: null, close: null };
          return (
            <li key={dayOfWeek} className={styles.hoursRow} aria-label={`${name}요일`}>
              <span className={styles.dayName}>{name}</span>
              <label className={styles.check}>
                <input
                  type="checkbox"
                  checked={setting?.closed === true}
                  onChange={(event) => set(toggleDayClosed(setting, dayOfWeek, event.currentTarget.checked))}
                />
                휴무
              </label>
              {setting?.closed ? null : (
                <span className={styles.times}>
                  <TimeSelect
                    compact
                    allowUnset
                    label={`${name}요일 시작`}
                    value={times.open}
                    onChange={(open) => set({ ...times, open })}
                  />
                  <span aria-hidden="true">–</span>
                  <TimeSelect
                    compact
                    allowUnset
                    label={`${name}요일 종료`}
                    value={times.close}
                    onChange={(close) => set({ ...times, close })}
                  />
                  {endsNextDay(times) ? <span className={styles.nextDay}>익일</span> : null}
                </span>
              )}
              {dayErrors[dayOfWeek] ? (
                <p className={[styles.error, styles.dayError].join(" ")} role="alert">
                  {dayErrors[dayOfWeek]}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
});
