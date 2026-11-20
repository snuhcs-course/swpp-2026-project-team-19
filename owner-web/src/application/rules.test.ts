import { describe, expect, it } from "vitest";
import {
  businessVerificationIsCurrent,
  businessVerificationKey,
  canCopyShopPhone,
  exactNameMatches,
  formatBusinessNumber,
  formatOwnerPhone,
  needsNewBarDetailsAfterClaimEdit,
  openingDateFromInput,
  partitionBarCandidates,
  phoneDigits,
  registrationPrecheckError,
  updatedBarName,
  validBusinessRegistrationNumber,
  validOpeningDate,
  validOwnerPhone,
  type BarChoice,
} from "./rules";

// The Android tests each block ports are named in the describe titles.

describe("OwnerBusinessVerificationKeyTest", () => {
  const checked = { businessNumber: "1234567890", representativeName: "홍길동", openingDate: "2020-11-16" };

  it("changing the opening date invalidates a previous result", () => {
    const key = businessVerificationKey(checked);
    expect(businessVerificationIsCurrent(key, checked)).toBe(true);
    expect(businessVerificationIsCurrent(key, { ...checked, openingDate: "2020-11-17" })).toBe(false);
    expect(businessVerificationIsCurrent(null, checked)).toBe(false);
  });

  it("changing the business number or representative also invalidates it", () => {
    const key = businessVerificationKey(checked);
    expect(businessVerificationIsCurrent(key, { ...checked, businessNumber: "1234567891" })).toBe(false);
    expect(businessVerificationIsCurrent(key, { ...checked, representativeName: "다른 대표자" })).toBe(false);
  });

  it("insignificant date and number formatting does not invalidate it", () => {
    const key = businessVerificationKey(checked);
    expect(
      businessVerificationIsCurrent(key, { businessNumber: "123-45-67890", openingDate: "2020.11.16", representativeName: " 홍길동 " }),
    ).toBe(true);
  });
});

describe("OwnerRegistrationPrecheckTest", () => {
  const now = new Date("2030-01-01T00:00:00+09:00");

  it("accepts well-formed business fields without claiming the server agrees", () => {
    expect(registrationPrecheckError("1234567891", "김민준", "2019-05-14", now)).toBeNull();
  });

  it("rejects an invalid check digit before sending", () => {
    expect(registrationPrecheckError("1234567890", "김민준", "2019-05-14", now)).not.toBeNull();
  });

  it("rejects a missing representative and a future opening date", () => {
    expect(registrationPrecheckError("1234567891", " ", "2019-05-14", now)).not.toBeNull();
    expect(registrationPrecheckError("1234567891", "김민준", "2031-01-01", now)).not.toBeNull();
  });
});

