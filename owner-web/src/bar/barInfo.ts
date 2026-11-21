import type { components } from "../api/schema";

/**
 * Editing a bar's description, phone, default pour and tags (spec 3.7), ported from the Android app:
 * - android/.../ui/owner/OwnerBarEditRules.kt: `barInfoError`, `withBarInfo`, `toggleBarTag`, `canCreateOwnerTagDraft`.
 * - android/.../ui/owner/OwnerInfoHtmlV4Screen.kt: the form, its tag suggestions and when it counts as edited.
 * - android/.../data/owner/LiveOwnerScreenRepository.kt `persistBar`: only changed fields are sent.
 *
 * Name and address are shown but not edited here: changing them will go through an operator review later.
 */
export type BarDetail = components["schemas"]["BarDetail"];
export type BarUpdate = components["schemas"]["BarUpdateInput"];

/** What the form holds, as typed. */
export interface BarInfoForm {
  description: string;
  phone: string;
  /** Digits only; empty for none. */
  pourMl: string;
  tags: string[];
}

export type BarInfoField = "description" | "phone" | "defaultPourMl" | "tags";

export const MAX_DESCRIPTION = 100;
export const MAX_PHONE = 30;
export const MAX_TAGS = 5;
export const MAX_TAG_LENGTH = 24;

/** Characters as the server counts them (Python), so an emoji is one, not two UTF-16 units. */
export const characterCount = (value: string): number => [...value].length;

export function formFromBar(bar: Pick<BarDetail, "description" | "phone" | "defaultPourMl" | "tags">): BarInfoForm {
  return {
    description: bar.description ?? "",
    phone: bar.phone ?? "",
    pourMl: bar.defaultPourMl?.toString() ?? "",
    tags: [...bar.tags],
  };
}

/** OwnerBarEditRules.kt `barInfoError`: the phone accepts digits and phone symbols only, as in the app. */
const PHONE_PATTERN = /^[+0-9() .-]{1,30}$/;

/**
 * The errors of the typed values, by field (OwnerBarEditRules.kt `barInfoError`, same messages). The
 * description is counted after trimming, as the server does (spec 3.7).
 *
 * The phone is checked only once the owner edits it (`loaded` is the form as opened). The API takes any text up
 * to 30 characters, and an operator may have saved one the app's rule refuses (e.g. "02-123 내선 4"): left
 * as it is, such a phone must not keep the owner from saving the other fields.
 */
export function barInfoErrors(form: BarInfoForm, loaded: BarInfoForm): Partial<Record<BarInfoField, string>> {
  const errors: Partial<Record<BarInfoField, string>> = {};
  if (characterCount(form.description.trim()) > MAX_DESCRIPTION) errors.description = "한 줄 소개는 100자 이하여야 해요.";
  const phoneEdited = form.phone !== loaded.phone;
  if (phoneEdited && (form.phone.length > MAX_PHONE || (form.phone.trim() !== "" && !PHONE_PATTERN.test(form.phone)))) {
    errors.phone = "전화번호는 숫자와 전화번호 기호만 입력해 주세요.";
  }
  if (form.pourMl !== "") {
    const pour = Number(form.pourMl);
    if (!/^\d+$/.test(form.pourMl) || pour < 1 || pour > 999) errors.defaultPourMl = "기본 잔 용량은 1~999ml 사이로 입력해 주세요.";
  }
  return errors;
}

const sameTags = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every((tag, index) => tag === b[index]);

/** Whether the form differs from the bar as loaded (OwnerInfoHtmlV4Screen.kt `hasEdits`: the values as typed). */
export function hasEdits(bar: BarDetail, form: BarInfoForm): boolean {
  const loaded = formFromBar(bar);
  return (
    form.description !== loaded.description ||
    form.phone !== loaded.phone ||
    form.pourMl !== loaded.pourMl ||
    !sameTags(form.tags, loaded.tags)
  );
}

/**
 * The PATCH body (spec 3.7): only the fields that change (LiveOwnerScreenRepository.kt `persistBar`), each
 * normalized as `withBarInfo` does. A blank description or phone is sent as null, which removes it. The tags
 * are sent whole, since the server replaces them all. An empty body means there is nothing to send.
 */
export function barUpdate(bar: BarDetail, form: BarInfoForm): BarUpdate {
  const body: BarUpdate = {};
  const description = form.description.trim() || null;
  if (description !== bar.description) body.description = description;
  const phone = form.phone.trim() || null;
  if (phone !== bar.phone) body.phone = phone;
  const pour = form.pourMl === "" ? null : Number(form.pourMl);
  if (pour !== bar.defaultPourMl) body.defaultPourMl = pour;
  if (!sameTags(form.tags, bar.tags)) body.tags = [...form.tags];
  return body;
}

const sameTag = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();

/**
 * Adds a tag, or removes it when one equal ignoring case is selected (OwnerBarEditRules.kt `toggleBarTag`).
 * Null when the tag is blank or too long, or when a sixth would be added.
 */
export function toggleTag(current: readonly string[], candidate: string): string[] | null {
  const value = candidate.trim();
  if (value === "" || characterCount(value) > MAX_TAG_LENGTH) return null;
  const existing = current.findIndex((tag) => sameTag(tag, value));
  if (existing >= 0) return current.filter((_, index) => index !== existing);
  if (current.length >= MAX_TAGS) return null;
  return [...current, value];
}

/** Whether the typed tag is a new one to offer (OwnerBarEditRules.kt `canCreateOwnerTagDraft`). */
export function canCreateTag(query: string, available: readonly string[], selected: readonly string[]): boolean {
  const candidate = query.trim();
  return candidate !== "" && ![...available, ...selected].some((tag) => sameTag(tag, candidate));
}

/**
 * Suggested tags (OwnerInfoHtmlV4Screen.kt `OWNER_HTML_V4_TAGS`): the app's design suggestions, not a server
 * list. The spec has no tag vocabulary (3.7), so any tag can also be typed.
 */
export const SUGGESTED_TAGS = ["위스키 전문", "칵테일", "혼술바", "조용한 분위기", "안주", "클래식 인테리어", "데이트", "바 좌석", "단체석"];

/**
 * The tags to offer for `query` (OwnerInfoHtmlV4Screen.kt `candidates`): the suggestions and the tags of the
 * owner's bars, each once ignoring case, without the selected ones, matching the query, at most seven.
 */
export function tagCandidates(query: string, selected: readonly string[], ownBarTags: readonly string[]): string[] {
  const seen = new Set<string>();
  const needle = query.trim().toLowerCase();
  return [...SUGGESTED_TAGS, ...ownBarTags]
    .filter((tag) => {
      const key = tag.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .filter((tag) => !selected.some((chosen) => sameTag(chosen, tag)))
    .filter((tag) => tag.toLowerCase().includes(needle))
    .slice(0, 7);
}

/** The pool `canCreateTag` checks against (OwnerInfoHtmlV4Screen.kt `canCreate`). */
export const availableTags = (ownBarTags: readonly string[]): string[] => [...SUGGESTED_TAGS, ...ownBarTags];

/** Which form field a server `fieldErrors[].path` belongs to (`tags[2]` is the tags field). */
export function fieldOfPath(path: string): BarInfoField | null {
  if (path === "description" || path === "phone" || path === "defaultPourMl") return path;
  if (path === "tags" || path.startsWith("tags[")) return "tags";
  return null;
}
