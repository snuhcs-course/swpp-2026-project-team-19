import { describe, expect, it } from "vitest";
import {
  inactiveOwnerCatalogMatch,
  manualBrandProposal,
  manualBrandSearchQuery,
  manualEditorCategory,
  manualProductProposal,
} from "./catalogMatch";
import { editDraftOf, EDIT_BLOCKED, freshExactMatch, prepareMenuSave, SaveRefused, toOption, type DraftOption, type SaveInput } from "./menuEditor";
import { ownerAddMenuIdentity } from "./menuIdentity";
import {
  MAX_OWNER_MENU_PRICE_KRW,
  existingBarProductMenu,
  manualMenuMatches,
  manualMenuOptionError,
  manualMenuShortName,
  menuProductOf,
  ownerPriceInput,
  type MenuBrand,
  type MenuItem,
  type MenuProduct,
  type OptionValue,
} from "./menuRules";
import { canonicalServingLabel, isBottleServingLabel, servingIdentityKey } from "./servingIdentity";

const product = (overrides: Partial<MenuProduct>): MenuProduct => ({
  productId: "product",
  brandId: "",
  displayName: "",
  category: "whisky",
  ageYears: null,
  isActive: true,
  matchedAlias: null,
  catalogMatched: true,
  ...overrides,
});
const option = (optionId: string, pourMl: number | null, priceKrw: number, bottle = false): OptionValue => ({
  optionId,
  label: bottle ? "Bottle" : null,
  pourMl,
  priceKrw,
  discount: null,
});
/** A menu item as GET /api/bars/{barId}/menu returns it (spec 3.9). */
const item = (overrides: Partial<MenuItem>): MenuItem => ({
  menuBoardEntryId: "entry",
  barMenuItemId: "item",
  productId: null,
  productName: null,
  brandId: null,
  brandName: null,
  category: null,
  kind: "whisky",
  displayName: "",
  sortOrder: 1,
  soldOut: false,
  options: [],
  ...overrides,
});
const menuOption = (id: string, label: string | null, pourMl: number | null, priceKrw: number): MenuItem["options"][number] => ({
  menuEntryOptionId: id,
  optionLabel: label,
  pourMl,
  priceKrw,
  discount: null,
  sortOrder: 1,
});

describe("serving identity (OwnerServingIdentityTest.kt)", () => {
  it("koreanAndEnglishBottleShareTheSameIdentity", () => {
    expect(canonicalServingLabel("병")).toBe("Bottle");
    expect(canonicalServingLabel(" bottle ")).toBe("Bottle");
    expect(canonicalServingLabel("병 500ml")).toBe("Bottle");
    expect(canonicalServingLabel("Bottle 700ml")).toBe("Bottle");
    expect(canonicalServingLabel("병(330ml)")).toBe("Bottle");
    expect(isBottleServingLabel("병")).toBe(true);
    expect(isBottleServingLabel("BOTTLE")).toBe(true);
    expect(servingIdentityKey(null, "병")).toBe(servingIdentityKey(null, "Bottle"));
    expect(servingIdentityKey(700, "병")).toBe(servingIdentityKey(null, "Bottle"));
  });

  it("glassIdentityIsOnlyPourVolumeRegardlessOfLabel", () => {
    expect(isBottleServingLabel("잔")).toBe(false);
    expect(isBottleServingLabel("샷")).toBe(false);
    expect(canonicalServingLabel("잔")).toBe("잔");
    expect(servingIdentityKey(30, "잔")).toBe(servingIdentityKey(30, "샷"));
    expect(servingIdentityKey(30, "잔")).not.toBe(servingIdentityKey(60, "잔"));
  });

  it("missingOrCustomNonBottleLabelsAreNotInvented", () => {
    expect(canonicalServingLabel(null)).toBeNull();
    expect(canonicalServingLabel(" 하프잔 ")).toBe("하프잔");
    expect(servingIdentityKey(null, null)).toBe("ml:unspecified");
    expect(servingIdentityKey(null, "잔")).toBe(servingIdentityKey(null, "샷"));
  });
});

