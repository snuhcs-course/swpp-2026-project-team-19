/**
 * Digit fields shown with separators (business number 123-45-67891, phones 010-1234-5678, dates
 * 2019.05.14). Deleting a separator the field adds by itself must delete the digit before it, or Backspace
 * would seem to do nothing (android/.../ui/owner/OwnerRegistrationPhoneInput.kt ownerPhoneEdit).
 */
export function editDigits(
  previousDigits: string,
  previousText: string,
  nextText: string,
  caret: number,
  maxDigits: number,
): { digits: string; caretDigits: number } {
  let digits = nextText.replace(/\D/g, "").slice(0, maxDigits);
  let caretDigits = nextText.slice(0, caret).replace(/\D/g, "").length;
  const removedSeparatorOnly = digits === previousDigits && nextText.length === previousText.length - 1;
  if (removedSeparatorOnly && caretDigits > 0) {
    digits = digits.slice(0, caretDigits - 1) + digits.slice(caretDigits);
    caretDigits -= 1;
  }
  return { digits, caretDigits: Math.min(caretDigits, digits.length) };
}

/** Where the caret goes in `formatted` to sit after `digitCount` digits, past a separator right there. */
export function caretAfterDigits(formatted: string, digitCount: number): number {
  if (digitCount <= 0) return 0;
  let seen = 0;
  for (let index = 0; index < formatted.length; index++) {
    if (/\d/.test(formatted[index] ?? "")) seen++;
    if (seen === digitCount) {
      const right = index + 1;
      return formatted[right] === "-" || formatted[right] === "." ? right + 1 : right;
    }
  }
  return formatted.length;
}
