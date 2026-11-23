import { describe, expect, it } from "vitest";
import { candidate, line, lineOption, menu, menuItem, otherLine, review, savedOption, unmatchedLine } from "../../test/menuImport";
import { encodeDraft, partialDecision, restoreDraft } from "./draft";
import { mapReview, splitMerged } from "./mapping";
import { priceValue, readNumeric, validDefaultPour, validPrice, validVolume, won, type ReviewCard, type ReviewState } from "./model";
import {
  applyDefaultPour,
  applyRematch,
  chooseServingPrice,
  confirmNew,
  confirmVolumeChoices,
  editOption,
  markAsNewForOperator,
  markLinked,
  mergedNotice,
  normalizedUnlinkedMenuName,
  optionFieldText,
  pendingPriceServings,
  priceCandidatesForServing,
  problems,
  reclassify,
  reviewStats,
  servingKey,
  toggleBottle,
  toggleVolumeChoice,
} from "./rules";
import { changeDecision, existingOptionsForProduct, finalReviewOptions, retainedForGroupedLine, reviewBody, ReviewSubmitError } from "./submit";

const NO_SAVED = {};
const stateOf = (cards: ReviewCard[], extra: Partial<ReviewState> = {}): ReviewState => ({ cards, defaultPour: 30, savedByProduct: NO_SAVED, ...extra });
const update = (state: ReviewState, card: ReviewCard): ReviewState => ({ ...state, cards: state.cards.map((c) => (c.id === card.id ? card : c)) });

