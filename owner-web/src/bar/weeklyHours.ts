import type { components } from "../api/schema";
import { minutesOf } from "./seoulTime";

/**
 * Editing the regular hours (spec 3.15.1), ported from android/.../ui/owner/OwnerBarEditRules.kt
 * (`toggleWeeklyDayClosed`, `validWeeklyHourDraft`, `weeklyHoursError`, `copyMondayToWeekdays`) and the hours
 * rows of OwnerInfoHtmlV4Screen.kt.
 *
 * A weekday is one of three: not set (left out of the list, "no information"), a regular day off, or open
 * from `open` to `close`. A range ends the next day when `close < open`, shown as "익일" (3.15.1); the app's
 * separate "익일" checkbox is not kept, so the times alone decide it.
 */
export type WeeklyHoursInput = components["schemas"]["WeeklyHoursInput"];

export interface DayDraft {
  dayOfWeek: number;
  closed: boolean;
  /** "HH:MM", or null while not chosen. Kept while the day is marked off, so unmarking brings them back. */
  open: string | null;
  close: string | null;
}

export const WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"] as const;

export function draftFromHours(hours: readonly components["schemas"]["WeeklyHours"][]): DayDraft[] {
  return hours
    .map((day) => ({ dayOfWeek: day.dayOfWeek, closed: day.closed, open: day.openTime, close: day.closeTime }))
    .sort((a, b) => a.dayOfWeek - b.dayOfWeek);
}

/** Sets one weekday, or leaves it out (null), keeping the list in weekday order. */
export function withDay(hours: readonly DayDraft[], day: number, value: DayDraft | null): DayDraft[] {
  // A weekday with nothing chosen is "not set", not an open day without times.
  const keep = value && (value.closed || value.open !== null || value.close !== null) ? [value] : [];
  return [...hours.filter((item) => item.dayOfWeek !== day), ...keep].sort((a, b) => a.dayOfWeek - b.dayOfWeek);
}

/**
 * `toggleWeeklyDayClosed`: marking a day off keeps its times in the draft; unmarking brings them back, and a
 * day that had none returns to not set.
 */
export function toggleDayClosed(setting: DayDraft | undefined, day: number, closed: boolean): DayDraft | null {
  if (closed) return { ...(setting ?? { dayOfWeek: day, open: null, close: null }), dayOfWeek: day, closed: true };
  if (!setting) return null;
  return setting.open !== null || setting.close !== null ? { ...setting, closed: false } : null;
}

const validTime = (time: string | null): time is string => {
  const minutes = minutesOf(time);
  return minutes !== null && minutes % 5 === 0;
};

/** `validWeeklyHourDraft`: a day off, or two different times in 5-minute steps (00:00 to 23:55). */
export function validDay(day: DayDraft): boolean {
  if (day.dayOfWeek < 1 || day.dayOfWeek > 7) return false;
  if (day.closed) return true;
  return validTime(day.open) && validTime(day.close) && day.open !== day.close;
}

/** `weeklyHoursError`, with the app's messages. */
export function weeklyHoursError(hours: readonly DayDraft[]): string | null {
  if (new Set(hours.map((day) => day.dayOfWeek)).size !== hours.length) return "같은 요일이 중복됐어요.";
  if (hours.some((day) => !validDay(day))) return "영업시간은 5분 단위이며 시작과 종료 시간이 달라야 해요.";
  return null;
}

/** Whether a range ends the next day (spec 3.15.1), for the "익일" mark. */
export function endsNextDay(day: Pick<DayDraft, "open" | "close">): boolean {
  const open = minutesOf(day.open);
  const close = minutesOf(day.close);
  return open !== null && close !== null && close < open;
}

/**
 * `copyMondayToWeekdays` ("평일에 복사"): Monday's setting to Tuesday to Friday; the weekend is kept. With
 * Monday not set, nothing changes, so drafts for Tuesday to Friday are not wiped.
 */
export function copyMondayToWeekdays(hours: readonly DayDraft[]): DayDraft[] {
  const monday = hours.find((day) => day.dayOfWeek === 1);
  if (!monday) return [...hours];
  return [
    ...hours.filter((day) => day.dayOfWeek < 2 || day.dayOfWeek > 5),
    ...[2, 3, 4, 5].map((dayOfWeek) => ({ ...monday, dayOfWeek })),
  ].sort((a, b) => a.dayOfWeek - b.dayOfWeek);
}

/** The list PATCH sends (spec 3.7, 3.15.1): weekday order, and no times on a day off (`TIME_ON_CLOSED_DAY`). */
export function hoursInput(hours: readonly DayDraft[]): WeeklyHoursInput[] {
  return [...hours]
    .sort((a, b) => a.dayOfWeek - b.dayOfWeek)
    .map((day) =>
      day.closed
        ? { dayOfWeek: day.dayOfWeek, closed: true, openTime: null, closeTime: null }
        : { dayOfWeek: day.dayOfWeek, closed: false, openTime: day.open, closeTime: day.close },
    );
}

/** Whether two settings send the same list. */
export const sameHours = (a: readonly DayDraft[], b: readonly DayDraft[]): boolean =>
  JSON.stringify(hoursInput(a)) === JSON.stringify(hoursInput(b));
