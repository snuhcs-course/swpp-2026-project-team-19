import type { components } from "../api/schema";
import { addDays, epochDay, minutesOf, monthDay, seoulClock, weekdayOf } from "./seoulTime";

/**
 * Whether a bar is open now and what its temporary closure is, computed in the browser as the server sends
 * no open status (spec 3.15.4, 3.15.5). Ported from the Android app so both show the same words for the same
 * data:
 * - android/.../ui/owner/OwnerManagementHomeState.kt: `homeOperatingException`, `homeExceptionHeading`,
 *   `registrationOperatingLabel`, `homeOperatingState`, `ownerQuickApplyDay`, `validQuickVacationAtApply`.
 * - android/.../ui/owner/OwnerPreviewV4Status.kt: `ownerPreviewNextText`.
 *
 * Where the app and the spec differ, the spec is followed (recorded in data/android 수정 필요 사항.md):
 * - A time range ends the next day when `closeTime < openTime` (3.15.1), for the closure's own hours too.
 *   The app keeps a separate flag that it does not set for a closure read from the server.
 * - A weekday missing from `weeklyHours` is "영업시간 정보 없음" even when other days are set (3.15.5).
 * - A vacation not started yet is "임시 휴업 예정" on the home card (3.15.4).
 */
export type WeeklyHours = components["schemas"]["WeeklyHours"];
export type OperatingException = components["schemas"]["OperatingException"];

export interface Schedule {
  weeklyHours: readonly WeeklyHours[];
  operatingException: OperatingException | null;
}

export type OperatingState = "영업 중" | "영업 종료" | "임시 휴무" | "영업시간 정보 없음";

interface Range {
  open: number;
  close: number;
  /** Ends the next day (spec 3.15.1: `closeTime < openTime`). */
  overnight: boolean;
}

function rangeOf(open: string | null | undefined, close: string | null | undefined): Range | null {
  const from = minutesOf(open);
  const to = minutesOf(close);
  if (from === null || to === null) return null;
  return { open: from, close: to, overnight: to < from };
}

const covers = (exception: OperatingException, date: string) =>
  epochDay(exception.startDate) <= epochDay(date) && epochDay(date) <= epochDay(exception.endDate);

const isClosure = (exception: OperatingException | null | undefined) =>
  exception?.kind === "closed_today" || exception?.kind === "vacation";

const regularOf = (schedule: Schedule, weekday: number) => schedule.weeklyHours.find((day) => day.dayOfWeek === weekday);

const regularRange = (day: WeeklyHours | undefined) => (day && !day.closed ? rangeOf(day.openTime, day.closeTime) : null);

/**
 * The closure to show on the home card (`homeOperatingException`): one covering today, yesterday's
 * overnight changed hours until they end this morning, or a vacation still to come.
 */
export function homeOperatingException(schedule: Schedule, now: number): OperatingException | null {
  const exception = schedule.operatingException;
  if (!exception) return null;
  const { date, minute } = seoulClock(now);
  if (covers(exception, date)) return exception;
  if (exception.kind === "custom_hours" && exception.endDate === addDays(date, -1)) {
    const range = rangeOf(exception.openTime, exception.closeTime);
    if (range?.overnight && minute < range.close) return exception;
  }
  if (exception.kind === "vacation" && epochDay(exception.startDate) > epochDay(date)) return exception;
  return null;
}

/** `homeExceptionHeading`: the closure's heading, or "정상 영업". */
export function homeExceptionHeading(exception: OperatingException | null): string {
  switch (exception?.kind) {
    case "closed_today":
      return "오늘 임시 휴무";
    case "custom_hours":
      return "오늘 영업시간 변경";
    case "vacation":
      return `${monthDay(exception.startDate)} ~\n${monthDay(exception.endDate)}\n임시 휴업`;
    default:
      return "정상 영업";
  }
}

/** `registrationOperatingLabel`: a vacation not started yet is "임시 휴업 예정", not a closure already. */
export function registrationOperatingLabel(exception: OperatingException | null, now: number): string {
  if (exception?.kind === "vacation") {
    return epochDay(exception.startDate) > epochDay(seoulClock(now).date) ? "임시 휴업 예정" : "임시 휴무";
  }
  return homeExceptionHeading(exception);
}

/**
 * The home card's title. The app shows a vacation as "임시 휴무" (OwnerManagementHomeScreen.kt); one not
 * started yet is "임시 휴업 예정" here, as `registrationOperatingLabel` and spec 3.15.4 say.
 */
export const homeStatusTitle = (exception: OperatingException | null, now: number): string =>
  exception?.kind === "vacation" ? registrationOperatingLabel(exception, now) : homeExceptionHeading(exception);

