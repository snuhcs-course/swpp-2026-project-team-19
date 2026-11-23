import type { components } from "../../api/schema";
import type { BarMenu } from "../../owner/queries";
import { isBottleServingLabel, servingIdentityKey } from "../../menu/servingIdentity";
import { validPrice, validVolume, type PriceCandidate, type ReviewCard, type ReviewOption, type ReviewState } from "./model";
import { normalizedUnlinkedMenuName, servingKey } from "./rules";

export type ImportReview = components["schemas"]["ImportReviewResponse"];
export type ReviewLine = components["schemas"]["ReviewItem"];
type SavedOption = BarMenu["items"][number]["options"][number];

/**
 * The review cards from the review response (5.4) and the bar's current menu (3.9), ported from
 * android/.../data/owner/review/LivePhotoReviewMapping.kt (`mapServerPhotoReview`) and
 * LiveWhiskyReviewGrouping.kt (`groupLiveWhiskyReview`).
 */
export function mapReview(review: ImportReview, menu: BarMenu, defaultPourMl: number | null): ReviewState {
  const defaultPour = defaultPourMl ?? 30;
  const lines = [...review.images]
    .sort((a, b) => a.imageOrder - b.imageOrder)
    .flatMap((image) => [...image.items].sort((a, b) => a.itemOrder - b.itemOrder).map((line) => ({ line, image })));
  const savedByProduct: Record<string, PriceCandidate[]> = {};
  for (const item of menu.items) {
    if (item.productId === null) continue;
    savedByProduct[item.productId] = [...(savedByProduct[item.productId] ?? []), ...item.options.map(savedCandidate)];
  }
  const mapped = lines.map(({ line, image }) => ({ line, card: mapLine(line, image.imageOrder, menu, defaultPour) }));
  return { cards: groupSameWhisky(mapped, menu), defaultPour, savedByProduct };
}

export function savedCandidate(option: Pick<SavedOption, "pourMl" | "optionLabel" | "priceKrw">): PriceCandidate {
  return {
    servingKey: servingIdentityKey(option.pourMl, option.optionLabel),
    volumeMl: option.pourMl,
    bottle: isBottleServingLabel(option.optionLabel),
    label: option.optionLabel,
    priceKrw: option.priceKrw,
    existing: true,
    sourceItemId: null,
  };
}

/**
 * `ownerExistingUnlinkedOptions`: the options of the bar's item without a product whose name key is `name`'s
 * (3.14.1), or none. Two such items cannot be told apart, so that is refused.
 */
export function existingUnlinkedOptions(menu: BarMenu, name: string): SavedOption[] {
  const key = normalizedUnlinkedMenuName(name);
  if (key === "") return [];
  const matches = menu.items.filter((item) => item.productId === null && normalizedUnlinkedMenuName(item.displayName) === key);
  if (matches.length > 1) throw new Error("기존 메뉴에 같은 이름의 항목이 중복돼 있어요. 메뉴 관리에서 확인해 주세요.");
  return matches[0]?.options ?? [];
}

/** A missing pour takes the bar's default only for an explicit glass (or any whisky serving). */
const isGlass = (label: string | null): boolean => /^(잔|샷|glass|shot)/.test(label?.trim().toLowerCase() ?? "");

