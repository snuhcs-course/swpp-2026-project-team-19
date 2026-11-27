/**
 * Owner application rules, ported from the Android app. Each rule names its Kotlin source.
 * These are local format checks only; the NTS check is the server's (spec 3.11.2, 3.11.16).
 */

// android/.../ui/owner/OwnerRegistrationValidation.kt
export const phoneDigits = (value: string): string => value.replace(/\D/g, "").slice(0, 12);

/** 02, 0xx, 010 and 050x numbers. Blank passes: screens check that a required number is filled. */
export const validOwnerPhone = (value: string): boolean =>
  value.trim() === "" || /^0[0-9]{8,11}$/.test(value.replace(/\D/g, ""));

export const businessDigits = (value: string): string => value.replace(/\D/g, "").slice(0, 10);

/** The NTS check digit of a business registration number (spec 3.11.2). Not an NTS lookup. */
export function validBusinessRegistrationNumber(value: string): boolean {
  const number = businessDigits(value);
  if (number.length !== 10) return false;
  const digit = (index: number) => Number(number[index]);
  const weights = [1, 3, 7, 1, 3, 7, 1, 3, 5];
  let sum = weights.reduce((total, weight, index) => total + digit(index) * weight, 0);
  sum += Math.floor((digit(8) * 5) / 10);
  return (10 - (sum % 10)) % 10 === digit(9);
}

/** Today in Seoul as YYYY-MM-DD; opening dates after it are refused (spec 3.11.2 DATE_IN_FUTURE). */
export function seoulToday(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

/** A real calendar date in YYYY-MM-DD, no later than today in Seoul. */
export function validOpeningDate(iso: string, now: Date = new Date()): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return false;
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const date = new Date(Date.UTC(year, month - 1, day));
  const real = date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
  return real && iso <= seoulToday(now);
}

/** For display only; the draft keeps digits. */
export function formatOwnerPhone(value: string): string {
  const digits = phoneDigits(value);
  const prefix = digits.startsWith("02") ? 2 : digits.startsWith("050") ? 4 : 3;
  if (digits.length <= prefix) return digits;
  const remaining = digits.slice(prefix);
  if (remaining.length <= 4) return `${digits.slice(0, prefix)}-${remaining}`;
  const middle = remaining.length >= 8 ? 4 : 3;
  return `${digits.slice(0, prefix)}-${remaining.slice(0, middle)}-${remaining.slice(middle)}`;
}

/** 123-45-67891 (android/.../ui/owner/OwnerOnboardingScreen.kt bnFormat). */
export function formatBusinessNumber(value: string): string {
  const digits = businessDigits(value);
  if (digits.length <= 3) return digits;
  if (digits.length <= 5) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  return `${digits.slice(0, 3)}-${digits.slice(3, 5)}-${digits.slice(5)}`;
}

/** Typed digits as YYYY-MM-DD (OwnerOnboardingScreen.kt, the DATE page). */
export function openingDateFromInput(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 8);
  if (digits.length <= 4) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 4)}-${digits.slice(4)}`;
  return `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6)}`;
}

/** The first problem with the three business fields, or null (ownerRegistrationPrecheckError). */
export function registrationPrecheckError(
  businessNumber: string,
  representativeName: string,
  openingDate: string,
  now: Date = new Date(),
): string | null {
  if (!validBusinessRegistrationNumber(businessNumber)) return "사업자등록번호와 검사 숫자를 확인해 주세요.";
  const name = representativeName.trim();
  if (name.length === 0 || name.length > 100) return "사업자등록증의 대표자 이름을 확인해 주세요.";
  if (!validOpeningDate(openingDate, now)) return "개업일을 YYYY-MM-DD 형식으로 확인해 주세요.";
  return null;
}

// android/.../ui/owner/OwnerOnboardingScreen.kt ownerBusinessVerificationKey
export interface BusinessFields {
  businessNumber: string;
  representativeName: string;
  openingDate: string;
}

/** A check result belongs to exactly the three values it was asked for; formatting does not change them. */
export function businessVerificationKey(fields: BusinessFields): string {
  return [
    fields.businessNumber.replace(/\D/g, ""),
    fields.representativeName.trim(),
    fields.openingDate.trim().replaceAll(".", "-"),
  ].join("|");
}

export function businessVerificationIsCurrent(verifiedKey: string | null | undefined, fields: BusinessFields): boolean {
  return verifiedKey != null && verifiedKey === businessVerificationKey(fields);
}

// android/.../ui/owner/OwnerRegistrationProgress.kt
export type ApplicationKind = "existing_bar" | "new_bar";

export interface BarChoice {
  kind: ApplicationKind;
  existingBarId: string | null;
  proposedBarName: string;
}

/** Changing the name of a chosen existing bar drops that choice: the name no longer points at it. */
export function updatedBarName<T extends BarChoice>(draft: T, rawName: string): T {
  const name = rawName.slice(0, 150);
  const changedSelectedBar =
    draft.kind === "existing_bar" && draft.proposedBarName.trim().toLowerCase() !== name.trim().toLowerCase();
  return changedSelectedBar ? { ...draft, proposedBarName: name, kind: "new_bar", existingBarId: null } : { ...draft, proposedBarName: name };
}

/** A claim turned into a new-bar application while editing from review needs the new-bar details first. */
export function needsNewBarDetailsAfterClaimEdit(editingReview: boolean, previousKind: ApplicationKind, nextKind: ApplicationKind): boolean {
  return editingReview && previousKind === "existing_bar" && nextKind === "new_bar";
}

/** Whether the shop number can be copied into the contact field. */
export const canCopyShopPhone = (phone: string): boolean => phone.trim() !== "" && validOwnerPhone(phone);

// android/.../data/owner/LiveOwnerScreenRepository.kt partitionOwnerApplicationBarCandidates, and the
// exact-name matching of OwnerOnboardingScreen.kt (BARNAME)
export interface BarNameCandidate {
  barId: string;
  name: string;
  address: string;
  hasOwner: boolean;
}

/** Bars whose name is the typed name (trimmed, any case): each is asked about ("우리 매장이에요"). */
export function exactNameMatches<T extends BarNameCandidate>(candidates: readonly T[], typedName: string): T[] {
  const name = typedName.trim().toLowerCase();
  if (!name) return [];
  return candidates.filter((candidate) => candidate.name.trim().toLowerCase() === name);
}

/** Claimable bars, and bars that already have an owner (spec 3.11.11 hasOwner). */
export function partitionBarCandidates<T extends BarNameCandidate>(candidates: readonly T[]): [T[], T[]] {
  return [candidates.filter((candidate) => !candidate.hasOwner), candidates.filter((candidate) => candidate.hasOwner)];
}

/**
 * The consent asked with the contact phone (spec 3.11.2 `contactPhonePublic`). The app has no such item yet
 * (android/.../ui/owner/OwnerOnboardingScreen.kt contact step); this wording is the one the app is to use.
 */
export const CONTACT_PHONE_PUBLIC_LABEL = "매장 번호가 없으면 이 번호를 손님에게 보여 줘요";

/** The consent as the review step and the application detail show it. */
export function contactPhonePublicText(consented: boolean): string {
  return consented ? "매장 번호가 없을 때 보여요" : "보여 주지 않아요";
}
