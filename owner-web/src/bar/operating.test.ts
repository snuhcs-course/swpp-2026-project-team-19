import { afterEach, describe, expect, it } from "vitest";
import {
  applyDate,
  homeExceptionHeading,
  homeOperatingException,
  homeOperatingState,
  homeStatusDetail,
  homeStatusTitle,
  operatingLine,
  operatingNextText,
  registrationOperatingLabel,
  validVacationAtApply,
  type OperatingException,
  type Schedule,
  type WeeklyHours,
} from "./operating";
import { addDays, seoulClock } from "./seoulTime";

/** An instant at Seoul local `date` `hh:mm` (Seoul is UTC+9 all year, spec 3.15). */
function at(date: string, hour: number, minute = 0): number {
  return Date.UTC(Number(date.slice(0, 4)), Number(date.slice(5, 7)) - 1, Number(date.slice(8, 10)), hour - 9, minute);
}
const hours = (dayOfWeek: number, openTime: string | null, closeTime: string | null, closed = false): WeeklyHours => ({
  dayOfWeek,
  closed,
  openTime: closed ? null : openTime,
  closeTime: closed ? null : closeTime,
});
const closedDay = (dayOfWeek: number) => hours(dayOfWeek, null, null, true);
const exception = (kind: OperatingException["kind"], startDate: string, endDate = startDate, times: [string, string] | null = null, note: string | null = null): OperatingException => ({
  kind,
  startDate,
  endDate,
  openTime: times?.[0] ?? null,
  closeTime: times?.[1] ?? null,
  note,
});
const schedule = (weeklyHours: WeeklyHours[] = [], operatingException: OperatingException | null = null): Schedule => ({ weeklyHours, operatingException });

// Ported from android/.../ui/owner/OwnerPreviewV4StatusTest.kt (2026-11-02 is a Monday).
describe("operating status (OwnerPreviewV4Status.kt)", () => {
  const monday = "2026-11-02";

  it("shows the next-day closing next to the open status", () => {
    // showsHTMLNextDayClosingNextToGreenStatus
    const bar = schedule([hours(1, "18:00", "02:00")]);
    expect(homeOperatingState(bar, at(monday, 20))).toBe("영업 중");
    expect(operatingNextText(bar, at(monday, 20))).toBe("익일 02:00 종료");
    expect(operatingNextText(bar, at(addDays(monday, 1), 1))).toBe("02:00 종료");
    expect(operatingNextText(bar, at(monday, 17))).toBe("18:00 시작");
  });

  it("hides the next opening on a day closed today", () => {
    // todayClosedHidesNextOpeningText
    const bar = schedule([hours(1, "18:00", "22:00")], exception("closed_today", monday));
    expect(homeOperatingState(bar, at(monday, 19))).toBe("임시 휴무");
    expect(operatingNextText(bar, at(monday, 19))).toBe("");
    // A week later the closure has ended (and the server would no longer send it, spec 3.15.4).
    expect(operatingNextText(bar, at(addDays(monday, 7), 17))).toBe("18:00 시작");
  });
});