function mapLine(line: ReviewLine, photoIndex: number, menu: BarMenu, defaultPour: number): ReviewCard {
  const recognized = [...line.options].sort((a, b) => a.optionOrder - b.optionOrder);
  const proposed = line.candidates.find((candidate) => candidate.productId === line.proposedProductId);
  const category = line.extractedKind ?? proposed?.category ?? line.newProductDraft?.category ?? "whisky";
  const nonProduct = line.effectiveLineType !== "product" && line.effectiveLineType !== "unknown";
  const other = nonProduct || category.toLowerCase() !== "whisky";
  const match = other
    ? "new"
    : line.initialResolutionStatus === "exact_match" && line.proposedProductId !== null
      ? "exact"
      : line.candidates.length > 1
        ? "candidate"
        : line.candidates.length === 1
          ? "ambiguous"
          : "new";
  const linkedId = match === "exact" ? line.proposedProductId : null;
  const options: ReviewOption[] = recognized.map((option) => {
    const bottle = isBottleServingLabel(option.extractedOptionLabel);
    const takesDefault = option.extractedPourMl === null && !bottle && (!other || isGlass(option.extractedOptionLabel));
    return {
      volume: bottle ? 0 : (option.extractedPourMl ?? (takesDefault ? defaultPour : Number.NaN)),
      price: option.extractedPriceKrw ?? 0,
      bottle,
      sourceOptionId: option.extractedOptionId,
      label: option.extractedOptionLabel,
      fromDefault: takesDefault,
    };
  });
  // The raw text is evidence, not a menu name: it can hold prices. A line without a name waits for the owner's.
  const name = line.extractedProductName?.trim() || line.newProductDraft?.displayName?.trim() || "";
  // The bar's item without a product of the same name is updated by name (3.14.1): its prices take part.
  const oldUnlinked = linkedId === null && name !== "" ? existingUnlinkedOptions(menu, name) : [];
  const priceCandidates: PriceCandidate[] =
    oldUnlinked.length === 0
      ? []
      : [
          ...options.flatMap((option) =>
            validPrice(option.price)
              ? [
                  {
                    servingKey: servingKey(option),
                    volumeMl: validVolume(option.volume) ? option.volume : null,
                    bottle: option.bottle,
                    label: option.label,
                    priceKrw: option.price,
                    existing: false,
                    sourceItemId: line.extractedItemId,
                  },
                ]
              : [],
          ),
          ...oldUnlinked.map(savedCandidate),
        ];
  return {
    id: line.extractedItemId,
    name,
    recognizedName: name,
    type: other ? "other" : "whisky",
    match,
    matchConfirmed: linkedId !== null,
    newConfirmed: linkedId !== null || other,
    nameSaved: name !== "" && (linkedId !== null || other),
    linkedProductId: linkedId,
    linkedProductName: linkedId !== null ? (proposed?.displayName ?? null) : null,
    candidates: [...line.candidates]
      .sort((a, b) => a.candidateRank - b.candidateRank)
      .map((candidate) => ({ productId: candidate.productId, name: candidate.displayName, isActive: true })),
    options,
    rawEdits: {},
    priceCandidates,
    chosenServingPrices: {},
    volumeChoices: [],
    chosenVolumeKeys: [],
    volumeChoicesConfirmed: true,
    excluded: nonProduct,
    required: !nonProduct,
    mergedInto: null,
    mergeSources: [],
    preMergeOptions: [],
    manuallySplit: false,
    operatorReason: null,
    classificationSnapshot: null,
    searchMode: false,
    nameEditing: false,
    raw: line.rawText,
    photoIndex,
    sourceLine: line.itemOrder,
    sourceBox: line.sourceBox?.length === 4 ? line.sourceBox : null,
    recognizedOffers: recognized.map((option) => ({
      volumeMl: option.extractedPourMl,
      bottle: isBottleServingLabel(option.extractedOptionLabel),
      priceKrw: option.extractedPriceKrw,
    })),
  };
}

/**
 * `groupLiveWhiskyReview`: the lines of one whisky (same product, or same name without one) become one card.
 * Each line keeps its own decision: the first publishes every serving, the others are sent as `reject` once
 * their servings are in the first (8.12). A serving with different prices on the lines, or a different price
 * on the bar's menu, is chosen once; more than three servings are picked down to three.
 */
