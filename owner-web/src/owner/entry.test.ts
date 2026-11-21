import { describe, expect, it } from "vitest";
import type { ApplicationStatus } from "./applications";
import { ownerEntry } from "./entry";

const BAR = { barId: "22222222-2222-4222-8222-222222222222" };
const application = (status: ApplicationStatus, applicationId: string = crypto.randomUUID()) => ({ applicationId, status });

describe("ownerEntry", () => {
  // Ported from android/.../ui/owner/OwnerEntryRoutingTest.kt (the production cases; the mock-mode case has
  // no counterpart on the web).
  it("does not send an owner to registration while their data has not arrived", () => {
    // firstProductionEntryStaysOnOwnerDashboardWhenCacheIsEmpty
    expect(ownerEntry(undefined, undefined)).toBe("loading");
    expect(ownerEntry(undefined, [])).toBe("loading");
    expect(ownerEntry([], undefined)).toBe("loading");
  });

  it("keeps an owner on their bars once owned bars arrive", () => {
    // productionEntryKeepsDashboardWhenOwnedBarsArrive
    expect(ownerEntry([BAR], [])).toBe("bars");
  });

  // From the My Page entry rule, android/.../ui/auth/AccountScreens.kt.
  it("shows the bars first, even with an open application", () => {
    expect(ownerEntry([BAR], [application("pending")])).toBe("bars");
    expect(ownerEntry([BAR, { barId: "other" }], [application("rejected")])).toBe("bars");
  });

  it.each(["pending", "rejected"] as const)("shows the application status for a %s application", (status) => {
    expect(ownerEntry([], [application(status)])).toBe("application");
    expect(ownerEntry([], [application("canceled"), application(status)])).toBe("application");
  });

  it("starts an application when there is nothing to show", () => {
    expect(ownerEntry([], [])).toBe("apply");
    expect(ownerEntry([], [application("canceled")])).toBe("apply");
    // Approved, but the ownership was ended later (spec 3.11.10): the owner applies again.
    expect(ownerEntry([], [application("approved")])).toBe("apply");
  });

  // From OwnerMockModels.kt `openSingleBarManager`: a rejection removed from the list is not shown again.
  it("does not count a rejection the owner removed from their list", () => {
    const removed = application("rejected", "removed");
    expect(ownerEntry([], [removed], new Set(["removed"]))).toBe("apply");
    expect(ownerEntry([], [removed, application("rejected")], new Set(["removed"]))).toBe("application");
    // Only a rejection can be removed: a pending application with that ID still counts.
    expect(ownerEntry([], [application("pending", "removed")], new Set(["removed"]))).toBe("application");
  });
});
