import { describe, expect, it } from "vitest";
import { bar } from "../test/api";
import {
  barInfoErrors,
  barUpdate,
  canCreateTag,
  characterCount,
  fieldOfPath,
  formFromBar,
  hasEdits,
  tagCandidates,
  toggleTag,
  type BarInfoForm,
} from "./barInfo";

const BAR_ID = "22222222-2222-4222-8222-222222222222";
const form = (change: Partial<BarInfoForm> = {}): BarInfoForm => ({ description: "", phone: "", pourMl: "", tags: [], ...change });

// Ported from android/.../ui/owner/OwnerBarEditRulesTest.kt (photo and hours tests wait for I5-P6).
describe("bar info rules (OwnerBarEditRules.kt)", () => {
  it("validates each field and never clears unrelated data", () => {
    // basicFieldsValidateAndNeverClearUnrelatedData: name and address are not edited on the web, so their
    // cases are left out; the unrelated data check becomes "only changed fields are sent".
    expect(barInfoErrors(form({ phone: "1234X" })).phone).toBeDefined();
    expect(barInfoErrors(form({ pourMl: "0" })).defaultPourMl).toBeDefined();
    expect(barInfoErrors(form({ description: "x".repeat(101) })).description).toBeDefined();
    expect(barInfoErrors(form({ description: "소개", phone: "02-1234-5678", pourMl: "30" }))).toEqual({});
    expect(barInfoErrors(form({ description: "소개", pourMl: "1000" })).defaultPourMl).toBeDefined();

    const before = bar(BAR_ID, "바", {
      tags: ["몰트"],
      photos: [{ photoId: "p1", imageUrl: "https://x/p1", thumbnailUrl: "https://x/p1/t" }],
    });
    const body = barUpdate(before, form({ description: " 조용한 바 ", phone: "02-1234-5678", pourMl: "45", tags: ["몰트"] }));
    expect(body).toEqual({ description: "조용한 바", phone: "02-1234-5678", defaultPourMl: 45 });
    expect(body).not.toHaveProperty("tags");
    expect(body).not.toHaveProperty("name");
  });

  it("rejects a sixth tag and a long tag, and toggles ignoring case and spaces", () => {
    // tagSearchSelectionToggleRejectsSixthAndLongTags
    const five = ["바", "몰트", "싱글몰트", "칵테일", "하이볼"];
    expect(toggleTag(five, "추가")).toBeNull();
    expect(toggleTag([], "한".repeat(25))).toBeNull();
    expect(toggleTag(five, " 몰트 ")).toEqual(five.filter((tag) => tag !== "몰트"));
    expect(toggleTag([], " 싱글몰트 ")).toEqual(["싱글몰트"]);
    expect(toggleTag(["몰트"], "몰트")).toEqual([]);
  });

  it("does not offer to create a tag already selected in the unsaved form", () => {
    // creatingTagDoesNotDeselectMatchingUnsavedDraftTag
    const available = ["몰트", "위스키"];
    const selected = ["수제 맥주", "몰트"];
    expect(canCreateTag("수제 맥주", available, selected)).toBe(false);
    expect(canCreateTag(" 수제 맥주 ", available, selected)).toBe(false);
    expect(canCreateTag("SINGLE", available, ["single"])).toBe(false);
    expect(canCreateTag("몰트", available, [])).toBe(false);
    expect(canCreateTag("  ", available, [])).toBe(false);
    expect(canCreateTag("새로운 태그", available, selected)).toBe(true);
  });
});

describe("bar info rules (web)", () => {
  it("counts characters as the server does, so an emoji is one", () => {
    expect(characterCount("🥃")).toBe(1);
    expect(barInfoErrors(form({ description: "🥃".repeat(100) })).description).toBeUndefined();
    expect(barInfoErrors(form({ description: "🥃".repeat(101) })).description).toBeDefined();
    // Counted after trimming (spec 3.7), and line breaks count as one.
    expect(barInfoErrors(form({ description: `  ${"가".repeat(98)}\n가  ` })).description).toBeUndefined();
    expect(toggleTag([], "🥃".repeat(24))).toEqual(["🥃".repeat(24)]);
  });

  it("accepts the phone characters the app accepts (OwnerBarEditRules.kt)", () => {
    expect(barInfoErrors(form({ phone: "+82 (2) 555.1234" })).phone).toBeUndefined();
    expect(barInfoErrors(form({ phone: "02-123 내선 4" })).phone).toBeDefined();
    expect(barInfoErrors(form({ phone: "1".repeat(31) })).phone).toBeDefined();
  });

  it("sends null for a cleared description, phone or pour, and the whole tag list when it changes", () => {
    const before = bar(BAR_ID, "바", { description: "소개", phone: "02-555-1234", defaultPourMl: 30, tags: ["몰트", "칵테일"] });

    expect(barUpdate(before, form({ description: "   ", phone: "", pourMl: "", tags: ["칵테일", "몰트"] }))).toEqual({
      description: null,
      phone: null,
      defaultPourMl: null,
      tags: ["칵테일", "몰트"],
    });
    expect(barUpdate(before, formFromBar(before))).toEqual({});
  });

  it("counts the form as edited by the values typed, as the app does", () => {
    const before = bar(BAR_ID, "바", { description: "소개", tags: ["몰트"] });
    expect(hasEdits(before, formFromBar(before))).toBe(false);
    expect(hasEdits(before, { ...formFromBar(before), description: "소개 " })).toBe(true);
    expect(hasEdits(before, { ...formFromBar(before), tags: [] })).toBe(true);
    // Edited, but the same after trimming: nothing to send.
    expect(barUpdate(before, { ...formFromBar(before), description: "소개 " })).toEqual({});
  });

  it("offers suggestions and the owner's own tags, once each, without the selected ones, at most seven", () => {
    // OwnerInfoHtmlV4Screen.kt `candidates`
    expect(tagCandidates("", [], [])).toHaveLength(7);
    expect(tagCandidates("칵", [], [])).toEqual(["칵테일"]);
    expect(tagCandidates("", ["칵테일"], [])).not.toContain("칵테일");
    expect(tagCandidates("몰트", [], ["싱글몰트", "싱글몰트", "SINGLE"])).toEqual(["싱글몰트"]);
    expect(tagCandidates("single", [], ["Single", "single"])).toEqual(["Single"]);
  });

  it("maps a server field path to its field", () => {
    expect(fieldOfPath("tags[2]")).toBe("tags");
    expect(fieldOfPath("description")).toBe("description");
    expect(fieldOfPath("weeklyHours[0].openTime")).toBeNull();
  });
});