describe("mapping the review response to cards (LivePhotoReviewMapping.kt)", () => {
  // LivePhotoReviewMappingTest.kt mapsRealExtractedIdsAndExistingPriceConflictWithoutDemoProducts
  it("links an exact match and asks which price to keep when the bar sells that serving for another", () => {
    const state = mapReview(review([line()]), menu(), 30);
    const card = state.cards[0]!;
    expect(state.cards).toHaveLength(1);
    expect([card.id, card.linkedProductId, card.match]).toEqual(["line-1", "product-1", "exact"]);
    expect(card.priceCandidates.map((c) => c.priceKrw).sort()).toEqual([12000, 15000]);
    expect(reviewStats(state).pending).toHaveLength(1);
    expect(card.options[0]!.volume).toBe(30);
    expect(state.defaultPour).toBe(30);
  });

  // LivePhotoReviewMappingTest.kt sameSizeDifferentLabelMatchesExistingWhiskyPriceByMl
  it("compares servings by ml whatever the menu calls them", () => {
    const saved = menu([menuItem({ barMenuItemId: "row-1", productId: "product-1", options: [savedOption("old-30", "잔", 30, 12000)] })]);
    const shot = mapReview(review([line({ options: [lineOption("ocr-shot", "샷", 30, 15000)] })]), saved, 30).cards[0]!;
    expect(shot.priceCandidates.map((c) => c.priceKrw).sort()).toEqual([12000, 15000]);
    expect(pendingPriceServings(shot, NO_SAVED)).toHaveLength(1);
  });

  // LivePhotoReviewMappingTest.kt koreanAndEnglishBottleShareExistingBarPrice
  it("treats 병 and Bottle as one bottle", () => {
    const saved = menu([menuItem({ barMenuItemId: "row-1", productId: "product-1", options: [savedOption("saved-bottle", "Bottle", null, 120000)] })]);
    for (const label of ["병", "Bottle"]) {
      const card = mapReview(review([line({ options: [lineOption("ocr-bottle", label, null, 150000)] })]), saved, 30).cards[0]!;
      expect(card.priceCandidates.map((c) => c.priceKrw).sort()).toEqual([120000, 150000]);
    }
  });

  // LivePhotoReviewMappingTest.kt sameWhiskyOcrLinesBecomeOneCardWithOne30mlChoice
  it("makes the lines of one whisky one card, with one choice for the serving they price differently", () => {
    const a = line({ options: [lineOption("ocr-glass-30", "잔", 30, 12000, 1), lineOption("ocr-60", "잔", 60, 22000, 2), lineOption("ocr-bottle", "병", null, 130000, 3)] });
    const b = line({ extractedItemId: "line-2", itemOrder: 2, rawText: "Whisky 샷 30ml 15,000", options: [lineOption("ocr-shot-30", "샷", 30, 15000)] });
    const data = review([a, b]);
    const state = mapReview(data, menu(), 30);
    const stats = reviewStats(state);
    expect(state.cards).toHaveLength(2);
    expect([stats.pending.length, stats.excluded.length]).toEqual([1, 0]);
    const master = state.cards[0]!;
    expect(state.cards[1]!.mergedInto).toBe("line-1");
    expect(mergedNotice(master)).toBe("같은 위스키가 두 줄 있어 하나로 합쳤어요.");
    expect(master.options).toHaveLength(3);
    expect(master.priceCandidates.filter((c) => c.servingKey === "ml:30").map((c) => c.priceKrw).sort()).toEqual([12000, 12000, 15000]);
    expect(pendingPriceServings(master, state.savedByProduct)).toEqual(["ml:30"]);
    const chosen = chooseServingPrice(master, "ml:30", 15000, state.savedByProduct);
    expect(pendingPriceServings(chosen, state.savedByProduct)).toEqual([]);
    expect(chosen.options[0]!.price).toBe(15000);

    const body = reviewBody(data, update(state, chosen), menu());
    expect(body.itemDecisions[0]!).toMatchObject({ action: "select_existing_product", productId: "product-1" });
    const options = (body.itemDecisions[0]! as { options: { extractedOptionId: string | null }[] }).options;
    expect(options.map((o) => o.extractedOptionId)).toEqual(["ocr-glass-30", "ocr-60", "ocr-bottle"]);
    expect(body.itemDecisions[1]!).toEqual({ action: "reject", extractedItemId: "line-2", finalLineType: "product" });
  });

  // LivePhotoReviewMappingTest.kt newServingFromAnotherOcrLineNeverUsesForeignExtractedOptionId
  it("sends a serving taken from another line as the owner's own, without that line's option ID", () => {
    const a = line({ options: [lineOption("a-30", null, 30, 15000)] });
    const b = line({ extractedItemId: "line-2", itemOrder: 2, options: [lineOption("b-60", null, 60, 26000)] });
    const state = mapReview(review([a, b]), menu([]), 30);
    expect(state.cards[0]!.options.map((o) => o.sourceOptionId)).toEqual(["a-30", null]);
  });

  // LivePhotoReviewMappingTest.kt fourWhiskySizesRequireExplicitSelectionOfUpToThree
  it("has the owner pick up to three servings when four or more were read", () => {
    const options = [1, 2, 3, 4].map((n) => lineOption(`opt-${n}`, null, n * 15, 10000 + n * 1000, n));
    const data = review([line({ options })]);
    const state = mapReview(data, menu([]), 30);
    let card = state.cards[0]!;
    expect([card.volumeChoicesConfirmed, card.volumeChoices.length]).toEqual([false, 4]);
    expect(problems(card, state)).toContain("option");
    for (const option of card.volumeChoices) card = toggleVolumeChoice(card, servingKey(option));
    expect(card.chosenVolumeKeys).toHaveLength(3);
    card = confirmVolumeChoices(card);
    expect(card.options).toHaveLength(3);
    expect(problems(card, update(state, card))).toEqual([]);
    const body = reviewBody(data, update(state, card), menu([]));
    expect((body.itemDecisions[0]! as { options: { extractedOptionId: string }[] }).options.map((o) => o.extractedOptionId)).toEqual(["opt-1", "opt-2", "opt-3"]);
  });

  // LivePhotoReviewMappingTest.kt missingPourUsesConfiguredBarDefaultInEveryOption
  it("gives a whisky glass without a pour the bar's default", () => {
    const state = mapReview(review([line({ options: [lineOption("a", "잔", null, 15000, 1), lineOption("b", null, 60, 20000, 2)] })]), menu([]), 45);
    expect(state.cards[0]!.options.map((o) => [o.volume, o.fromDefault])).toEqual([
      [45, true],
      [60, false],
    ]);
    expect(mapReview(review([line({ options: [lineOption("a", null, null, 15000)] })]), menu([]), null).cards[0]!.options[0]!.volume).toBe(30);
  });

  // LivePhotoReviewMappingTest.kt newWhiskyIsPublishedUnlinkedEvenWhenBrandIsMissing
  it("publishes a whisky the catalog lacks without a product once the owner confirms its name", () => {
    const data = review([unmatchedLine({ extractedBrandName: null })]);
    const state = mapReview(data, menu([]), 30);
    expect(problems(state.cards[0]!, state)).toContain("new");
    const confirmed = update(state, confirmNew(state.cards[0]!));
    expect(reviewStats(confirmed).canPublish).toBe(true);
    expect(reviewBody(data, confirmed, menu([])).itemDecisions[0]!).toEqual({
      action: "publish_without_product",
      extractedItemId: "line-1",
      finalLineType: "product",
      kind: "whisky",
      correctedProductName: "위스키 12년",
      options: [{ extractedOptionId: "opt-1", optionLabel: null, pourMl: 30, priceKrw: 15000 }],
    });
  });

  // LivePhotoReviewMappingTest.kt nonWhiskyOcrMenuCanPublishWithoutCatalogConfirmationOrBrand
  it("publishes a non-whisky line as another menu without a product or a pour", () => {
    const data = review([otherLine({ extractedProductName: "진토닉", options: [lineOption("gin", null, null, 12000)] })]);
    const state = mapReview(data, menu([]), 30);
    expect(reviewStats(state).other).toHaveLength(1);
    expect(reviewBody(data, state, menu([])).itemDecisions[0]!).toEqual({
      action: "publish_without_product",
      extractedItemId: "line-1",
      finalLineType: "product",
      kind: "other",
      correctedProductName: "진토닉",
      options: [{ extractedOptionId: "gin", optionLabel: null, pourMl: null, priceKrw: 12000 }],
    });
  });

  // LivePhotoReviewMappingTest.kt unnamedNonWhiskyMustReceiveOwnerNameInsteadOfRawOcrPriceLine
  it("asks for a name when the line has none instead of using its raw text", () => {
    const state = mapReview(review([otherLine({ extractedProductName: null, rawText: "12,000" })]), menu([]), 30);
    expect(state.cards[0]!.name).toBe("");
    expect(problems(state.cards[0]!, state)).toContain("name");
  });

  // LivePhotoReviewMappingTest.kt excludedLineMapsToRejectWithoutProductWrites
  it("sends headers and descriptions as reject, and they are not counted", () => {
    const header = line({ extractedItemId: "head", effectiveLineType: "section_header", extractedLineType: "section_header", extractedKind: null, options: [] });
    const data = review([header, line({ extractedItemId: "line-2", itemOrder: 2 })]);
    const state = mapReview(data, menu([]), 30);
    expect(state.cards[0]!).toMatchObject({ excluded: true, required: false });
    expect(reviewStats(state).total).toBe(1);
    expect(reviewBody(data, state, menu([])).itemDecisions[0]!).toEqual({ action: "reject", extractedItemId: "head", finalLineType: "section_header" });
  });

  // LivePhotoReviewMappingTest.kt sourceLineUsesServerItemOrderEvenWhenItIsNotContiguous
  it("numbers the line by the server's item order", () => {
    const state = mapReview(review([line({ itemOrder: 7 })]), menu([]), 30);
    expect(state.cards[0]!.sourceLine).toBe(7);
  });

  // LivePhotoReviewMappingTest.kt existingUnlinkedWhiskyNeedsPriceChoiceBeforeReplacingDiscountedServing
  it("asks which price to keep for the bar's item without a product of the same name", () => {
    const local = menu([
      menuItem({ barMenuItemId: "row1", displayName: "위스키 12년", options: [savedOption("old-30", "잔", 30, 12000), savedOption("old-60", "샷", 60, 26000)] }),
    ]);
    const state = mapReview(review([unmatchedLine()]), local, 30);
    const card = state.cards[0]!;
    expect(card.priceCandidates.filter((c) => c.servingKey === "ml:30").map((c) => c.priceKrw).sort()).toEqual([12000, 15000]);
    expect(pendingPriceServings(card, NO_SAVED)).toEqual(["ml:30"]);
    expect(reviewStats(state).canPublish).toBe(false);
    const chosen = chooseServingPrice(card, "ml:30", 12000, NO_SAVED);
    expect(pendingPriceServings(chosen, NO_SAVED)).toEqual([]);
    expect(chosen.options[0]!.price).toBe(12000);
  });

  // LivePhotoReviewMappingTest.kt existingUnlinkedOtherMenuAlsoRequiresSavedPriceReview
  it("asks the same for another menu", () => {
    const local = menu([menuItem({ barMenuItemId: "row2", kind: "other", displayName: "위스키 12년", options: [savedOption("old", "잔", 30, 12000)] })]);
    const state = mapReview(review([otherLine({ extractedProductName: "위스키 12년" })]), local, 30);
    const card = state.cards[0]!;
    expect(card.type).toBe("other");
    expect(problems(card, state)).toContain("priceChoice");
    expect(problems(chooseServingPrice(card, "ml:30", 12000, NO_SAVED), state)).not.toContain("priceChoice");
  });

  // LivePhotoReviewMappingTest.kt koreanBottleIsPublishedAsBottleWithoutLosingOcrIdentity
  it("publishes 병 as Bottle without a pour, keeping its option ID", () => {
    const data = review([line({ options: [lineOption("bottle", "병", null, 150000)] })]);
    const state = mapReview(data, menu([]), 30);
    expect((reviewBody(data, state, menu([])).itemDecisions[0]! as { options: unknown[] }).options).toEqual([
      { extractedOptionId: "bottle", optionLabel: "Bottle", pourMl: null, priceKrw: 150000 },
    ]);
  });

  // PhotoReviewViewModel.kt splitMerged
  it("splits a merged card back into its lines", () => {
    const a = line({ options: [lineOption("a-30", null, 30, 15000)] });
    const b = line({ extractedItemId: "line-2", itemOrder: 2, options: [lineOption("b-60", null, 60, 26000)] });
    const split = splitMerged(mapReview(review([a, b]), menu([]), 30), "line-1", () => []);
    expect(split.cards.map((c) => [c.id, c.mergedInto, c.excluded, c.options.map((o) => o.sourceOptionId)])).toEqual([
      ["line-1", null, false, ["a-30"]],
      ["line-2", null, false, ["b-60"]],
    ]);
    expect(split.cards[0]!.mergeSources).toEqual([]);
  });
});

