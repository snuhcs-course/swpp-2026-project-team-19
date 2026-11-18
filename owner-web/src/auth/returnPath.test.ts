import { afterEach, describe, expect, it, vi } from "vitest";
import { isSafeReturnPath, saveReturnPath, takeReturnPath } from "./returnPath";

describe("return path after sign-in", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("is taken once", () => {
    saveReturnPath("/bars/22222222-2222-4222-8222-222222222222?tab=menu");

    expect(takeReturnPath()).toBe("/bars/22222222-2222-4222-8222-222222222222?tab=menu");
    expect(takeReturnPath()).toBeNull();
  });

  it.each(["//evil.example/owner", "/\\evil.example", "https://evil.example/", "bars", "/login", "", null])(
    "never keeps %s",
    (path) => {
      expect(isSafeReturnPath(path)).toBe(false);
      if (typeof path === "string") saveReturnPath(path);
      expect(takeReturnPath()).toBeNull();
    },
  );

  it("works without storage", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });

    expect(() => saveReturnPath("/bars")).not.toThrow();
    expect(takeReturnPath()).toBeNull();
  });
});
