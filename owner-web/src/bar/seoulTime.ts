/**
 * Seoul local time for opening hours (spec 3.15): dates are "YYYY-MM-DD" and times "HH:MM" in Asia/Seoul,
 * never converted to UTC. "Today" is Seoul's today whatever the browser's time zone, as the app's
 * `ownerSeoulZone` (android/.../ui/owner/OwnerManagementHomeState.kt) does.
 */
export interface SeoulClock {
  /** Today in Seoul, "YYYY-MM-DD". */
  date: string;
  /** Minutes since midnight in Seoul, 0 to 1439. */
  minute: number;
  /** ISO weekday in Seoul: 1 Monday to 7 Sunday (spec 3.15.1 `dayOfWeek`). */
  weekday: number;
}

const FORMAT = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

export function seoulClock(at: number | Date = Date.now()): SeoulClock {
  const parts = Object.fromEntries(FORMAT.formatToParts(new Date(at)).map((part) => [part.type, part.value]));
  const date = `${parts.year}-${parts.month}-${parts.day}`;
  return { date, minute: Number(parts.hour) * 60 + Number(parts.minute), weekday: weekdayOf(date) };
}

/** Days since 1970-01-01 of a "YYYY-MM-DD" date (the app's `toEpochDay`). */
export function epochDay(date: string): number {
  const [year, month, day] = [Number(date.slice(0, 4)), Number(date.slice(5, 7)), Number(date.slice(8, 10))];
  return Math.round(Date.UTC(year, month - 1, day) / 86_400_000);
}

export function dateOfEpochDay(day: number): string {
  return new Date(day * 86_400_000).toISOString().slice(0, 10);
}

export const addDays = (date: string, days: number): string => dateOfEpochDay(epochDay(date) + days);

/** ISO weekday (1 Monday to 7 Sunday) of a "YYYY-MM-DD" date. */
export function weekdayOf(date: string): number {
  const sunday0 = new Date(epochDay(date) * 86_400_000).getUTCDay();
  return sunday0 === 0 ? 7 : sunday0;
}

/** Minutes since midnight of "HH:MM", or null for a missing or malformed time. */
export function minutesOf(time: string | null | undefined): number | null {
  const match = time ? /^(\d{2}):(\d{2})$/.exec(time) : null;
  if (!match) return null;
  const minutes = Number(match[1]) * 60 + Number(match[2]);
  return Number(match[1]) < 24 && Number(match[2]) < 60 ? minutes : null;
}

export const timeOf = (minutes: number): string =>
  `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;

/** "MM.dd" of a date (the app's `ownerDate`). */
export const monthDay = (date: string): string => `${date.slice(5, 7)}.${date.slice(8, 10)}`;

const SEOUL_OFFSET_MS = 9 * 60 * 60 * 1000;

/**
 * The instant Seoul's day `date` starts, as UTC RFC 3339 without fractions ("2026-11-23T15:00:00Z"), as the
 * app's `atStartOfDay(ownerManualZone).toInstant()` sends it. Seoul keeps +09:00 all year.
 */
export const seoulStartOf = (date: string): string => new Date(epochDay(date) * 86_400_000 - SEOUL_OFFSET_MS).toISOString().replace(".000Z", "Z");

/** Whether `at` falls exactly on midnight in Seoul. */
export const isSeoulMidnight = (at: number): boolean => (((at + SEOUL_OFFSET_MS) % 86_400_000) + 86_400_000) % 86_400_000 === 0;