describe("review rules (PhotoReviewRules.kt)", () => {
  const card = (overrides: Partial<ReviewCard> = {}) => ({ ...mapReview(review([line()]), menu([]), 30).cards[0]!, ...overrides });

  // PhotoReviewRulesTest.kt numberParsingFollowsThePrototype
  it("reads numbers as the app does", () => {
    expect(priceValue("15,000원")).toBe(15000);
    expect(priceValue("15000원원")).toBeNaN();
    expect(priceValue("12.5")).toBeNaN();
    expect(readNumeric("22.5")).toBe(22.5);
    expect(validVolume(22.5)).toBe(false);
    expect([validVolume(999), validVolume(1000), validVolume(32_767), validVolume(32_768)]).toEqual([true, true, true, false]);
    expect([validDefaultPour(999), validDefaultPour(1000), validDefaultPour(Infinity)]).toEqual([true, false, false]);
    expect(validPrice(100_000_000)).toBe(false);
    expect([won(15000), won(0), won(Number.NaN)]).toEqual(["15,000원", "—", "—"]);
  });

  // PhotoReviewRulesTest.kt duplicateOrMoreThanThreeWhiskyServingsNeedOptionReview, samePourWithDifferentOcrLabelsIsStillADuplicateOption
  it("refuses two options of one pour, whatever they are called, and more than three", () => {
    const option = (volume: number, label: string | null) => ({ volume, price: 10000, bottle: false, sourceOptionId: null, label, fromDefault: false });
    const state = stateOf([]);
    expect(problems(card({ options: [option(30, "잔"), option(30, "샷")] }), state)).toContain("option");
    expect(problems(card({ options: [15, 30, 45, 60].map((v) => option(v, null)) }), state)).toContain("option");
    expect(problems(card({ options: [option(30, null), option(60, null)] }), state)).not.toContain("option");
  });

  // PhotoReviewRulesTest.kt zeroOptionLineAsksForAPrice
  it("asks for a price on a line without options", () => {
    expect(problems(card({ options: [] }), stateOf([]))).toContain("price");
  });

  // PhotoReviewRulesTest.kt renameToTheSameProductKeepsTheLink
  it("keeps the link when the new name finds the same product", () => {
    const [renamed, outcome] = applyRematch(card({ name: "Whisky 12" }), [{ productId: "product-1", name: "Whisky 12" }], NO_SAVED);
    expect([outcome, renamed.linkedProductId, renamed.operatorReason]).toEqual(["same", "product-1", null]);
  });

  // PhotoReviewRulesTest.kt renameToAnotherSingleProductLinksItForOperatorCheck
  it("links another product the new name finds, for the operator to check", () => {
    const [renamed, outcome] = applyRematch(card(), [{ productId: "product-2", name: "Whisky 15" }], NO_SAVED);
    expect([outcome, renamed.linkedProductId, renamed.operatorReason]).toEqual(["changed", "product-2", "changed"]);
  });

  // PhotoReviewRulesTest.kt renameWithNoOrManyMatchesUnlinksForTheOperator
  it("leaves the whisky without a product when the new name finds none or several", () => {
    for (const matches of [[], [{ productId: "a", name: "A" }, { productId: "b", name: "B" }]]) {
      const [renamed, outcome] = applyRematch(card(), matches, NO_SAVED);
      expect([outcome, renamed.linkedProductId, renamed.match, renamed.nameSaved, renamed.operatorReason]).toEqual(["operator", null, "new", true, "unlinked"]);
      expect(problems(renamed, stateOf([renamed]))).toEqual([]);
    }
  });

  // PhotoReviewRulesTest.kt notFoundWhiskyBecomesANewMenuWithoutCatalogFields
  it("marks a whisky not found in the catalog as new, waiting for its name", () => {
    const marked = markAsNewForOperator(card({ searchMode: true }), "새 위스키");
    expect([marked.name, marked.linkedProductId, marked.match, marked.nameEditing, marked.searchMode]).toEqual(["새 위스키", null, "new", true, false]);
    expect(problems(marked, stateOf([marked]))).toEqual(expect.arrayContaining(["new", "name"]));
  });

  // PhotoReviewRulesTest.kt switchingCatalogWhiskyToOtherNeverLeavesAProductLink, reclassifyingBackRestoresTheOptions
  it("drops the product link for another menu and restores the card when changed back", () => {
    const whisky = card({ options: [{ volume: 30, price: 15000, bottle: false, sourceOptionId: "opt-1", label: null, fromDefault: true }] });
    const other = reclassify(whisky, 30);
    expect([other.type, other.linkedProductId, other.options[0]!.volume]).toEqual(["other", null, Number.NaN]);
    const back = reclassify(other, 30);
    expect([back.type, back.linkedProductId, back.options]).toEqual(["whisky", "product-1", whisky.options]);
  });

  // PhotoReviewRulesTest.kt otherToWhiskyRetainsSourceIdsPricesAndLabels
  it("keeps option IDs, prices and labels when another menu becomes a whisky", () => {
    const other = mapReview(review([otherLine({ options: [lineOption("o1", "잔", null, 9000)] })]), menu([]), 30).cards[0]!;
    const whisky = reclassify(other, 40);
    expect(whisky.options).toEqual([{ volume: 30, price: 9000, bottle: false, sourceOptionId: "o1", label: "잔", fromDefault: true }]);
    expect(whisky.match).toBe("new");
  });

  // PhotoReviewRulesTest.kt invalidOptionTextStaysVisibleUntilFixed
  it("keeps text that is not a number visible until it is fixed", () => {
    let edited = editOption(card(), "price", 0, "15,0a0");
    expect([optionFieldText(edited, "price", 0), edited.options[0]!.price]).toEqual(["15,0a0", Number.NaN]);
    expect(problems(edited, stateOf([edited]))).toContain("price");
    edited = editOption(edited, "price", 0, "16,000");
    expect([optionFieldText(edited, "price", 0), edited.options[0]!.price]).toEqual(["16000", 16000]);
  });

  // PhotoReviewRulesTest.kt bottleOptionsNeedNoVolume
  it("needs no volume for a bottle", () => {
    const bottle = toggleBottle(editOption(card(), "volume", 0, "abc"), 0, 30);
    expect([bottle.options[0]!.bottle, bottle.options[0]!.volume, bottle.rawEdits]).toEqual([true, 0, {}]);
    expect(problems(bottle, stateOf([bottle]))).not.toContain("volume");
  });

  // PhotoReviewRulesTest.kt crossPhotoDuplicateProductServingNeedsExplicitPriceCorrection
  it("flags two lines linked to one product with different prices for one serving", () => {
    const a = card({ id: "a", mergedInto: null });
    const b = card({ id: "b", options: [{ ...a.options[0]!, price: 17000 }] });
    const state = stateOf([a, b]);
    expect(problems(a, state)).toContain("duplicatePrice");
    // PhotoReviewRulesTest.kt differentProductOrDifferentServingDoesNotCauseFalsePhotoPriceConflict
    const c = card({ id: "c", options: [{ ...a.options[0]!, volume: 60, price: 17000 }] });
    expect(problems(a, stateOf([a, c]))).not.toContain("duplicatePrice");
  });

  // PhotoReviewRulesTest.kt sameNameOtherLinesWithSameOptionDifferentPricesNeedCorrection, sameNameOtherLinesWithDifferentOptionsMayMergeOnServer
  it("flags same-name other menus with different prices for one serving, but not different servings", () => {
    const other = (id: string, price: number, volume = Number.NaN) =>
      ({ ...mapReview(review([otherLine({ extractedItemId: id, extractedProductName: "하이볼" })]), menu([]), 30).cards[0]!, options: [{ volume, price, bottle: false, sourceOptionId: null, label: null, fromDefault: false }] });
    expect(problems(other("a", 9000), stateOf([other("a", 9000), other("b", 10000)]))).toContain("duplicatePrice");
    expect(problems(other("a", 9000), stateOf([other("a", 9000), other("b", 10000, 500)]))).not.toContain("duplicatePrice");
  });

  // PhotoReviewRulesTest.kt defaultPourChangesRefreshOnlyDefaultDerivedPrimaryAndSecondaryGlasses
  it("moves only the glasses that took the default when the default changes", () => {
    const base = card({
      options: [
        { volume: 30, price: 1, bottle: false, sourceOptionId: null, label: null, fromDefault: true },
        { volume: 60, price: 2, bottle: false, sourceOptionId: null, label: null, fromDefault: false },
        { volume: 0, price: 3, bottle: true, sourceOptionId: null, label: null, fromDefault: false },
      ],
    });
    expect(applyDefaultPour(base, 45).options.map((o) => o.volume)).toEqual([45, 60, 0]);
  });

  // PhotoReviewRulesTest.kt missingDefaultPourBlocksPublishingEvenWhenEverythingIsChecked
  it("cannot publish without a valid default pour", () => {
    const ready = card({ priceCandidates: [] });
    expect(reviewStats(stateOf([ready])).canPublish).toBe(true);
    expect(reviewStats(stateOf([ready], { defaultPour: 1000 }))).toMatchObject({ canPublish: false, noDefault: true });
  });

  // PhotoReviewRulesTest.kt unlinkedNameKeyMatchesBackendAgeAndPunctuationRules
  it("keys names without products as the server does", () => {
    expect(normalizedUnlinkedMenuName(" 글렌피딕 12년 ")).toBe(normalizedUnlinkedMenuName("글렌피딕12"));
    expect(normalizedUnlinkedMenuName("맥주 1")).toBe(normalizedUnlinkedMenuName("맥주1"));
    expect(normalizedUnlinkedMenuName("맥주-1")).not.toBe(normalizedUnlinkedMenuName("맥주1"));
    expect(normalizedUnlinkedMenuName("맥주 16.1")).not.toBe(normalizedUnlinkedMenuName("맥주 161"));
  });

  // PhotoReviewRulesTest.kt punctuationOnlyProductNameDoesNotUnlockPublish
  it("does not take a name of punctuation only", () => {
    expect(problems(card({ name: "!!!" }), stateOf([]))).toContain("name");
  });

  // PhotoReviewRulesTest.kt lateLinkingChecksEverySavedServingNotOnlyFirstOcrPrice
  it("asks about every saved serving of a product linked during the review", () => {
    const photo = card({
      linkedProductId: null,
      match: "candidate",
      matchConfirmed: false,
      options: [
        { volume: 30, price: 15000, bottle: false, sourceOptionId: null, label: null, fromDefault: false },
        { volume: 60, price: 26000, bottle: false, sourceOptionId: null, label: null, fromDefault: false },
      ],
      priceCandidates: [
        { servingKey: "ml:30", volumeMl: 30, bottle: false, label: null, priceKrw: 15000, existing: false, sourceItemId: null },
        { servingKey: "ml:60", volumeMl: 60, bottle: false, label: null, priceKrw: 26000, existing: false, sourceItemId: null },
      ],
    });
    const saved = {
      product: [
        { servingKey: "ml:30", volumeMl: 30, bottle: false, label: null, priceKrw: 12000, existing: true, sourceItemId: null },
        { servingKey: "ml:60", volumeMl: 60, bottle: false, label: null, priceKrw: 23000, existing: true, sourceItemId: null },
      ],
    };
    const linked = markLinked(photo, { productId: "product", name: "글렌피딕 12년" }, saved);
    expect(pendingPriceServings(linked, saved)).toHaveLength(2);
    const first = chooseServingPrice(linked, "ml:30", 15000, saved);
    expect(pendingPriceServings(first, saved)).toEqual(["ml:60"]);
    const second = chooseServingPrice(first, "ml:60", 23000, saved);
    expect(pendingPriceServings(second, saved)).toEqual([]);
    expect(second.options[1]!.price).toBe(23000);
  });

  // PhotoReviewRulesTest.kt changingGlassToBottleRechecksSavedBottlePrice
  it("checks the saved bottle price again after a glass becomes a bottle", () => {
    const saved = { "product-1": [{ servingKey: "bottle", volumeMl: null, bottle: true, label: null, priceKrw: 130000, existing: true, sourceItemId: null }] };
    const bottle = toggleBottle(card({ priceCandidates: [] }), 0, 30);
    expect(pendingPriceServings(bottle, saved)).toHaveLength(1);
    expect(new Set(priceCandidatesForServing(bottle, "bottle", saved).map((c) => c.priceKrw))).toEqual(new Set([15000, 130000]));
    expect(pendingPriceServings(chooseServingPrice(bottle, "bottle", 130000, saved), saved)).toEqual([]);
  });

  // PhotoReviewRulesTest.kt mergedNoticeCountsTheRealNumberOfLines
  it("counts the merged lines in words", () => {
    const source = { id: "x", photoIndex: 1, sourceLine: 1, raw: "", recognizedName: "", offers: [], sourceBox: null };
    expect(mergedNotice(card())).toBeNull();
    expect(mergedNotice(card({ mergeSources: [source, source] }))).toBe("같은 위스키가 세 줄 있어 하나로 합쳤어요.");
    expect(mergedNotice(card({ mergeSources: Array(10).fill(source) }))).toBe("같은 위스키가 11줄 있어 하나로 합쳤어요.");
  });
});