// Ported from android/.../ui/owner/OwnerManagementHomeStateTest.kt (2026-10-31 is a Saturday).
describe("home status (OwnerManagementHomeState.kt)", () => {
  const day = "2026-10-31";
  const time = (hour: number, minute = 0) => at(day, hour, minute);

  it("keeps a vacation's dates and shows one still to come", () => {
    // dateRangeIsStableAndFutureVacationIsVisibleOnHome
    const vacation = exception("vacation", addDays(day, 3), addDays(day, 6));
    const bar = schedule([], vacation);
    expect(homeOperatingException(bar, time(12))).toEqual(vacation);
    expect(homeExceptionHeading(vacation)).toContain("임시 휴업");
    expect(homeExceptionHeading(vacation)).toContain("\n");
    expect(registrationOperatingLabel(vacation, time(12))).toBe("임시 휴업 예정");
    expect(registrationOperatingLabel(vacation, at(addDays(day, 3), 12))).toBe("임시 휴무");
    expect(registrationOperatingLabel(null, time(12))).toBe("정상 영업");
    expect(homeOperatingException(bar, at(addDays(day, 8), 0))).toBeNull();
  });

  it("uses Korea time and today's closure", () => {
    // operatingStateUsesKoreaTimeAndCurrentOverride
    const bar = schedule([hours(6, "18:00", "23:00")]);
    expect(homeOperatingState(bar, time(15))).toBe("영업 종료");
    expect(homeOperatingState(bar, time(20))).toBe("영업 중");
    expect(homeOperatingState({ ...bar, operatingException: exception("closed_today", day) }, time(20))).toBe("임시 휴무");
    const custom = exception("custom_hours", day, day, ["10:00", "12:00"]);
    expect(homeOperatingState({ ...bar, operatingException: custom }, time(20))).toBe("영업 종료");
    expect(homeExceptionHeading(custom)).toBe("오늘 영업시간 변경");
  });

  it("applies changed hours on every day of the range and past midnight after the last", () => {
    // multiDayCustomHoursApplyEveryDayAndOvernightAfterFinalDay (the spec sets one day, the rule takes any)
    const bar = schedule([], exception("custom_hours", day, addDays(day, 2), ["19:00", "02:00"]));
    const on = (offset: number, hour: number) => at(addDays(day, offset), hour);
    expect(homeOperatingState(bar, on(0, 12))).toBe("영업 종료");
    expect(homeOperatingState(bar, on(0, 20))).toBe("영업 중");
    expect(homeOperatingState(bar, on(1, 1))).toBe("영업 중");
    expect(homeOperatingState(bar, on(1, 12))).toBe("영업 종료");
    expect(homeOperatingState(bar, on(1, 20))).toBe("영업 중");
    expect(homeOperatingState(bar, on(2, 20))).toBe("영업 중");
    expect(homeOperatingState(bar, on(3, 1))).toBe("영업 중");
    expect(homeOperatingState(bar, on(3, 3))).toBe("영업시간 정보 없음");
  });

  it("shows today's close time during a range of overnight changed hours", () => {
    // previewOvernightCloseTimeUsesTodayForOngoingMultiDayShift
    const bar = schedule([], exception("custom_hours", day, addDays(day, 2), ["19:00", "02:00"]));
    const on = (offset: number, hour: number) => at(addDays(day, offset), hour);
    expect(operatingNextText(bar, on(0, 20))).toBe("익일 02:00 종료");
    expect(operatingNextText(bar, on(1, 1))).toBe("02:00 종료");
    expect(operatingNextText(bar, on(2, 1))).toBe("02:00 종료");
    expect(operatingNextText(bar, on(3, 1))).toBe("02:00 종료");
    expect(operatingNextText(bar, on(2, 20))).toBe("익일 02:00 종료");
  });

  it("keeps yesterday's overnight changed hours after midnight", () => {
    // yesterdayTemporaryOvernightHoursRemainVisibleAfterMidnight
    const hoursYesterday = exception("custom_hours", addDays(day, -1), addDays(day, -1), ["19:00", "02:00"]);
    const bar = schedule([], hoursYesterday);
    expect(homeOperatingException(bar, time(1))).toEqual(hoursYesterday);
    expect(homeOperatingState(bar, time(1))).toBe("영업 중");
    expect(homeOperatingException(bar, time(3))).toBeNull();
  });

  it("does not open before tonight when yesterday was a day off", () => {
    // regularOvernightDoesNotOpenBeforeTonightWhenYesterdayWasClosed
    const bar = schedule([hours(6, "18:00", "02:00"), closedDay(5)]);
    expect(homeOperatingState(bar, time(1))).toBe("영업 종료");
    expect(homeOperatingState(bar, time(19))).toBe("영업 중");
    expect(homeOperatingState(bar, at(addDays(day, 1), 1))).toBe("영업 중");
    // Sunday is not set: after Saturday's shift ends there is no information (spec 3.15.5; the app says 영업 종료).
    expect(homeOperatingState(bar, at(addDays(day, 1), 3))).toBe("영업시간 정보 없음");
  });

  it("lets yesterday's closure replace yesterday's regular overnight shift", () => {
    // previousDayOverrideSuppressesStaleRegularOvernightShift
    const friday = addDays(day, -1);
    const base = schedule([hours(5, "18:00", "04:00"), hours(6, "19:00", "23:00")]);
    expect(homeOperatingState(base, time(1))).toBe("영업 중");

    const shortened = exception("custom_hours", friday, friday, ["18:00", "23:00"]);
    expect(homeOperatingState({ ...base, operatingException: shortened }, time(1))).toBe("영업 종료");
    expect(homeOperatingState({ ...base, operatingException: shortened }, time(20))).toBe("영업 중");
    expect(homeOperatingState({ ...base, operatingException: exception("closed_today", friday) }, time(1))).toBe("영업 종료");
    expect(homeOperatingState({ ...base, operatingException: exception("vacation", friday) }, time(1))).toBe("영업 종료");

    // Yesterday's own overnight hours end at their own close, not the regular 04:00.
    const shortenedOvernight = exception("custom_hours", friday, friday, ["18:00", "02:00"]);
    expect(homeOperatingState({ ...base, operatingException: shortenedOvernight }, time(1))).toBe("영업 중");
    expect(homeOperatingState({ ...base, operatingException: shortenedOvernight }, time(3))).toBe("영업 종료");
  });

  it("shows today's close when yesterday's regular overnight shift was replaced", () => {
    // previewUsesTodaysCloseWhenYesterdaysRegularOvernightWasOverridden
    const friday = addDays(day, -1);
    const base = schedule([hours(5, "18:00", "04:00"), hours(6, "00:00", "06:00")]);
    expect(operatingNextText(base, time(1))).toBe("04:00 종료");

    const shortFriday = exception("custom_hours", friday, friday, ["18:00", "23:00"]);
    expect(homeOperatingState({ ...base, operatingException: shortFriday }, time(1))).toBe("영업 중");
    expect(operatingNextText({ ...base, operatingException: shortFriday }, time(1))).toBe("06:00 종료");
    expect(operatingNextText({ ...base, operatingException: exception("closed_today", friday) }, time(1))).toBe("06:00 종료");
    expect(operatingNextText({ ...base, operatingException: exception("vacation", friday) }, time(1))).toBe("06:00 종료");

    const overnightFriday = exception("custom_hours", friday, friday, ["18:00", "02:00"]);
    expect(operatingNextText({ ...base, operatingException: overnightFriday }, time(1))).toBe("02:00 종료");
  });

  it("returns to the regular hours once a closure day is over", () => {
    // completedTemporaryDayReturnsToRegularSchedule
    const ended = exception("closed_today", addDays(day, -1), addDays(day, -1), null, "어제 휴무");
    const bar = schedule([hours(6, "18:00", "23:00")], ended);
    expect(homeOperatingException(bar, time(20))).toBeNull();
    expect(homeOperatingState(bar, time(20))).toBe("영업 중");
  });

  it("takes the date to send when the button is pressed, across Seoul midnight", () => {
    // applyDateIsCalculatedAtTapTimeAcrossSeoulMidnight
    const before = at(day, 23, 59);
    const after = at(addDays(day, 1), 0, 1);
    expect(applyDate(before)).toBe(day);
    expect(applyDate(after)).toBe(addDays(day, 1));
    expect(validVacationAtApply(day, addDays(day, 2), applyDate(before))).toBe(true);
    expect(validVacationAtApply(day, addDays(day, 2), applyDate(after))).toBe(false);
  });
});

