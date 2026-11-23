import type { components } from "../api/schema";
import type { BarMenu } from "../owner/queries";
import type { ImportReview, ReviewLine } from "../menuImport/review/mapping";

/** Fixtures for menu import tests, shaped as spec 5.4 and 3.9 return them. */
type MenuItem = BarMenu["items"][number];
type MenuOption = MenuItem["options"][number];
type Candidate = components["schemas"]["ReviewCandidate"];
type LineOption = ReviewLine["options"][number];

export const lineOption = (id: string, label: string | null, pourMl: number | null, price: number | null, order = 1): LineOption => ({
  extractedOptionId: id,
  optionOrder: order,
  extractedOptionLabel: label,
  extractedPourMl: pourMl,
  extractedPriceKrw: price,
});

export const candidate = (productId: string, displayName: string, rank = 1): Candidate => ({
  productId,
  candidateRank: rank,
  displayName,
  brandId: "brand-1",
  brandName: "Brand",
  category: "whisky",
  ageYears: null,
  editionName: null,
  abv: null,
  matchMethod: "alias",
  score: 1,
  evidence: {},
});

/** A whisky line matched exactly to `product-1` by default (LivePhotoReviewMappingTest.kt `item`). */
export function line(overrides: Partial<ReviewLine> = {}): ReviewLine {
  return {
    extractedItemId: "line-1",
    itemOrder: 1,
    rawText: "위스키 30ml 15,000",
    sourceBox: [10, 20, 900, 60],
    extractedLineType: "product",
    extractedKind: "whisky",
    correctedLineType: null,
    effectiveLineType: "product",
    initialResolutionStatus: "exact_match",
    extractedProductName: "위스키 12년",
    extractedBrandName: "Brand",
    extractedAgeYears: null,
    extractedEditionName: null,
    extractedAbv: null,
    extractionConfidence: 0.9,
    proposedProductId: "product-1",
    options: [lineOption("opt-1", null, 30, 15000)],
    candidates: [candidate("product-1", "Whisky 12")],
    newProductDraft: { brandText: "Brand", category: "whisky", displayName: "위스키 12년", ageYears: null, editionName: null, abv: null },
    ...overrides,
  };
}

/** A whisky line no catalog product was found for. */
export const unmatchedLine = (overrides: Partial<ReviewLine> = {}): ReviewLine =>
  line({ initialResolutionStatus: "unmatched", proposedProductId: null, candidates: [], ...overrides });

/** A non-whisky line (extractedKind other, 5.4). */
export const otherLine = (overrides: Partial<ReviewLine> = {}): ReviewLine =>
  line({ extractedKind: "other", initialResolutionStatus: null, proposedProductId: null, candidates: [], newProductDraft: null, ...overrides });

export function review(lines: ReviewLine[], overrides: Partial<ImportReview> = {}): ImportReview {
  return {
    menuImportId: "import-1",
    barId: "bar-1",
    mode: "partial_update",
    status: "ready_for_review",
    reviewVersion: 3,
    images: [{ imageId: "photo-1", imageOrder: 1, imageUrl: "https://signed.example/photo-1", imageUrlExpiresAt: null, items: lines }],
    reviewDraft: null,
    proposedChanges: [],
    ...overrides,
  };
}

export const savedOption = (id: string, label: string | null, pourMl: number | null, priceKrw: number, discount: MenuOption["discount"] = null): MenuOption => ({
  menuEntryOptionId: id,
  optionLabel: label,
  pourMl,
  priceKrw,
  discount,
  sortOrder: 1,
});

export const menuItem = (overrides: Partial<MenuItem>): MenuItem => ({
  menuBoardEntryId: `entry-${overrides.barMenuItemId ?? "x"}`,
  barMenuItemId: "x",
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

/** The bar's menu: `product-1` at 12,000 won for 30ml by default (LivePhotoReviewMappingTest.kt `fixture`). */
export function menu(items: MenuItem[] = [menuItem({ barMenuItemId: "row-1", productId: "product-1", displayName: "Whisky 12", options: [savedOption("saved-30", null, 30, 12000)] })]): BarMenu {
  return {
    barId: "bar-1",
    name: "Whisky Bar",
    address: "서울",
    latitude: 37.5,
    longitude: 127,
    phone: null,
    description: null,
    tags: [],
    weeklyHours: [],
    operatingException: null,
    photos: [],
    menuBoardId: "board-1",
    menuVersion: 4,
    publishedAt: "2026-11-01T00:00:00Z",
    items,
  };
}