describe("add identity (OwnerMenuIdentityContractTest.kt)", () => {
  const canonicalId = "11111111-1111-4111-8111-111111111111";

  it("canonicalProductOnlyInFreshLookupStillUsesProductId", () => {
    const staged = product({ productId: canonicalId, displayName: "라가불린 16년" });
    expect(ownerAddMenuIdentity(canonicalId, staged, null)).toEqual({ productId: canonicalId });
  });

  it("canonicalProductFromPublishedSnapshotUsesProductId", () => {
    const saved = product({ productId: canonicalId, displayName: "위스키" });
    expect(ownerAddMenuIdentity(canonicalId, null, saved)).toEqual({ productId: canonicalId });
  });

  it("unmatchedWhiskyOnlySendsKind", () => {
    const local = product({ productId: "local-unverified-test", displayName: "위스키 1", catalogMatched: false });
    expect(ownerAddMenuIdentity(local.productId, local, null)).toEqual({ kind: "whisky" });
  });

  it("nonWhiskyOnlySendsOtherWithoutCatalogId", () => {
    const beer = product({ productId: "local-unverified-beer", displayName: "맥주 1", category: "맥주", catalogMatched: false });
    expect(ownerAddMenuIdentity(beer.productId, beer, null)).toEqual({ kind: "other" });
    const published = { ...beer, productId: "unlinked:bar-item-id" };
    expect(ownerAddMenuIdentity(published.productId, null, published)).toEqual({ kind: "other" });
  });

  it("missingOrSyntheticCatalogIdentityFailsBeforeSending", () => {
    expect(() => ownerAddMenuIdentity(canonicalId, null, null)).toThrow("선택한 상품 정보를 확인하지 못했어요.");
    expect(() => ownerAddMenuIdentity("unlinked:row", product({ productId: "unlinked:row" }), null)).toThrow(RangeError);
    expect(() => ownerAddMenuIdentity("wrong", product({ productId: canonicalId }), null)).toThrow(RangeError);
  });
});