// Spec 3.15.1, 3.15.4 and 3.15.5 cases beyond the app's tests.
describe("operating status (spec 3.15.5)", () => {
  const saturday = "2026-10-31";
  const originalTz = process.env.TZ;
  afterEach(() => {
    process.env.TZ = originalTz;
  });

  it("has no information for today's weekday even when other days are set", () => {
    const bar = schedule([hours(1, "18:00", "23:00")]);
    expect(homeOperatingState(bar, at(saturday, 20))).toBe("영업시간 정보 없음");
    // A regular day off is 영업 종료, not missing information.
    expect(homeOperatingState(schedule([closedDay(6)]), at(saturday, 20))).toBe("영업 종료");
    // Today's changed hours count as today's hours.
    expect(homeOperatingState(schedule([], exception("custom_hours", saturday, saturday, ["10:00", "12:00"])), at(saturday, 20))).toBe("영업 종료");
  });

  it("treats a closing time earlier than the opening as the next day, for changed hours from the server too", () => {
    const bar = schedule([hours(6, "18:00", "23:00")], exception("custom_hours", saturday, saturday, ["20:00", "01:00"]));
    expect(homeOperatingState(bar, at(saturday, 21))).toBe("영업 중");
    expect(operatingNextText(bar, at(saturday, 21))).toBe("익일 01:00 종료");
    expect(homeOperatingState(bar, at(addDays(saturday, 1), 0, 30))).toBe("영업 중");
    expect(homeOperatingState(bar, at(addDays(saturday, 1), 1, 30))).toBe("영업시간 정보 없음");
    expect(homeStatusDetail(bar.operatingException)).toBe("20:00 ~ 익일 01:00");
  });

  it("closes at midnight for 00:00", () => {
    const bar = schedule([hours(6, "18:00", "00:00")]);
    expect(homeOperatingState(bar, at(saturday, 23, 59))).toBe("영업 중");
    expect(operatingNextText(bar, at(saturday, 20))).toBe("익일 00:00 종료");
    expect(homeOperatingState(bar, at(addDays(saturday, 1), 0, 0))).toBe("영업시간 정보 없음");
  });

  it("keeps a closure that ended yesterday from letting yesterday's regular shift run over (3.15.4)", () => {
    // Friday 18:00 to 02:00, Friday changed to 18:00 to 22:00: at 00:30 on Saturday the bar is closed.
    const friday = addDays(saturday, -1);
    const bar = schedule([hours(5, "18:00", "02:00"), hours(6, "19:00", "23:00")], exception("custom_hours", friday, friday, ["18:00", "22:00"]));
    expect(homeOperatingState(bar, at(saturday, 0, 30))).toBe("영업 종료");
    expect(homeOperatingException(bar, at(saturday, 0, 30))).toBeNull();
  });

  it("closes the whole day on a vacation's boundary days, also yesterday's shift past midnight", () => {
    const bar = schedule([hours(5, "18:00", "02:00"), hours(6, "18:00", "02:00")], exception("vacation", saturday, addDays(saturday, 1)));
    expect(homeOperatingState(bar, at(saturday, 0, 30))).toBe("임시 휴무");
    expect(homeOperatingState(bar, at(addDays(saturday, 1), 23, 59))).toBe("임시 휴무");
    // The day after the last day: Sunday's hours (not set) do not run over, the vacation covered Sunday.
    expect(homeOperatingState(bar, at(addDays(saturday, 2), 0, 30))).toBe("영업시간 정보 없음");
  });

  it("titles the home card and its line", () => {
    const future = exception("vacation", "2026-11-05", "2026-11-07");
    expect(homeStatusTitle(future, at(saturday, 12))).toBe("임시 휴업 예정");
    expect(homeStatusTitle(future, at("2026-11-05", 12))).toBe("임시 휴무");
    expect(homeStatusDetail(future)).toBe("11.05 ~ 11.07");
    expect(homeStatusTitle(exception("closed_today", saturday), at(saturday, 12))).toBe("오늘 임시 휴무");
    expect(homeStatusTitle(null, at(saturday, 12))).toBe("정상 영업");
    expect(operatingLine(schedule([hours(6, "18:00", "02:00")]), at(saturday, 20))).toBe("영업 중, 익일 02:00 종료");
    expect(operatingLine(schedule([hours(6, "18:00", "02:00")]), at(saturday, 12))).toBe("영업 종료, 18:00 시작");
    expect(operatingLine(schedule([], exception("closed_today", saturday)), at(saturday, 12))).toBe("임시 휴무");
  });

  it("uses Seoul's date and time whatever the browser's time zone", () => {
    process.env.TZ = "America/Los_Angeles";
    // 2026-10-31 01:00 in Seoul is still 2026-10-30 in Los Angeles.
    expect(seoulClock(at(saturday, 1))).toEqual({ date: saturday, minute: 60, weekday: 6 });
    expect(applyDate(at(saturday, 1))).toBe(saturday);
    expect(homeOperatingState(schedule([hours(5, "18:00", "02:00")]), at(saturday, 1))).toBe("영업 중");
  });
});
