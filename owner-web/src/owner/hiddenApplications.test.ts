import { afterEach, describe, expect, it, vi } from "vitest";
import { hideApplication, loadHiddenApplications } from "./hiddenApplications";

describe("hidden applications", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps the hidden IDs per account", () => {
    const first = hideApplication("user-a", "app-1", new Set());
    hideApplication("user-a", "app-2", first);

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

    const first = hideApplication("user-a", "app-1", new Set());
    const second = hideApplication("user-a", "app-2", first);

    // The first card stays hidden: the set builds on what the screen hides, not on storage.
    expect([...second].sort()).toEqual(["app-1", "app-2"]);
  });
});