describe("catalog proposals (OwnerManualCatalogMatchTest.kt)", () => {
  const brand: MenuBrand = { brandId: "brand-gf", name: "Glenfiddich", matchedAlias: "글렌피딕" };
  const twelve = product({ productId: "product-12", brandId: "brand-gf", displayName: "Glenfiddich 12 Year Old", ageYears: 12 });
  const fifteen = { ...twelve, productId: "product-15", ageYears: 15, displayName: "Glenfiddich 15 Year Old" };

  it("brandCanBeSearchedAfterItsOnlyBarMenuWasDeleted", () => {
    expect(manualBrandSearchQuery("글렌 피딕12년", "")).toBe("글렌피딕");
    expect(manualBrandSearchQuery("글렌 피딕12년", "Glenfiddich")).toBe("Glenfiddich");
    expect(manualBrandProposal([brand], "글렌 피딕12년", "", null)).toEqual(brand);
    expect(manualBrandProposal([brand], "글렌 피딕12년", "", "brand-gf")).toBeNull();
  });

  it("sameCatalogProductCanBeSuggestedAfterBrandConfirmation", () => {
    expect(manualProductProposal([twelve, fifteen], "글렌 피딕12년", "위스키", "brand-gf", null)).toEqual(twelve);
    expect(manualProductProposal([twelve, fifteen], "글렌 피딕12년", "위스키", "brand-gf", "product-12")).toBeNull();
  });

  it("multipleSameAgeEditionsDoNotAutoSelectOne", () => {
    const other = { ...twelve, productId: "other-12", displayName: "Glenfiddich 12 Special Edition" };
    expect(manualProductProposal([twelve, other], "글렌피딕 12년", "위스키", "brand-gf", null)).toBeNull();
  });

  it("inactiveCatalogProductIsVisibleButNotSelectable", () => {
    const inactive = { ...twelve, isActive: false };
    expect(inactiveOwnerCatalogMatch([inactive], "Glenfiddich 12 Year Old")).toEqual(inactive);
    expect(manualProductProposal([inactive], "Glenfiddich 12 Year Old", "위스키", "brand-gf", null)).toBeNull();
    expect(inactiveOwnerCatalogMatch([twelve], "Glenfiddich 12 Year Old")).toBeNull();
  });

  it("inactiveProductMatchedByKoreanAliasCannotBeAddedAsNew", () => {
    const deanston = product({ productId: "inactive-deanston", brandId: "brand-deanston", displayName: "Deanston 12", isActive: false, matchedAlias: "딘스톤 12년" });
    expect(inactiveOwnerCatalogMatch([deanston], "딘스톤 12년")).toEqual(deanston);
    expect(inactiveOwnerCatalogMatch([deanston], "딘스톤12년")).toEqual(deanston);
    expect(manualProductProposal([deanston], "딘스톤 12년", "위스키", null, null)).toBeNull();
    expect(inactiveOwnerCatalogMatch([deanston], "딘스톤 18년")).toBeNull();
    expect(inactiveOwnerCatalogMatch([{ ...deanston, isActive: true }], "딘스톤 12년")).toBeNull();
  });

  it("exactCatalogAliasIsSuggestedWithoutManualBrandInput", () => {
    const alias = { ...twelve, matchedAlias: "글렌피딕 12년" };
    expect(manualProductProposal([alias], "글렌피딕 12년", "위스키", null, null)).toEqual(alias);
  });

  it("customAlcoholCategoryIsShownAsTypedAndEditableWithoutChangingProductId (category part)", () => {
    // The app's other-alcohol subtype ("맥주") is not kept by the server, so only the category is ported.
    const beer = product({ productId: "beer-1", brandId: "brewery", displayName: "수제 맥주", category: "맥주" });
    expect(manualEditorCategory(beer)).toBe("기타 주류");
    expect(manualProductProposal([beer], "수제 맥주", "기타 주류", null, null)).toEqual(beer);
  });

  it("missingBrandConfirmationDoesNotInferEnglishProductId", () => {
    expect(manualProductProposal([twelve], "글렌피딕12년", "위스키", null, null)).toBeNull();
  });
});