describe("OwnerOnboardingValidationTest", () => {
  it("accepts common area, mobile and 0507 numbers", () => {
    for (const phone of ["02-1234-5678", "031-123-4567", "010-1234-5678", "0507-1234-5678"]) {
      expect(validOwnerPhone(phone)).toBe(true);
    }
  });

  it("matches the reference business-number check digit", () => {
    expect(validBusinessRegistrationNumber("123-45-67891")).toBe(true);
    expect(validBusinessRegistrationNumber("1234567891")).toBe(true);
    expect(validBusinessRegistrationNumber("1234567890")).toBe(false);
    expect(validBusinessRegistrationNumber("123")).toBe(false);
  });

  it("rejects impossible and future opening dates", () => {
    expect(validOpeningDate("2019-05-14")).toBe(true);
    expect(validOpeningDate("2024-02-30")).toBe(false);
    expect(validOpeningDate("2025-13-01")).toBe(false);
    expect(validOpeningDate("2099-01-01")).toBe(false);
    expect(validOpeningDate("20190514")).toBe(false);
  });

  it("requires phone numbers to begin with zero", () => {
    expect(validOwnerPhone("123456789")).toBe(false);
    expect(validOwnerPhone("0507-1234-5678")).toBe(true);
    expect(formatOwnerPhone("050712345678")).toBe("0507-1234-5678");
  });

  const claim: BarChoice = { kind: "existing_bar", existingBarId: "candidate-1", proposedBarName: "기존 매장" };

  it("changing a claimed bar's name clears the stale selection", () => {
    const edited = updatedBarName(claim, "새 매장");
    expect(edited).toEqual({ kind: "new_bar", existingBarId: null, proposedBarName: "새 매장" });
    expect(claim.existingBarId).toBe("candidate-1");
  });

  it("an unchanged claimed name still points at the chosen bar", () => {
    const edited = updatedBarName(claim, " 기존 매장 ");
    expect(edited.kind).toBe("existing_bar");
    expect(edited.existingBarId).toBe("candidate-1");
  });

  it("rejecting a claim during review must visit the new-bar details", () => {
    expect(needsNewBarDetailsAfterClaimEdit(true, "existing_bar", "new_bar")).toBe(true);
    expect(needsNewBarDetailsAfterClaimEdit(false, "existing_bar", "new_bar")).toBe(false);
    expect(needsNewBarDetailsAfterClaimEdit(true, "new_bar", "new_bar")).toBe(false);
  });

  it("copies the shop phone only when it is a valid number", () => {
    expect(canCopyShopPhone("02-1234-5678")).toBe(true);
    expect(canCopyShopPhone("0507-1234-5678")).toBe(true);
    expect(canCopyShopPhone("")).toBe(false);
    expect(canCopyShopPhone("112")).toBe(false);
  });

  it("phone formatting does not prevent independent contact input", () => {
    expect(phoneDigits("02-1234-5678")).toBe("0212345678");
    expect(phoneDigits("0507-1234-5678")).toBe("050712345678");
    expect(phoneDigits("")).toBe("");
    expect(validOwnerPhone("")).toBe(true);
    expect(validOwnerPhone("123")).toBe(false);
    expect(validOwnerPhone("1234567890123")).toBe(false);
  });
});

describe("OwnerRegistrationPhoneInputTest (display grouping)", () => {
  it("keeps the group lengths of area and safe-number prefixes", () => {
    expect(formatOwnerPhone("0212345678")).toBe("02-1234-5678");
    expect(formatOwnerPhone("021234567")).toBe("02-123-4567");
    expect(formatOwnerPhone("0311234567")).toBe("031-123-4567");
    expect(formatOwnerPhone("01012345678")).toBe("010-1234-5678");
    expect(formatOwnerPhone("010-1234-5678")).toBe("010-1234-5678");
  });
});

describe("OwnerUatClaimedBarTest", () => {
  const owned = { barId: "b1", name: "관악 위스키 바", address: "관악로 1", hasOwner: true };
  const free = { barId: "b2", name: "몰트 앤 무드", address: "신림로 2", hasOwner: false };

  it("already-owned bars never appear as claimable", () => {
    expect(partitionBarCandidates([owned, free])).toEqual([[free], [owned]]);
  });

  it("empty results clear both candidate lists", () => {
    expect(partitionBarCandidates([])).toEqual([[], []]);
  });
});

describe("input formatting", () => {
  it("formats the business number and the opening date as the app does", () => {
    expect(formatBusinessNumber("1234567891")).toBe("123-45-67891");
    expect(formatBusinessNumber("12345")).toBe("123-45");
    expect(openingDateFromInput("2019.05.14")).toBe("2019-05-14");
    expect(openingDateFromInput("201905")).toBe("2019-05");
  });

  it("matches existing bars by exact name, ignoring case and outer spaces", () => {
    const bars = [
      { barId: "1", name: "Malt & Mood", address: "", hasOwner: false },
      { barId: "2", name: "Malt & Mood 2호점", address: "", hasOwner: false },
    ];
    expect(exactNameMatches(bars, " malt & mood ").map((bar) => bar.barId)).toEqual(["1"]);
    expect(exactNameMatches(bars, "  ")).toEqual([]);
  });
});
