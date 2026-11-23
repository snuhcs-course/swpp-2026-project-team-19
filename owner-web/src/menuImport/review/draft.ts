import { isBottleServingLabel } from "../../menu/servingIdentity";
import { validPrice, validVolume, type PriceCandidate, type ReviewCard, type ReviewOption, type ReviewState } from "./model";
import { splitMerged, type ImportReview } from "./mapping";
import { applyDefaultPour, confirmNew, markLinked, priceCandidatesForServing, reclassify, servingKey, validMenuName } from "./rules";

/**
 * The review draft (spec 5.9), so the review can be left and continued on another device, ported from
 * android/.../data/owner/review/ServerReviewDraftCodec.kt.
 *
 * `itemDecisions` are partial 8.1 decisions every client reads; `clientState.web` is this web's own copy of the
 * cards, which other clients ignore (the app keeps its own under `androidStateJson`). It holds no image URL.
 */
export type DraftContent = {
  itemDecisions: Record<string, unknown>[];
  changeDecisions: unknown[];
  clientState: { webSchemaVersion: 1; cards: SavedCard[]; expandedItemIds: string[] };
};

/** A card without what the review response gives again (the photo text, servings read and position). */
type SavedCard = Omit<ReviewCard, "raw" | "recognizedOffers" | "sourceBox" | "mergeSources"> & { mergeSources: { id: string }[] };

export const MAX_DRAFT_BYTES = 262_144;

/** `partialDecision`: what the card has decided so far, as a partial 8.1 decision. */
export function partialDecision(card: ReviewCard): Record<string, unknown> {
  if (card.excluded) return { extractedItemId: card.id, action: "reject" };
  const decision: Record<string, unknown> = { extractedItemId: card.id };
  if (card.name.trim() !== "") decision.correctedProductName = card.name;
  decision.finalLineType = "product";
  const options = card.options
    .filter((option) => validPrice(option.price))
    .map((option) => ({
      extractedOptionId: option.sourceOptionId,
      optionLabel: option.bottle ? "Bottle" : option.label,
      pourMl: option.bottle ? null : validVolume(option.volume) ? option.volume : null,
      priceKrw: option.price,
    }));
  if (options.length > 0 || card.options.length === 0) decision.options = options;
  if (options.length > 0 && card.name.trim() !== "") {
    if (card.linkedProductId !== null && card.matchConfirmed) {
      decision.action = "select_existing_product";
      decision.productId = card.linkedProductId;
    } else if (card.type === "other" || (card.nameSaved && card.newConfirmed)) {
      decision.action = "publish_without_product";
      decision.kind = card.type === "other" ? "other" : "whisky";
    }
  }
  return decision;
}

export function encodeDraft(state: ReviewState): DraftContent {
  const cards: SavedCard[] = state.cards.map(({ raw: _raw, recognizedOffers: _offers, sourceBox: _box, mergeSources, ...card }) => ({
    ...card,
    mergeSources: mergeSources.map((line) => ({ id: line.id })),
  }));
  return {
    itemDecisions: state.cards.map(partialDecision),
    changeDecisions: [],
    clientState: { webSchemaVersion: 1, cards, expandedItemIds: [] },
  };
}

/** The size of the content as sent; above 256 KB the server refuses it (413 REVIEW_DRAFT_TOO_LARGE). */
export const draftBytes = (content: unknown): number => new TextEncoder().encode(JSON.stringify(content)).length;

// JSON has no NaN: a number field that was not valid comes back as null.
const num = (value: unknown): number => (typeof value === "number" ? value : Number.NaN);
const reviveOption = (option: ReviewOption): ReviewOption => ({ ...option, volume: num(option.volume), price: num(option.price) });

function webCards(content: Record<string, unknown>): SavedCard[] | null {
  const client = content.clientState as { webSchemaVersion?: unknown; cards?: unknown } | undefined;
  if (!client || client.webSchemaVersion !== 1 || !Array.isArray(client.cards)) return null;
  return client.cards as SavedCard[];
}

/**
 * The cards with a saved draft applied. This web's own cards come back as they were when the draft belongs to
 * this review version and has the same lines; otherwise (a draft of the app or the operator web, or a review
 * built again, 9.4) each line's decision is applied when its line and options are still in the review, and
 * proposed-change decisions are dropped (5.4).
 */