describe("menu rules (OwnerManualMenuRulesTest.kt)", () => {
  const ten = product({ productId: "product-10", brandId: "brand-lagavulin", displayName: "라가불린 10년" });
  const sixteen = product({ productId: "product-16", brandId: "brand-lagavulin", displayName: "라가불린 16년" });

  it("ownerPriceInputStopsAtEightDigitsIncludingPasteAndImeInput", () => {
    expect(ownerPriceInput("123456789")).toBe("12345678");
    // A ninth digit inserted at the start or middle is ignored.
    expect(ownerPriceInput("12345678", "912345678")).toBe("12345678");
    expect(ownerPriceInput("12345678", "123945678")).toBe("12345678");
    expect(ownerPriceInput("12345678", "123456789")).toBe("12345678");
    expect(ownerPriceInput("", "123456789")).toBe("12345678");
    expect(ownerPriceInput("12345678", "1234567")).toBe("1234567");
    expect(ownerPriceInput("99,999,999원")).toBe("99999999");
    expect(ownerPriceInput("a1 b2,c3d4e5f6g7h8j9")).toBe("12345678");
    expect(ownerPriceInput("no digits")).toBe("");
    expect(manualMenuOptionError([option("max", 30, MAX_OWNER_MENU_PRICE_KRW)], "whisky")).toBeNull();
    expect(manualMenuOptionError([option("over", 30, 100_000_000)], "whisky")).not.toBeNull();
  });

  it("replacementLocalCategoryAcceptsSingleCocktailPriceAndRejectsWrongShape (rule part)", () => {
    expect(manualMenuOptionError([option("single", null, 15000)], "cocktail")).toBeNull();
    expect(manualMenuOptionError([option("ml99", 99, 15000), option("ml30-new", 30, 13000)], "cocktail")).toBe("이 메뉴는 가격을 하나만 등록할 수 있어요.");
  });

  it("manualPourLimitMatchesSharedImportInvariant", () => {
    expect(manualMenuOptionError([option("big", 32768, 10000)], "whisky")).not.toBeNull();
    expect(manualMenuOptionError([option("max", 32767, 10000)], "whisky")).toBeNull();
  });

  it("importSupportsLegacyHighPricesAndFourOptionsWhileManualCannotCreateThem", () => {
    const imported = [1, 2, 3, 4].map((index) => option(`legacy-${index}`, index * 15, index === 4 ? 100_000_000 : 1000 * index));
    expect(manualMenuOptionError(imported, "whisky")).not.toBeNull();
    // The web, like the app against the server, does not open an item with four or more options.
    const legacy = item({ options: imported.map((value) => menuOption(value.optionId, null, value.pourMl, value.priceKrw)) });
    expect(editDraftOf(legacy)).toBeNull();
    expect(EDIT_BLOCKED).toBe("이 메뉴는 가격 옵션이 4개 이상이어서 직접 수정할 수 없어요. 기존 메뉴는 유지됩니다.");
  });

  it("importedCocktailExtraOptionsAreRetainedWhileManualEditsSinglePrice", () => {
    const options = [1, 2, 3].map((index) => menuOption(`import-cocktail-${index}`, `serving-${index}`, null, 4000 * index));
    const cocktail = item({ barMenuItemId: "cocktail-menu", kind: "other", displayName: "수제 칵테일", options });
    const draft = editDraftOf(cocktail)!;
    expect(draft.category).toBe("기타 주류");
    expect(draft.options).toHaveLength(1);
    const request = prepareMenuSave({
      ...base([cocktail]),
      editing: cocktail,
      name: draft.name,
      category: draft.category,
      options: [{ ...draft.options[0]!, price: "6000" }],
    });
    expect(request.body.options).toEqual([
      { optionLabel: "serving-1", pourMl: null, priceKrw: 6000, discount: null },
      { optionLabel: "serving-2", pourMl: null, priceKrw: 8000, discount: null },
      { optionLabel: "serving-3", pourMl: null, priceKrw: 12000, discount: null },
    ]);
    expect(manualMenuOptionError(options.map((value) => ({ optionId: value.menuEntryOptionId, label: value.optionLabel, pourMl: null, priceKrw: value.priceKrw, discount: null })), "cocktail")).not.toBeNull();
  });

  it("sameBrandDifferentCatalogIdsRemainDifferentProducts", () => {
    const row10 = item({ barMenuItemId: "menu10", productId: ten.productId, productName: ten.displayName });
    expect(existingBarProductMenu([row10], ten.productId)).toBe(row10);
    expect(existingBarProductMenu([row10], sixteen.productId)).toBeUndefined();
  });

  it("duplicateOptionsAndInvalidPricesDoNotWriteAnyProductOrMenu", () => {
    expect(manualMenuOptionError([option("a", 30, 16000), option("b", 30, 20000)], "whisky")).not.toBeNull();
    expect(manualMenuOptionError([option("a", 30, 16000), option("b", 60, 20000), option("c", 90, 28000), option("d", 120, 35000)], "whisky")).not.toBeNull();
    expect(manualMenuOptionError([option("a", 30, 0)], "whisky")).not.toBeNull();
  });

  it("ownerMenuLabelOverrideRetainsCanonicalCatalogIdentityAndSearch (search part)", () => {
    const row = item({ productId: ten.productId, productName: ten.displayName, displayName: "라가불린 10년 시그니처", options: [menuOption("small", null, 30, 16000)] });
    expect(menuProductOf(row).productId).toBe(ten.productId);
    expect(manualMenuMatches(row, menuProductOf(row), "라가불린", "시그니처")).toBe(true);
  });

  it("searchingUsesBrandAndDisplayTextWithoutMergingDifferentAges", () => {
    const row10 = item({ productId: ten.productId, productName: ten.displayName, displayName: ten.displayName, options: [menuOption("opt10", null, 30, 16000)] });
    expect(manualMenuMatches(row10, menuProductOf(row10), "라가불린", "라가")).toBe(true);
    expect(manualMenuMatches(row10, menuProductOf(row10), "라가불린", "10년")).toBe(true);
    expect(manualMenuMatches(row10, menuProductOf(row10), "라가불린", "16년")).toBe(false);
    expect(manualMenuShortName(ten, "라가불린")).toBe("10년");
    expect(manualMenuShortName(sixteen, "라가불린")).toBe("16년");
  });

  it("importedLocalizedServingLabelsAreValidAndRemainIntactOnUnrelatedEdit", () => {
    const imported = [menuOption("ko-bottle", "병", null, 100_000_000), menuOption("ko-glass", "잔", 30, 17_000), menuOption("unspecified", null, null, 25_000)];
    const values = imported.map((value) => ({ optionId: value.menuEntryOptionId, label: value.optionLabel, pourMl: value.pourMl, priceKrw: value.priceKrw, discount: null }));
    expect(manualMenuOptionError(values, "whisky", values)).toBeNull();
    const localized = item({ barMenuItemId: "localized", productId: ten.productId, productName: ten.displayName, displayName: ten.displayName, options: imported });
    const draft = editDraftOf(localized)!;
    const request = prepareMenuSave({ ...base([localized]), editing: localized, name: "새 메뉴 이름", category: draft.category, options: draft.options });
    expect(request.body).toEqual({
      displayName: "새 메뉴 이름",
      options: [
        { optionLabel: "병", pourMl: null, priceKrw: 100_000_000, discount: null },
        { optionLabel: "잔", pourMl: 30, priceKrw: 17_000, discount: null },
        { optionLabel: null, pourMl: null, priceKrw: 25_000, discount: null },
      ],
    });
    // A saved price above the limit may stay, but cannot be changed to another one above it.
    const over: DraftOption[] = draft.options.map((value, index) => (index === 0 ? { ...value, price: "100000001" } : value));
    expect(() => prepareMenuSave({ ...base([localized]), editing: localized, name: "새 메뉴 이름", category: draft.category, options: over })).toThrow(SaveRefused);
  });

  it("ownerMenuSearchFindsUnlinkedBarOnlyWhiskyByNameNotCatalog", () => {
    const row = item({ barMenuItemId: "bar-only-row", displayName: "위스키 1", options: [menuOption("price-1", null, 30, 15000)] });
    expect(manualMenuMatches(row, null, "", "위스키1")).toBe(true);
    expect(manualMenuMatches(row, null, "", "위스키 1")).toBe(true);
    expect(manualMenuMatches(row, null, "", "위스키")).toBe(true);
    expect(manualMenuMatches(row, null, "", "다른 위스키")).toBe(false);
  });
});

