import { describe, expect, it } from "vitest";
import { emptyDraft, type ApplicationDraft } from "../application/draft";
import { bar, ownerApplication } from "../test/api";
import {
  applicationBadge,
  applicationDateText,
  barBadge,
  isOpenApplication,
  managesApprovedBar,
  reapplicationDraft,
  shouldResumeDraft,
  visibleApplications,
} from "./applications";

const BAR_ID = "22222222-2222-4222-8222-222222222222";
const OTHER_BAR_ID = "33333333-3333-4333-8333-333333333333";

// Ported from android/.../ui/owner/OwnerRegistrationReapplicationTest.kt.
describe("reapplicationDraft (OwnerRegistrationProgress.kt reapplicationDraftFromRejected)", () => {
  const rejected = (overrides: Parameters<typeof ownerApplication>[0] = {}) =>
    ownerApplication({
      applicationId: "old-rejected",
      status: "rejected",
      rejectionReason: "매장을 확인할 수 없었어요.",
      proposedBar: { name: "몰트 앤 무드", address: "서울특별시 관악구 관악로 1 2층", phone: "02-555-1234" },
      businessRegistrationNumber: "1234567891",
      representativeName: "김민준",
      openingDate: "2019-05-14",
      contactPhone: "010-1234-5678",
      ...overrides,
    });

  it("starts at the intro and restores every field the application has", () => {
    // rejectedReapplicationStartsIntroAndRestoresEveryAvailableFieldAndPhoto (photos: see the next test)
    const input = rejected();
    const draft = reapplicationDraft(input);

    expect(draft.step).toBe("intro");
    expect(draft.kind).toBe("new_bar");
    expect(draft.proposedBarName).toBe("몰트 앤 무드");
    expect(draft.address).toBe("서울특별시 관악구 관악로 1 2층");
    expect(draft.addressDetail).toBe("");
    expect(draft.representativeName).toBe("김민준");
    expect(draft.businessNumber).toBe("1234567891");
    expect(draft.openingDate).toBe("2019-05-14");
    expect(draft.contactPhone).toBe("01012345678");
    expect(draft.storePhone).toBe("025551234");
    // The consent to show the contact phone is asked again, not carried over.
    expect(reapplicationDraft(rejected({ contactPhonePublic: true })).contactPhonePublic).toBe(false);
    // The source application is not changed.
    expect(input.status).toBe("rejected");
  });

  it("starts a new application: checked and sent anew, with no photo carried over", () => {
    // rejectedServerMenuPhotosAreReadOnlyNotUploaderPickerUris: a server URL is never uploaded again. The
    // web draft keeps no photos at all, so only the upload state and the application ID are checked.
    const draft = reapplicationDraft(
      rejected({
        menuPhotos: [{ imageOrder: 1, imageUrl: "https://storage.example.com/signed/menu.jpg", imageUrlExpiresAt: null }],
      }),
    );

    expect(draft.applicationId).toBeNull();
    expect(draft.uploaded).toEqual({ cover: false, menus: false });
    expect(draft.verification).toBeNull();
  });

  it("keeps the claimed bar of an existing-bar application", () => {
    // rejectedExistingBarRetainsBarIdentityAndSkipsNewBarRequirements
    const draft = reapplicationDraft(
      ownerApplication({
        status: "rejected",
        applicationType: "existing_bar",
        bar: { barId: "saved-bar", name: "관악 위스키 바", address: "서울특별시 관악구 관악로 2" },
        proposedBar: null,
      }),
    );

    expect(draft.kind).toBe("existing_bar");
    expect(draft.existingBar).toEqual({ barId: "saved-bar", name: "관악 위스키 바", address: "서울특별시 관악구 관악로 2" });
    expect(draft.proposedBarName).toBe("관악 위스키 바");
    expect(draft.address).toBe("");
    expect(draft.step).toBe("intro");
  });

  it.each(["pending", "approved", "canceled"] as const)("refuses a %s application", (status) => {
    // nonRejectedApplicationCannotStartReapply: no second pending application by accident. Canceled ones
    // start a new application instead, as in the app.
    expect(() => reapplicationDraft(ownerApplication({ status }))).toThrow();
  });

  it("leaves the business number empty when the server could not read it", () => {
    expect(reapplicationDraft(rejected({ businessRegistrationNumber: null })).businessNumber).toBe("");
  });
});