function groupSameWhisky(mapped: { line: ReviewLine; card: ReviewCard }[], menu: BarMenu): ReviewCard[] {
  const identity = ({ line, card }: { line: ReviewLine; card: ReviewCard }): string => {
    if (card.type !== "whisky" || (line.effectiveLineType !== "product" && line.effectiveLineType !== "unknown")) return `line:${card.id}`;
    const productId = card.linkedProductId ?? line.proposedProductId ?? (line.candidates.length === 1 ? (line.candidates[0]?.productId ?? null) : null);
    if (productId) return `product:${productId}`;
    const name = card.name.normalize("NFKC").toLowerCase().replace(/\s+/g, "");
    return name !== "" ? `name:${name}` : `line:${card.id}`;
  };
  const batches = new Map<string, { line: ReviewLine; card: ReviewCard }[]>();
  for (const entry of mapped) {
    const key = identity(entry);
    batches.set(key, [...(batches.get(key) ?? []), entry]);
  }
  return [...batches.values()].flatMap((batch) => {
    const head = batch[0]?.card;
    if (!head) return [];
    if (head.type !== "whisky") return batch.map((entry) => entry.card);
    const all = batch.flatMap(({ card }) => card.options.map((option) => ({ lineId: card.id, option })));
    if (all.length === 0) return batch.map((entry) => entry.card);
    const firstByServing = new Map<string, { lineId: string; option: ReviewOption }>();
    for (const offer of all) if (!firstByServing.has(servingKey(offer.option))) firstByServing.set(servingKey(offer.option), offer);
    // Extracted option IDs belong to one line: a serving taken from another line is the owner's new option.
    const unique = [...firstByServing.values()].map(({ lineId, option }) => ({
      ...option,
      sourceOptionId: lineId === head.id ? option.sourceOptionId : null,
    }));
    const productId = batch.map(({ line, card }) => card.linkedProductId ?? line.proposedProductId).find((id) => id) ?? null;
    const existing = menu.items.filter((item) => productId !== null && item.productId === productId).flatMap((item) => item.options);
    const seen = new Set<string>();
    const candidates = [
      ...all.flatMap(({ lineId, option }) =>
        validPrice(option.price)
          ? [
              {
                servingKey: servingKey(option),
                volumeMl: validVolume(option.volume) ? option.volume : null,
                bottle: option.bottle,
                label: option.label,
                priceKrw: option.price,
                existing: false,
                sourceItemId: lineId,
              },
            ]
          : [],
      ),
      ...existing.map(savedCandidate),
      ...batch.flatMap(({ card }) => card.priceCandidates.filter((candidate) => candidate.existing)),
    ].filter((candidate) => {
      const key = `${candidate.servingKey}|${candidate.priceKrw}|${candidate.existing}|${candidate.sourceItemId}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    const tooMany = unique.length > 3;
    const master: ReviewCard = {
      ...head,
      options: tooMany ? [] : unique,
      priceCandidates: candidates,
      chosenServingPrices: {},
      volumeChoices: tooMany ? unique : [],
      chosenVolumeKeys: [],
      volumeChoicesConfirmed: !tooMany,
      preMergeOptions: batch.length > 1 ? head.options : [],
      mergeSources: batch.slice(1).map(({ card }) => ({
        id: card.id,
        photoIndex: card.photoIndex,
        sourceLine: card.sourceLine,
        raw: card.raw,
        recognizedName: card.recognizedName,
        offers: card.recognizedOffers,
        sourceBox: card.sourceBox,
      })),
    };
    const children = batch.slice(1).map(({ card }) => ({ ...card, excluded: true, required: false, mergedInto: head.id }));
    return [master, ...children];
  });
}

/**
 * "서로 다른 위스키예요" (PhotoReviewViewModel.kt `splitMerged`): the lines of a merged card become cards of
 * their own again, each with its own servings. `unlinkedPrices` gives the saved prices of the bar's item
 * without a product of a name, for a line without a product.
 */
export function splitMerged(
  state: ReviewState,
  id: string,
  unlinkedPrices: (name: string) => PriceCandidate[],
): ReviewState {
  const master = state.cards.find((card) => card.id === id);
  if (!master || master.mergeSources.length === 0) return state;
  const rebind = (card: ReviewCard): ReviewCard => {
    if (card.linkedProductId !== null) return card;
    const saved = unlinkedPrices(card.name);
    const active = new Set(card.options.map(servingKey));
    const fromPhoto = card.priceCandidates.filter((candidate) => !candidate.existing && active.has(candidate.servingKey));
    return { ...card, priceCandidates: [...saved.filter((c) => active.has(c.servingKey)), ...fromPhoto], chosenServingPrices: {} };
  };
  return {
    ...state,
    cards: state.cards.map((card) => {
      if (card.id === id) {
        return rebind({
          ...card,
          mergeSources: [],
          manuallySplit: true,
          options: card.preMergeOptions,
          preMergeOptions: [],
          priceCandidates: card.priceCandidates.filter((candidate) => !candidate.existing && candidate.sourceItemId === id),
          chosenServingPrices: {},
          volumeChoices: [],
          chosenVolumeKeys: [],
          volumeChoicesConfirmed: true,
          rawEdits: {},
        });
      }
      if (card.mergedInto === id) return rebind({ ...card, mergedInto: null, excluded: false, required: true, manuallySplit: true });
      return card;
    }),
  };
}