describe("duplicate servings (OwnerReviewOptionContractTest.kt)", () => {
  it("manualMenuValidationAlsoRejectsDuplicateVolumeLabels", () => {
    const sameVolume: OptionValue[] = [
      { optionId: "glass-a", label: "잔", pourMl: 30, priceKrw: 20_000, discount: null },
      { optionId: "glass-b", label: "샷", pourMl: 30, priceKrw: 24_000, discount: null },
    ];
    expect(manualMenuOptionError(sameVolume, "whisky")).toBe("같은 제품에 동일한 용량 옵션을 중복 등록할 수 없어요.");
    expect(manualMenuOptionError(sameVolume.map((value, index) => (index === 1 ? { ...value, pourMl: 60 } : value)), "whisky")).toBeNull();
  });
});

function base(items: MenuItem[]): SaveInput {
  return { items, name: "", category: "위스키", options: [], linkedId: null, rejectedId: null, candidates: [], now: Date.parse("2026-11-22T00:00:00Z") };
}

describe("saving an item (OwnerManualMenuScreen.kt save)", () => {
  const glass: DraftOption = { id: "local-1", bottle: false, ml: "30", price: "17000", discount: null };
  const canonical = product({ productId: "44444444-4444-4444-8444-444444444444", brandId: "brand-gf", displayName: "Glenfiddich 12" });

  it("adds a confirmed catalog product by its productId, and another whisky by kind", () => {
    expect(prepareMenuSave({ ...base([]), name: "Glenfiddich 12", options: [glass], linkedId: canonical.productId, candidates: [canonical] })).toEqual({
      kind: "add",
      body: { displayName: "Glenfiddich 12", options: [{ optionLabel: null, pourMl: 30, priceKrw: 17000, discount: null }], productId: canonical.productId },
      shown: 1,
    });
    const bottle = { ...glass, bottle: true, ml: "" };
    expect(prepareMenuSave({ ...base([]), name: "위스키 1", options: [bottle] }).body).toEqual({
      displayName: "위스키 1",
      options: [{ optionLabel: "Bottle", pourMl: null, priceKrw: 17000, discount: null }],
      kind: "whisky",
    });
    expect(prepareMenuSave({ ...base([]), name: "진토닉", category: "칵테일", options: [{ ...glass, ml: "" }] }).body).toMatchObject({ kind: "other" });
  });

  it("refuses a product already on the menu, and a same-named item without a product, naming the item", () => {
    const onMenu = item({ barMenuItemId: "gf-item", productId: canonical.productId, productName: canonical.displayName, displayName: "글렌피딕 12년" });
    expect(() => prepareMenuSave({ ...base([onMenu]), name: "Glenfiddich 12", options: [glass], linkedId: canonical.productId, candidates: [canonical] })).toThrow(
      expect.objectContaining({ message: "이미 등록한 상품이에요. 기존 메뉴에서 용량, 가격을 수정해 주세요.", existingItemId: "gf-item" }),
    );
    const local = item({ barMenuItemId: "local-item", displayName: "위스키 1" });
    expect(() => prepareMenuSave({ ...base([local]), name: "위스키1", options: [glass] })).toThrow(expect.objectContaining({ existingItemId: "local-item" }));
    // Declined with "아니에요": a second item of that name may be added.
    expect(prepareMenuSave({ ...base([local]), name: "위스키1", options: [glass], rejectedId: "unlinked:local-item" }).kind).toBe("add");
  });

  it("refuses an inactive product's name, a long name, and a pour that is missing", () => {
    const inactive = { ...canonical, isActive: false };
    expect(() => prepareMenuSave({ ...base([]), name: "Glenfiddich 12", options: [glass], candidates: [inactive] })).toThrow("운영이 중지된 카탈로그 상품이에요.");
    expect(() => prepareMenuSave({ ...base([]), name: "가".repeat(81), options: [glass] })).toThrow("메뉴 이름을 확인해 주세요.");
    expect(() => prepareMenuSave({ ...base([]), name: "위스키 1", options: [{ ...glass, ml: "" }] })).toThrow("용량을 입력하거나 Bottle 판매를 선택해 주세요.");
    expect(() => prepareMenuSave({ ...base([]), name: "위스키 1", options: [{ ...glass, price: "" }] })).toThrow("가격을 숫자로 입력해 주세요.");
  });

  it("sends a saved discount back, and leaves out one that has ended (spec 3.14.2)", () => {
    const now = Date.parse("2026-11-22T00:00:00Z");
    const running = { discountedPriceKrw: 14000, startsAt: "2026-11-01T00:00:00Z", endsAt: "2026-12-01T00:00:00Z" };
    const ended = { ...running, endsAt: "2026-11-21T00:00:00Z" };
    expect(toOption({ ...glass, discount: running }, true, undefined, true, now).discount).toEqual(running);
    expect(toOption({ ...glass, discount: ended }, true, undefined, true, now).discount).toBeNull();
  });

  it("asks to confirm an exact active product before adding a whisky without one", () => {
    const exact = product({ productId: "p", displayName: "Lagavulin 16", matchedAlias: "라가불린 16년" });
    expect(freshExactMatch([exact], "라가불린 16년", "위스키", null)).toBe(exact);
    expect(freshExactMatch([exact], "라가불린 16년", "위스키", "p")).toBeNull();
    expect(freshExactMatch([{ ...exact, isActive: false }], "라가불린 16년", "위스키", null)).toBeNull();
  });
});