describe("final options (OwnerReviewOptionContract.kt)", () => {
  const lineWith = line({ options: [lineOption("first", "잔", null, 20000, 1), lineOption("second", "병", null, 180000, 2)] });
  const chosen = (id: string | null, label: string | null, pourMl: number | null, priceKrw: number) => ({ extractedOptionId: id, label, pourMl, priceKrw });

  // OwnerReviewOptionContractTest.kt fullFinalListKeepsActualOcrIdAndMarksNewOptionAsUnlinked
  it("keeps extracted option IDs and sends an added option without one", () => {
    const result = finalReviewOptions(lineWith, [chosen("first", "잔", 45, 21000), chosen("manual-added", "다른 잔", 60, 35000)], 30, true);
    expect(result).toEqual([
      { extractedOptionId: "first", optionLabel: null, pourMl: 45, priceKrw: 21000 },
      { extractedOptionId: null, optionLabel: null, pourMl: 60, priceKrw: 35000 },
    ]);
  });

  // OwnerReviewOptionContractTest.kt defaultPourOnlyAppliesToUnspecifiedWhiskyGlass
  it("gives the default pour to a whisky glass only", () => {
    const options = [chosen("first", "잔", null, 20000), chosen("second", "병", null, 180000)];
    expect(finalReviewOptions(lineWith, options, 35, true).map((o) => o.pourMl)).toEqual([35, null]);
    expect(finalReviewOptions(lineWith, options, 35, false)[0]!.pourMl).toBeNull();
  });

  // OwnerReviewOptionContractTest.kt duplicateOcrIdentityIsRejectedBeforeNetworkWrite, invalidPricesAndMoreThanTenOptionsAreRejected
  it("refuses one extracted option twice, a missing price and more than ten options", () => {
    expect(() => finalReviewOptions(lineWith, [chosen("first", "잔", 30, 20000), chosen("first", "잔", 45, 25000)], 30, true)).toThrow(ReviewSubmitError);
    expect(() => finalReviewOptions(lineWith, [chosen("first", "잔", 30, 0)], 30, true)).toThrow(ReviewSubmitError);
    const eleven = Array.from({ length: 11 }, (_, i) => chosen(null, `잔 ${i}`, (i + 1) * 10, (i + 1) * 1000));
    expect(() => finalReviewOptions(lineWith, eleven, 30, true)).toThrow(ReviewSubmitError);
  });

  // OwnerReviewOptionContractTest.kt glassLabelsAreIgnoredInFinalServerOptionsButOcrIdsRemain, sameMlWithDifferentLabelsCannotBePublishedTwice
  it("sends a glass by its ml without its word, and refuses two of one ml", () => {
    const options = finalReviewOptions(lineWith, [chosen("first", "샷", 30, 20000), chosen("second", "잔", 60, 35000)], 35, true);
    expect(options.map((o) => [o.extractedOptionId, o.pourMl, o.optionLabel])).toEqual([
      ["first", 30, null],
      ["second", 60, null],
    ]);
    expect(() => finalReviewOptions(lineWith, [chosen("first", "잔", 30, 20000), chosen("second", "샷", 30, 25000)], 30, true)).toThrow(ReviewSubmitError);
    const bottle = finalReviewOptions(lineWith, [chosen("first", "샷", 30, 20000), chosen("second", "병", null, 180000)], 30, true);
    expect(bottle[1]).toMatchObject({ optionLabel: "Bottle", pourMl: null });
  });

  // OwnerReviewOptionContractTest.kt existingServerOptionIsUpdatedByMlWithoutChangingItsStoredLabel
  it("updates the bar's saved serving of that ml under its saved label", () => {
    const result = finalReviewOptions(lineWith, [chosen("first", "잔", 30, 22000)], 30, true, [savedOption("server", "샷", 30, 19000)]);
    expect(result).toEqual([{ extractedOptionId: "first", optionLabel: "샷", pourMl: 30, priceKrw: 22000 }]);
  });

  // OwnerReviewOptionContractTest.kt ambiguousLegacySameMlOptionsCannotBeSilentlyOverwritten
  it("refuses when the bar has two saved options of that ml", () => {
    const saved = [savedOption("one", "잔", 30, 18000), savedOption("two", "샷", 30, 19000)];
    expect(() => finalReviewOptions(lineWith, [chosen("first", "잔", 30, 22000)], 30, true, saved)).toThrow(ReviewSubmitError);
  });

  // OwnerReviewOptionContractTest.kt existingLegacySizedBottleKeepsItsServerKey
  it("keeps a saved bottle's label and capacity", () => {
    const result = finalReviewOptions(lineWith, [chosen("second", "Bottle", null, 130000)], 30, true, [savedOption("b", "병", 700, 100000)]);
    expect(result[0]).toMatchObject({ optionLabel: "병", pourMl: 700 });
  });

  // OwnerReviewOptionContractTest.kt partialUpdateKeepsUnphotographedServingsAndTheirServerIdentity
  it("sends the bar's servings the photo does not show exactly as saved, so they and their discounts stay", () => {
    const saved = [
      savedOption("saved-30", "잔", 30, 18000),
      savedOption("saved-60", "샷", 60, 34000, { discountedPriceKrw: 30000, startsAt: "2026-11-01T00:00:00Z", endsAt: "2026-12-01T00:00:00Z" }),
      savedOption("saved-bottle", "병", 700, 130000),
    ];
    const result = finalReviewOptions(lineWith, [chosen("first", "잔", 30, 22000)], 30, true, saved);
    expect(result).toEqual([
      { extractedOptionId: "first", optionLabel: "잔", pourMl: 30, priceKrw: 22000 },
      { extractedOptionId: null, optionLabel: "샷", pourMl: 60, priceKrw: 34000 },
      { extractedOptionId: null, optionLabel: "병", pourMl: 700, priceKrw: 130000 },
    ]);
  });

  // OwnerReviewOptionContractTest.kt partialUpdateRefusesToDropServingIfCombinedOptionsExceedBackendLimit
  it("refuses rather than drop a saved serving past ten options", () => {
    const saved = Array.from({ length: 10 }, (_, i) => savedOption(`s${i}`, "잔", (i + 1) * 30 + 30, 10001 + i));
    expect(() => finalReviewOptions(lineWith, [chosen("first", "잔", 30, 22000)], 30, true, saved)).toThrow(ReviewSubmitError);
  });

  // OwnerReviewOptionContractTest.kt groupedProposedChangeAppliesWhenOnlyLaterOcrLineIsPublished
  it("applies a change when any of its lines is published, and never a removal", () => {
    const grouped = { changeType: "update" as const, extractedItemId: "line-a", extractedItemIds: ["line-a", "line-b"] };
    expect(changeDecision(grouped, new Set(["line-b"]))).toBe("apply");
    expect(changeDecision(grouped, new Set())).toBe("ignore");
    expect(changeDecision({ ...grouped, extractedItemIds: [] }, new Set(["line-a"]))).toBe("apply");
    expect(changeDecision({ ...grouped, changeType: "remove" }, new Set(["line-a", "line-b"]))).toBe("ignore");
  });

  // OwnerReviewOptionContractTest.kt groupedOtherRetentionDoesNotReintroduceOldPriceInBottleLine
  it("gives a saved serving to the line that updates it, and untouched ones to the first line only", () => {
    const saved = [savedOption("old-30", "샷", 30, 8000), savedOption("old-60", "잔", 60, 20000)];
    const keys = new Map([
      ["photo-30", new Set(["ml:30"])],
      ["photo-bottle", new Set(["bottle"])],
    ]);
    const group = ["photo-30", "photo-bottle"];
    expect(retainedForGroupedLine("photo-30", group, keys, saved).map((o) => o.menuEntryOptionId)).toEqual(["old-30", "old-60"]);
    expect(retainedForGroupedLine("photo-bottle", group, keys, saved)).toEqual([]);
  });

  // OwnerReviewOptionContractTest.kt catalogLinkToExistingUnlinkedMenuRetainsUnseenOptions
  it("keeps the options of the item without a product that a line now links", () => {
    const local = menu([menuItem({ barMenuItemId: "existing-x", options: [savedOption("old-30", "샷", 30, 12000), savedOption("old-bottle", "병", null, 130000)] })]);
    const changes = [{ changeId: "c", changeType: "update" as const, barMenuItemId: "existing-x", extractedItemId: "photo-30", extractedItemIds: ["photo-30", "photo-bottle"], before: null, after: null, summary: "", decision: "pending" as const }];
    expect(existingOptionsForProduct(local, changes, "photo-bottle", "catalog-p").map((o) => o.menuEntryOptionId)).toEqual(["old-30", "old-bottle"]);
  });

  it("sends the bar's other servings of a linked whisky with the photo's price (partial update keeps them)", () => {
    const data = review([line({ options: [lineOption("ocr-30", null, 30, 15000)] })]);
    const saved = menu([menuItem({ barMenuItemId: "row-1", productId: "product-1", options: [savedOption("s30", null, 30, 12000), savedOption("s60", null, 60, 22000)] })]);
    const state = mapReview(data, saved, 30);
    const chosenCard = chooseServingPrice(state.cards[0]!, "ml:30", 15000, state.savedByProduct);
    expect((reviewBody(data, update(state, chosenCard), saved).itemDecisions[0]! as { options: unknown[] }).options).toEqual([
      { extractedOptionId: "ocr-30", optionLabel: null, pourMl: 30, priceKrw: 15000 },
      { extractedOptionId: null, optionLabel: null, pourMl: 60, priceKrw: 22000 },
    ]);
  });
});