export function restoreDraft(
  fresh: ReviewState,
  review: ImportReview,
  draft: { reviewVersion: number; content: Record<string, unknown> },
  unlinkedPrices: (name: string) => PriceCandidate[] = () => [],
): ReviewState {
  const saved = webCards(draft.content);
  const freshById = new Map(fresh.cards.map((card) => [card.id, card]));
  if (
    saved &&
    draft.reviewVersion === review.reviewVersion &&
    saved.length === fresh.cards.length &&
    saved.every((card) => freshById.has(card.id))
  ) {
    return {
      ...fresh,
      cards: saved.map((card) => {
        const current = freshById.get(card.id) as ReviewCard;
        const restored: ReviewCard = {
          ...card,
          options: card.options.map(reviveOption),
          volumeChoices: card.volumeChoices.map(reviveOption),
          preMergeOptions: card.preMergeOptions.map(reviveOption),
          classificationSnapshot: card.classificationSnapshot
            ? { ...card.classificationSnapshot, options: card.classificationSnapshot.options.map(reviveOption) }
            : null,
          raw: current.raw,
          recognizedOffers: current.recognizedOffers,
          sourceBox: current.sourceBox,
          photoIndex: current.photoIndex,
          sourceLine: current.sourceLine,
          mergeSources: card.mergeSources.flatMap((line) => {
            const source = freshById.get(line.id);
            return source
              ? [{ id: source.id, photoIndex: source.photoIndex, sourceLine: source.sourceLine, raw: source.raw, recognizedName: source.recognizedName, offers: source.recognizedOffers, sourceBox: source.sourceBox }]
              : [];
          }),
        };
        return applyDefaultPour(restored, fresh.defaultPour);
      }),
    };
  }
  const decisions = Array.isArray(draft.content.itemDecisions) ? (draft.content.itemDecisions as Record<string, unknown>[]) : [];
  const lineOptions = new Map(
    review.images.flatMap((image) => image.items.map((line) => [line.extractedItemId, new Set(line.options.map((o) => o.extractedOptionId))] as const)),
  );
  const byId = new Map(decisions.filter((d) => typeof d.extractedItemId === "string").map((d) => [d.extractedItemId as string, d]));
  // A line this review merged into another card but the draft decided on its own (another client did not merge it):
  // the group is split first, so that decision applies to that line alone (the app refuses such a draft).
  let split = fresh;
  for (const master of new Set(fresh.cards.filter((card) => card.mergedInto !== null && byId.has(card.id)).map((card) => card.mergedInto as string))) {
    split = splitMerged(split, master, unlinkedPrices);
  }
  return {
    ...split,
    cards: split.cards.map((card) => {
      const decision = byId.get(card.id);
      if (!decision || card.mergedInto !== null) return card;
      return applyStandardDecision(card, decision, lineOptions.get(card.id) ?? new Set(), split);
    }),
  };
}

function applyStandardDecision(card: ReviewCard, decision: Record<string, unknown>, optionIds: ReadonlySet<string>, state: ReviewState): ReviewCard {
  const action = decision.action;
  if (action === "reject" || action === "confirm_non_product") return { ...card, excluded: true };
  let next = card;
  if (typeof decision.correctedProductName === "string" && validMenuName(decision.correctedProductName)) {
    next = { ...next, name: decision.correctedProductName.trim() };
  }
  // An empty list is a decision too: every serving was removed, so the card asks for one again.
  if (Array.isArray(decision.options)) {
    const options = decision.options as { extractedOptionId?: unknown; optionLabel?: unknown; pourMl?: unknown; priceKrw?: unknown }[];
    const known = options.every((o) => o.extractedOptionId === null || o.extractedOptionId === undefined || optionIds.has(o.extractedOptionId as string));
    if (known && options.every((o) => typeof o.priceKrw === "number")) {
      next = {
        ...next,
        rawEdits: {},
        volumeChoices: [],
        chosenVolumeKeys: [],
        volumeChoicesConfirmed: true,
        options: options.map((o) => {
          const label = typeof o.optionLabel === "string" ? o.optionLabel : null;
          const bottle = isBottleServingLabel(label);
          return {
            volume: bottle ? 0 : typeof o.pourMl === "number" ? o.pourMl : Number.NaN,
            price: o.priceKrw as number,
            bottle,
            sourceOptionId: typeof o.extractedOptionId === "string" ? o.extractedOptionId : null,
            label,
            fromDefault: false,
          };
        }),
      };
    }
  }
  if (action === "select_existing_product" && typeof decision.productId === "string") {
    const productId = decision.productId;
    const name = card.candidates.find((c) => c.productId === productId)?.name ?? card.linkedProductName ?? next.name;
    if (next.type === "other") next = reclassify(next, state.defaultPour);
    next = markLinked({ ...next, excluded: false }, { productId, name }, state.savedByProduct);
  } else if (action === "publish_without_product") {
    const kind = decision.kind === "other" ? "other" : "whisky";
    if (next.type !== kind) next = reclassify(next, state.defaultPour);
    next = { ...next, excluded: false };
    if (kind === "whisky") next = confirmNew(next);
  }
  // A price the draft holds for a serving with several prices counts as the owner's choice.
  const chosen: Record<string, number> = {};
  for (const option of next.options) {
    const key = servingKey(option);
    const prices = new Set(priceCandidatesForServing(next, key, state.savedByProduct).map((c) => c.priceKrw));
    if (prices.size > 1 && prices.has(option.price)) chosen[key] = option.price;
  }
  return { ...next, chosenServingPrices: chosen };
}

// ---- This device's copy (spec 5.9: kept on the device while the server cannot be reached) ----

export interface DeviceDraft {
  reviewVersion: number;
  /** The server draft version this edit started from. */
  baseDraftVersion: number;
  content: DraftContent;
}

const deviceKey = (userId: string, menuImportId: string) => `bottlemap-owner-review:${userId}:${menuImportId}`;

export function readDeviceDraft(userId: string, menuImportId: string): DeviceDraft | null {
  try {
    const raw = localStorage.getItem(deviceKey(userId, menuImportId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as DeviceDraft;
    return typeof parsed.reviewVersion === "number" && typeof parsed.baseDraftVersion === "number" && parsed.content ? parsed : null;
  } catch {
    return null;
  }
}

/** Keeps the latest edit on this device; false when the browser does not allow it. */
export function writeDeviceDraft(userId: string, menuImportId: string, draft: DeviceDraft): boolean {
  try {
    localStorage.setItem(deviceKey(userId, menuImportId), JSON.stringify(draft));
    return true;
  } catch {
    return false;
  }
}

export function clearDeviceDraft(userId: string, menuImportId: string): void {
  try {
    localStorage.removeItem(deviceKey(userId, menuImportId));
  } catch {
    // Nothing kept, or nothing can be removed: either way there is no copy to use.
  }
}