describe("barBadge (OwnerMockModels.kt hasPublishedInitialReview)", () => {
  it("asks for the menu until the first review is published", () => {
    // approvedBarRequiresPublishedImportAndMenuBeforeManaging: the web reads the bar's current menu instead
    // of the import history and the menu items.
    expect(barBadge(bar(BAR_ID, "바"))).toEqual({ label: "메뉴 확인 필요", tone: "pending" });
    expect(
      barBadge(
        bar(BAR_ID, "바", {
          currentMenu: { menuBoardId: "m", menuVersion: 1, publishedAt: "2026-11-20T03:00:00Z", confirmedAt: null },
        }),
      ),
    ).toEqual({ label: "승인됨", tone: "approved" });
  });
});

// From OwnerRegistrationDashboard.kt (no Android unit test).
describe("application cards (OwnerRegistrationDashboard.kt)", () => {
  it.each([
    ["pending", "검토 중", "pending"],
    ["rejected", "승인되지 않음", "rejected"],
    ["approved", "승인됨", "approved"],
    ["canceled", "취소됨", "pending"],
  ] as const)("labels a %s application", (status, label, tone) => {
    expect(applicationBadge(status)).toEqual({ label, tone });
  });

  it("dates a rejection by its review and everything else by when it was sent, in Seoul time", () => {
    const sent = "2026-11-20T15:30:00Z"; // 11월 21일 in Seoul
    const reviewed = "2026-11-22T01:00:00Z";
    expect(applicationDateText({ status: "pending", createdAt: sent, reviewedAt: null })).toBe("11월 21일에 신청했어요");
    expect(applicationDateText({ status: "rejected", createdAt: sent, reviewedAt: reviewed })).toBe("11월 22일에 검토했어요");
    expect(applicationDateText({ status: "approved", createdAt: sent, reviewedAt: reviewed })).toBe("11월 21일에 신청했어요");
    expect(applicationDateText({ status: "canceled", createdAt: sent, reviewedAt: null })).toBe("11월 21일에 신청했어요");
  });

  it("never makes up a date", () => {
    // A rejection without a review time falls back to the sending date, never calling it a review date.
    expect(applicationDateText({ status: "rejected", createdAt: "2026-11-20T03:00:00Z", reviewedAt: null })).toBe(
      "11월 20일에 신청했어요",
    );
    expect(applicationDateText({ status: "pending", createdAt: "not a time", reviewedAt: null })).toBe("신청일 정보 없음");
  });

  it("hides removed rejections and approvals whose bar is on the bar list", () => {
    const removed = ownerApplication({ status: "rejected" });
    const rejected = ownerApplication({ status: "rejected" });
    const managed = ownerApplication({ status: "approved", bar: { barId: BAR_ID, name: "바", address: "주소" } });
    const ended = ownerApplication({ status: "approved", bar: { barId: OTHER_BAR_ID, name: "바", address: "주소" } });
    const pending = ownerApplication({ status: "pending" });
    const canceled = ownerApplication({ status: "canceled" });
    const bars = [bar(BAR_ID, "바")];

    const shown = visibleApplications([removed, rejected, managed, ended, pending, canceled], bars, new Set([removed.applicationId]));

    expect(shown).toEqual([rejected, ended, pending, canceled]);
    expect(managesApprovedBar(managed, bars)).toBe(true);
    expect(managesApprovedBar(ended, bars)).toBe(false);
  });

  it("hides only rejections, whatever IDs are stored", () => {
    const pending = ownerApplication({ status: "pending" });
    expect(visibleApplications([pending], [], new Set([pending.applicationId]))).toEqual([pending]);
    expect(isOpenApplication(pending, new Set([pending.applicationId]))).toBe(true);
  });
});

describe("shouldResumeDraft", () => {
  const draft = (overrides: Partial<ApplicationDraft>): ApplicationDraft => ({ ...emptyDraft(), ...overrides });

  it("resumes a draft not sent yet", () => {
    expect(shouldResumeDraft(draft({ step: "representative" }), [])).toBe(true);
  });

  it("resumes a sent application only while it is pending with photos to send", () => {
    const sent = draft({ applicationId: "app-1", step: "review" });
    expect(shouldResumeDraft(sent, [{ applicationId: "app-1", status: "pending" }])).toBe(true);
    expect(shouldResumeDraft(sent, [{ applicationId: "app-1", status: "canceled" }])).toBe(false);
    expect(shouldResumeDraft(sent, [{ applicationId: "app-1", status: "rejected" }])).toBe(false);
    expect(shouldResumeDraft(sent, [])).toBe(false);
  });

  it("has nothing to resume without a draft", () => {
    expect(shouldResumeDraft(null, [])).toBe(false);
  });
});
