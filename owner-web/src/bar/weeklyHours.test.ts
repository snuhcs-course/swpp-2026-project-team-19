import { describe, expect, it } from "vitest";
import { canDeletePhoto, makeCover, MAX_BAR_PHOTOS, movePhoto, moveSecondaryPhoto, photoSlots } from "./photos";
import {
  copyMondayToWeekdays,
  draftFromHours,
  endsNextDay,
  hoursInput,
  sameHours,
  toggleDayClosed,
  validDay,
  weeklyHoursError,
  withDay,
  type DayDraft,
} from "./weeklyHours";

const day = (dayOfWeek: number, open: string | null, close: string | null, closed = false): DayDraft => ({ dayOfWeek, closed, open, close });

// Ported from android/.../ui/owner/OwnerBarEditRulesTest.kt (the hours and photo tests left for I5-P6).
describe("weekly hours (OwnerBarEditRules.kt)", () => {
  it("copies Monday to Tuesday to Friday only, and never wipes those days from an unset Monday", () => {
    // htmlV4MondayCopyAppliesOnlyTuesdayToFridayAndKeepsWeekend
    const monday = day(1, "18:00", "01:00");
    const saturday = day(6, null, null, true);
    const copied = copyMondayToWeekdays([monday, saturday]);
    expect(copied.map((item) => item.dayOfWeek)).toEqual([1, 2, 3, 4, 5, 6]);
    expect(copied.filter((item) => item.dayOfWeek >= 2 && item.dayOfWeek <= 5).every((item) => item.open === "18:00" && item.close === "01:00" && endsNextDay(item))).toBe(true);
    expect(copied.at(-1)).toEqual(saturday);
    expect(copyMondayToWeekdays([saturday])).toEqual([saturday]);
    // Regression: Monday is absent, but edits for Tue-Fri already exist.
    const existing = [day(2, "18:00", "23:00"), day(3, null, null, true), day(5, "20:00", "23:00"), saturday];
    expect(copyMondayToWeekdays(existing)).toEqual(existing);
  });

  it("keeps the entered times while a day is marked off", () => {
    // holidayToggleKeepsPreviouslyEnteredHoursInDraft
    const prior = day(2, "19:00", "02:00");
    const closed = toggleDayClosed(prior, 2, true);
    expect(closed).toEqual({ ...prior, closed: true });
    expect(toggleDayClosed(closed!, 2, false)).toEqual(prior);

    // A weekday not set before checking "휴무" returns to not set.
    const unsetClosed = toggleDayClosed(undefined, 3, true);
    expect(unsetClosed).toEqual(day(3, null, null, true));
    expect(toggleDayClosed(unsetClosed!, 3, false)).toBeNull();

    // Partly entered times survive the checkbox too.
    const partial = day(4, "18:00", null);
    expect(toggleDayClosed(toggleDayClosed(partial, 4, true)!, 4, false)).toEqual(partial);
  });

  it("tells not set, a day off, regular and overnight hours apart", () => {
    // weeklyHourValidationSeparatesUnsetClosedRegularAndOvernight (overnight comes from the times, spec 3.15.1)
    const normal = day(1, "18:00", "23:00");
    const overnight = day(2, "18:00", "02:00");
    expect(validDay(normal)).toBe(true);
    expect(validDay(overnight)).toBe(true);
    expect(endsNextDay(overnight)).toBe(true);
    expect(endsNextDay(normal)).toBe(false);
    expect(validDay(day(3, null, null, true))).toBe(true);
    expect(validDay({ ...normal, close: "18:00" })).toBe(false);
    expect(validDay({ ...normal, close: "18:03" })).toBe(false);
    expect(validDay({ ...normal, close: null })).toBe(false);
    expect(weeklyHoursError([normal, normal])).not.toBeNull();
    expect(weeklyHoursError([])).toBeNull();
    expect(hoursInput([overnight, normal]).map((item) => item.dayOfWeek)).toEqual([1, 2]);
  });
});

describe("weekly hours (web)", () => {
  it("sends no times on a day off, and nothing for a day not set", () => {
    const draft = [day(5, "18:00", "02:00"), day(1, "17:00", "23:00", true)];
    expect(hoursInput(draft)).toEqual([
      { dayOfWeek: 1, closed: true, openTime: null, closeTime: null },
      { dayOfWeek: 5, closed: false, openTime: "18:00", closeTime: "02:00" },
    ]);
  });

  it("leaves a day with nothing chosen out of the list", () => {
    const draft = withDay([day(1, "18:00", "23:00")], 1, day(1, null, null));
    expect(draft).toEqual([]);
    expect(withDay([], 3, day(3, "18:00", null))).toEqual([day(3, "18:00", null)]);
  });

  it("compares by what would be sent", () => {
    const loaded = draftFromHours([{ dayOfWeek: 1, closed: true, openTime: null, closeTime: null }]);
    // A day off keeps its draft times, but sends none: the same as loaded.
    expect(sameHours(loaded, [day(1, "18:00", "23:00", true)])).toBe(true);
    expect(sameHours(loaded, [day(1, "18:00", "23:00")])).toBe(false);
    expect(weeklyHoursError([day(1, "00:00", "23:55"), day(7, "23:55", "00:00")])).toBeNull();
  });
});

// Ported from android/.../ui/owner/OwnerBarEditRulesTest.kt.
describe("bar photos (OwnerBarEditRules.kt)", () => {
  it("stops at fifteen photos", () => {
    // photoGalleryStopsAtFifteenAndRejectsDuplicateUris (the server rejects a duplicate, 409 PHOTO_EXISTS)
    expect(MAX_BAR_PHOTOS).toBe(15);
    expect(photoSlots(14, 0)).toBe(1);
    expect(photoSlots(14, 1)).toBe(0);
    expect(photoSlots(15, 0)).toBe(0);
  });

  it("moves, sets the cover, and handles no photos", () => {
    // photoOrderAndCoverAndZeroPhotos
    const photos = ["p1", "p2", "p3"];
    expect(movePhoto(photos, 0, 1)).toEqual(["p2", "p1", "p3"]);
    expect(makeCover(photos, 2)).toEqual(["p3", "p1", "p2"]);
    expect(movePhoto(photos, 0, -1)).toEqual(photos);
    expect(makeCover(photos, 10)).toEqual(photos);
    expect(movePhoto([], 0, -1)).toEqual([]);
  });

  it("keeps the cover out of the arrows' reach", () => {
    // htmlV4PhotoArrowsProtectCoverAndChangeSecondaryOrder
    const images = ["p1", "p2", "p3"];
    expect(moveSecondaryPhoto(images, 0, 1)).toEqual(images);
    expect(moveSecondaryPhoto(images, 1, -1)).toEqual(images);
    expect(moveSecondaryPhoto(images, 1, 1)).toEqual(["p1", "p3", "p2"]);
    expect(makeCover(images, 2)).toEqual(["p3", "p1", "p2"]);
  });

  it("keeps the last photo, as the app does", () => {
    expect(canDeletePhoto(1)).toBe(false);
    expect(canDeletePhoto(2)).toBe(true);
  });
});