describe("the review draft (ServerReviewDraftCodec.kt)", () => {
  const data = review([line(), unmatchedLine({ extractedItemId: "line-2", itemOrder: 2, extractedProductName: "새 위스키", newProductDraft: null })]);

  it("comes back as it was saved on this web, numbers not yet valid included", () => {
    const fresh = mapReview(data, menu(), 30);
    let edited = update(fresh, chooseServingPrice(fresh.cards[0]!, "ml:30", 12000, fresh.savedByProduct));
    edited = update(edited, editOption(confirmNew(edited.cards[1]!), "price", 0, "abc"));
    const content = JSON.parse(JSON.stringify(encodeDraft(edited))) as Record<string, unknown>;
    expect(JSON.stringify(content)).not.toContain("signed.example");
    const restored = restoreDraft(fresh, data, { reviewVersion: 3, content });
    expect(restored.cards.map((c) => [c.options[0]!.price, c.chosenServingPrices, c.nameSaved])).toEqual([
      [12000, { "ml:30": 12000 }, true],
      [Number.NaN, {}, true],
    ]);
    expect(optionFieldText(restored.cards[1]!, "price", 0)).toBe("abc");
    expect(restored.cards[0]!.raw).toBe(fresh.cards[0]!.raw);
  });

  // ServerReviewDraftCodec.kt partialDecision: what the app and the operator web read
  it("writes each line's decision so far as a partial 8.1 decision", () => {
    const fresh = mapReview(data, menu(), 30);
    expect(partialDecision(fresh.cards[0]!)).toEqual({
      extractedItemId: "line-1",
      correctedProductName: "위스키 12년",
      finalLineType: "product",
      options: [{ extractedOptionId: "opt-1", optionLabel: null, pourMl: 30, priceKrw: 15000 }],
      action: "select_existing_product",
      productId: "product-1",
    });
    expect(partialDecision({ ...fresh.cards[1]!, excluded: true })).toEqual({ extractedItemId: "line-2", action: "reject" });
  });

  it("applies another client's decisions whose lines and options are still in the review", () => {
    const fresh = mapReview(data, menu(), 30);
    const content = {
      itemDecisions: [
        { extractedItemId: "line-1", action: "select_existing_product", productId: "product-1", options: [{ extractedOptionId: "opt-1", optionLabel: null, pourMl: 30, priceKrw: 12000 }] },
        { extractedItemId: "line-2", action: "publish_without_product", kind: "other", correctedProductName: "하이볼", options: [{ extractedOptionId: "gone", priceKrw: 9000 }] },
        { extractedItemId: "line-9", action: "reject" },
      ],
      changeDecisions: [{ changeId: "old", decision: "apply" }],
      clientState: { androidSchemaVersion: 1, androidStateJson: "{}" },
    };
    const restored = restoreDraft(fresh, data, { reviewVersion: 2, content });
    expect(restored.cards[0]!.options[0]!.price).toBe(12000);
    expect(pendingPriceServings(restored.cards[0]!, restored.savedByProduct)).toEqual([]);
    // The option it named is not in this review: its options stay as read; its kind and name apply.
    expect([restored.cards[1]!.type, restored.cards[1]!.name, restored.cards[1]!.options[0]!.sourceOptionId]).toEqual(["other", "하이볼", "opt-1"]);
    expect(restored.cards).toHaveLength(2);
  });

  it("excludes a line another client rejected", () => {
    const fresh = mapReview(data, menu(), 30);
    const restored = restoreDraft(fresh, data, { reviewVersion: 3, content: { itemDecisions: [{ extractedItemId: "line-2", action: "reject" }] } });
    expect(restored.cards[1]!.excluded).toBe(true);
  });
});

describe("a product picked from the candidates or the search", () => {
  it("links it and checks that product's saved prices", () => {
    const data = review([line({ initialResolutionStatus: "ambiguous", proposedProductId: "product-1", candidates: [candidate("product-1", "Whisky 12"), candidate("product-2", "Whisky 15", 2)] })]);
    const saved = menu([menuItem({ barMenuItemId: "r2", productId: "product-2", options: [savedOption("s", null, 30, 18000)] })]);
    const state = mapReview(data, saved, 30);
    expect(problems(state.cards[0]!, state)).toContain("candidate");
    const linked = markLinked(state.cards[0]!, { productId: "product-2", name: "Whisky 15" }, state.savedByProduct);
    expect(problems(linked, update(state, linked))).toEqual(["priceChoice"]);
    const body = reviewBody(data, update(state, chooseServingPrice(linked, "ml:30", 15000, state.savedByProduct)), saved);
    expect(body.itemDecisions[0]!).toMatchObject({ action: "select_existing_product", productId: "product-2", correctedProductName: null });
  });
});