/** The home card's second line (OwnerManagementHomeScreen.kt `statusDetail`). */
export function homeStatusDetail(exception: OperatingException | null): string | null {
  if (exception?.kind === "vacation") return `${monthDay(exception.startDate)} ~ ${monthDay(exception.endDate)}`;
  if (exception?.kind === "custom_hours") {
    const range = rangeOf(exception.openTime, exception.closeTime);
    if (!range) return null;
    return `${exception.openTime} ~ ${range.overnight ? "익일 " : ""}${exception.closeTime}`;
  }
  return null;
}

/** `homeOperatingState`, which follows spec 3.15.5 step by step. */
export function homeOperatingState(schedule: Schedule, now: number): OperatingState {
  const { date, minute, weekday } = seoulClock(now);
  const yesterday = addDays(date, -1);
  const exception = schedule.operatingException;
  const today = exception && covers(exception, date) ? exception : null;

  // 1. A closure covering today closes the whole day, even yesterday's shift running past midnight.
  if (isClosure(today)) return "임시 휴무";

  // 2. What runs over from yesterday: a closure covering yesterday replaces that day's regular hours.
  const previous = exception && covers(exception, yesterday) ? exception : null;
  if (previous) {
    const range = previous.kind === "custom_hours" ? rangeOf(previous.openTime, previous.closeTime) : null;
    if (range?.overnight && minute < range.close) return "영업 중";
  } else {
    const range = regularRange(regularOf(schedule, weekdayOf(yesterday)));
    if (range?.overnight && minute < range.close) return "영업 중";
  }

  // 3. Today's range: today's changed hours, or today's regular hours.
  const regular = regularOf(schedule, weekday);
  const range = today?.kind === "custom_hours" ? rangeOf(today.openTime, today.closeTime) : regularRange(regular);
  if (range && range.open <= minute && (range.overnight || minute < range.close)) return "영업 중";

  // 4. No changed hours and today's weekday not set: no information, even with other days set.
  if (today?.kind !== "custom_hours" && regular === undefined) return "영업시간 정보 없음";
  return "영업 종료";
}

const closeText = (close: number, nextDay: boolean) =>
  `${nextDay ? "익일 " : ""}${String(Math.floor(close / 60)).padStart(2, "0")}:${String(close % 60).padStart(2, "0")} 종료`;

/** `ownerPreviewNextText`: when the bar closes while open, or opens later today; empty otherwise. */
export function operatingNextText(schedule: Schedule, now: number): string {
  const { date, minute, weekday } = seoulClock(now);
  const state = homeOperatingState(schedule, now);
  const exception = schedule.operatingException;
  const today = exception && covers(exception, date) ? exception : null;
  if (isClosure(today)) return "";

  // Yesterday's closure replaces that day's regular shift, even when it did not run past midnight.
  const previous = exception && covers(exception, addDays(date, -1)) ? exception : null;
  let previousClose: number | null = null;
  if (previous?.kind === "custom_hours") {
    const range = rangeOf(previous.openTime, previous.closeTime);
    previousClose = range?.overnight ? range.close : null;
  } else if (!previous) {
    const range = regularRange(regularOf(schedule, weekdayOf(addDays(date, -1))));
    previousClose = range?.overnight ? range.close : null;
  }
  if (state === "영업 중" && previousClose !== null && minute < previousClose) return closeText(previousClose, false);

  const range = today?.kind === "custom_hours" ? rangeOf(today.openTime, today.closeTime) : regularRange(regularOf(schedule, weekday));
  if (state === "영업 중" && range) return closeText(range.close, range.overnight);
  if (range && minute < range.open) return `${String(Math.floor(range.open / 60)).padStart(2, "0")}:${String(range.open % 60).padStart(2, "0")} 시작`;
  return "";
}

/** The home card's status line: "영업 중, 익일 02:00 종료" (the state and the preview's next text). */
export function operatingLine(schedule: Schedule, now: number): string {
  const next = operatingNextText(schedule, now);
  const state = homeOperatingState(schedule, now);
  return next ? `${state}, ${next}` : state;
}

/** `ownerQuickApplyDay`: the date to send is Seoul's today when the button is pressed (spec 3.15.2). */
export const applyDate = (now: number): string => seoulClock(now).date;

/** `validQuickVacationAtApply`: a vacation starts today or later and ends on or after its start. */
export const validVacationAtApply = (startDate: string, endDate: string, today: string): boolean =>
  startDate !== "" && endDate !== "" && epochDay(startDate) >= epochDay(today) && epochDay(endDate) >= epochDay(startDate);
