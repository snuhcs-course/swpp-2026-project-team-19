import { afterEach, describe, expect, it, vi } from "vitest";
import { hideApplication, loadHiddenApplications } from "./hiddenApplications";

describe("hidden applications", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps the hidden IDs per account", () => {
    hideApplication("user-a", "app-1");
    hideApplication("user-a", "app-2");

    expect([...loadHiddenApplications("user-a")]).toEqual(["app-1", "app-2"]);
    expect(loadHiddenApplications("user-b").size).toBe(0);
    expect(loadHiddenApplications(undefined).size).toBe(0);
  });

  it("ignores a damaged entry", () => {
    localStorage.setItem("bottlemap-owner-web-hidden-applications:user-a", "{not json");
    expect(loadHiddenApplications("user-a").size).toBe(0);

    localStorage.setItem("bottlemap-owner-web-hidden-applications:user-a", JSON.stringify(["app-1", 3, null]));
    expect([...loadHiddenApplications("user-a")]).toEqual(["app-1"]);
  });

  it("still hides the card for this visit when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });

    expect([...hideApplication("user-a", "app-1")]).toEqual(["app-1"]);
  });
});
