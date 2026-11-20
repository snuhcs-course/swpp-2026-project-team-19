import { describe, expect, it } from "vitest";
import { caretAfterDigits, editDigits } from "./formattedInput";

// The cases of android/.../ui/owner/OwnerRegistrationPhoneInputTest.kt that apply to a browser field.
describe("editDigits", () => {
  it("deleting an automatic separator deletes the digit before it", () => {
    // "010-1234-5678" with Backspace right after the first hyphen.
    expect(editDigits("01012345678", "010-1234-5678", "0101234-5678", 3, 12)).toEqual({ digits: "0112345678", caretDigits: 2 });
  });

  it("typing in the middle keeps the caret after the typed digit", () => {
    expect(editDigits("0101234", "010-1234", "010-91234", 5, 12)).toEqual({ digits: "01091234", caretDigits: 4 });
  });

  it("pasting a number without hyphens keeps every digit", () => {
    expect(editDigits("", "", "01012345678", 11, 12)).toEqual({ digits: "01012345678", caretDigits: 11 });
  });

  it("replacing a selection is an ordinary edit, not a separator Backspace", () => {
    expect(editDigits("01012345678", "010-1234-5678", "010-9-5678", 5, 12)).toEqual({ digits: "01095678", caretDigits: 4 });
  });

  it("caps the digits", () => {
    expect(editDigits("", "", "1234567890123", 13, 10).digits).toBe("1234567890");
  });
});

describe("caretAfterDigits", () => {
  it("skips a separator right after the caret, and never mistakes separators for digits", () => {
    expect(caretAfterDigits("010-1234-5678", 3)).toBe(4);
    expect(caretAfterDigits("010-1234-5678", 5)).toBe(6);
    expect(caretAfterDigits("2019.05.14", 4)).toBe(5);
    expect(caretAfterDigits("010", 0)).toBe(0);
  });
});
