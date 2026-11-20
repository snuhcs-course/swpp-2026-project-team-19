import { afterEach, describe, expect, it, vi } from "vitest";
import { clearAllDrafts, clearDraft, emptyDraft, loadDraft, saveDraft } from "./draft";
import { stageOf, stepsBefore } from "./steps";

describe("application draft storage", () => {
  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("keeps each account's draft apart", () => {
    saveDraft("user-a", { ...emptyDraft(), step: "contact", businessNumber: "1234567891" });

    expect(loadDraft("user-a")).toMatchObject({ step: "contact", businessNumber: "1234567891" });
    expect(loadDraft("user-b")).toBeNull();
  });

  it("resumes at a saved checkpoint, and at the start for a transient screen", () => {
    saveDraft("user-a", { ...emptyDraft(), step: "reading" });
    expect(loadDraft("user-a")?.step).toBe("intro");

    saveDraft("user-a", { ...emptyDraft(), step: "done" });
    expect(loadDraft("user-a")?.step).toBe("intro");
  });

  it("ignores a broken or older draft", () => {
    localStorage.setItem("bottlemap-owner-web-application-draft:user-a", "{not json");
    expect(loadDraft("user-a")).toBeNull();
    localStorage.setItem("bottlemap-owner-web-application-draft:user-a", JSON.stringify({ version: 0, step: "menus" }));
    expect(loadDraft("user-a")).toBeNull();
  });

  it("clears one account, or every account on sign-out", () => {
    saveDraft("user-a", emptyDraft());
    saveDraft("user-b", emptyDraft());
    localStorage.setItem("unrelated", "kept");

    clearDraft("user-a");
    expect(loadDraft("user-a")).toBeNull();
    clearAllDrafts();
    expect(loadDraft("user-b")).toBeNull();
    expect(localStorage.getItem("unrelated")).toBe("kept");
  });

  it("works without storage", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });

    expect(() => saveDraft("user-a", emptyDraft())).not.toThrow();
    expect(loadDraft("user-a")).toBeNull();
  });
});

// Ported from android/.../ui/owner/OwnerOnboardingValidationTest.kt (the resume and Back path cases).
describe("application steps", () => {
  it("rebuilds the path to the menu photos of a new bar", () => {
    expect(stepsBefore("menus", "new_bar").at(-1)).toBe("bar-phone");
    expect(stepsBefore("bar-phone", "new_bar").at(-1)).toBe("address");
    expect(stepsBefore("address", "new_bar").at(-1)).toBe("cover");
  });

  it("goes back from contact to the menu photos", () => {
    expect(stepsBefore("contact", "new_bar").at(-1)).toBe("menus");
  });

  it("goes back from an existing bar's menu photos to the bar name", () => {
    expect(stepsBefore("menus", "existing_bar").at(-1)).toBe("bar-name");
  });

  it("goes back from the new-bar photo to the bar name, not to review", () => {
    expect(stepsBefore("cover", "new_bar").at(-1)).toBe("bar-name");
    expect(stepsBefore("intro", "new_bar")).toEqual([]);
  });

  it("shows the four stages", () => {
    expect((["method", "check", "bar-name", "address", "menus", "review", "intro", "done"] as const).map(stageOf)).toEqual([1, 1, 2, 2, 3, 4, 0, 0]);
  });
});
