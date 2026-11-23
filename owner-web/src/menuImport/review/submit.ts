import type { components } from "../../api/schema";
import type { BarMenu } from "../../owner/queries";
import { isBottleServingLabel, servingIdentityKey } from "../../menu/servingIdentity";
import { validPrice, validVolume, type ReviewCard, type ReviewState } from "./model";
import { existingUnlinkedOptions, type ImportReview, type ReviewLine } from "./mapping";
import { MAX_REVIEW_OPTIONS, normalizedUnlinkedMenuName, sentLabel } from "./rules";

export type ReviewAndApply = components["schemas"]["ReviewAndApplyRequest"];
type ItemDecision = ReviewAndApply["itemDecisions"][number];
type ChangeDecision = ReviewAndApply["changeDecisions"][number];
type ProposedChange = components["schemas"]["ProposedChange"];
type SavedOption = Pick<BarMenu["items"][number]["options"][number], "optionLabel" | "pourMl" | "priceKrw">;

/** A serving as sent in `options[]` (8.1). */
export interface FinalOption {
  extractedOptionId: string | null;
  optionLabel: string | null;
  pourMl: number | null;
  priceKrw: number;
}

/** A reviewed serving before the bar's saved options are taken into account. */
export interface ChosenOption {
  extractedOptionId: string | null;
  label: string | null;
  pourMl: number | null;
  priceKrw: number;
}

export class ReviewSubmitError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ReviewSubmitError";
  }
}

function require(condition: boolean, message: string): asserts condition {
  if (!condition) throw new ReviewSubmitError(message);
}

const keyOf = (option: { pourMl: number | null; optionLabel: string | null }) => servingIdentityKey(option.pourMl, option.optionLabel);

/**
 * `ownerFinalReviewOptions` (android/.../data/owner/OwnerReviewOptionContract.kt): the line's final options.
 *
 * - An extracted option keeps its ID; one the owner added is sent without one.
 * - A glass without a pour gets the bar's default, for a whisky only; a bottle has no pour.
 * - A serving the bar already sells keeps its saved label (and a saved bottle's capacity), so it updates that
 *   option instead of adding a second one.
 * - The bar's saved servings this line does not mention are sent as they are. The server replaces all of an
 *   item's options even in a partial update, so leaving them out would delete them and their discounts.
 */
export function finalReviewOptions(
  line: Pick<ReviewLine, "options">,
  chosen: readonly ChosenOption[],
  defaultPourMl: number,
  whisky: boolean,
  existing: readonly SavedOption[] = [],
): FinalOption[] {
  require(chosen.length >= 1 && chosen.length <= 10, "검수 메뉴의 가격 옵션은 1~10개여야 해요.");
  const ids = new Set(line.options.map((option) => option.extractedOptionId));
  const kept = chosen.map((option) => option.extractedOptionId).filter((id): id is string => id !== null && ids.has(id));
  require(new Set(kept).size === kept.length, "동일한 OCR 옵션을 두 번 게시할 수 없어요.");
  const reviewed = chosen.map((option): FinalOption => {
    require(validPrice(option.priceKrw), "가격을 확인해 주세요.");
    const bottle = isBottleServingLabel(option.label);
    const pour = bottle ? null : (option.pourMl ?? (whisky ? defaultPourMl : null));
    require(pour === null || validVolume(pour), "용량을 확인해 주세요.");
    const same = existing.filter((saved) => keyOf(saved) === servingIdentityKey(pour, bottle ? "Bottle" : option.label));
    require(same.length <= 1, "기존 매장에 같은 용량이 중복 등록되어 있어요. 기존 메뉴를 확인해 주세요.");
    const saved = same.length === 1 ? same[0] : undefined;
    const label = saved ? saved.optionLabel : bottle ? "Bottle" : pour !== null ? null : option.label;
    return {
      extractedOptionId: option.extractedOptionId !== null && ids.has(option.extractedOptionId) ? option.extractedOptionId : null,
      optionLabel: label,
      pourMl: saved ? saved.pourMl : pour,
      priceKrw: option.priceKrw,
    };
  });
  const reviewedKeys = new Set(reviewed.map(keyOf));
  const untouched = existing
    .filter((saved) => !reviewedKeys.has(keyOf(saved)))
    .map((saved): FinalOption => {
      require(validPrice(saved.priceKrw), "기존 메뉴 가격을 확인해 주세요.");
      return { extractedOptionId: null, optionLabel: saved.optionLabel, pourMl: saved.pourMl, priceKrw: saved.priceKrw };
    });
  const all = [...reviewed, ...untouched];
  require(all.length <= 10, "기존 용량을 보존하면 서버 최대 옵션 10개를 넘어요. 메뉴 관리에서 확인해 주세요.");
  const keys = all.map(keyOf);
  require(new Set(keys).size === keys.length, "같은 용량의 옵션이 중복됐어요. 가격을 하나로 정리해 주세요.");
  return all;
}

/**
 * `ownerPhotoSelectionExistingOptions`: the saved options a line linked to `productId` updates. The bar's item
 * of that product, or else the item the review compared the line with (an item without a product that the line
 * links, 5.4).
 */
export function existingOptionsForProduct(
  menu: BarMenu,
  proposedChanges: readonly ProposedChange[],
  extractedItemId: string,
  productId: string,
): BarMenu["items"][number]["options"] {
  const linked = menu.items.find((item) => item.productId === productId);
  if (linked) return linked.options;
  const compared = proposedChanges.find((change) =>
    (change.extractedItemIds.length > 0 ? change.extractedItemIds : [change.extractedItemId]).includes(extractedItemId),
  )?.barMenuItemId;
  return menu.items.find((item) => item.barMenuItemId === compared)?.options ?? [];
}

/**
 * `ownerRetainedOptionsForGroupedLine`: when several lines go to one item (8.12), a saved serving goes with the
 * lines that update it, and an untouched one with the first line only, so a later bottle-only line does not
 * bring back an old glass price.
 */
export function retainedForGroupedLine<T extends SavedOption>(
  lineId: string,
  groupLineIds: readonly string[],
  reviewedKeys: ReadonlyMap<string, ReadonlySet<string>>,
  saved: readonly T[],
): T[] {
  const lines = groupLineIds.length > 0 ? groupLineIds : [lineId];
  return saved.filter((old) => {
    const key = keyOf(old);
    const updating = lines.filter((id) => reviewedKeys.get(id)?.has(key));
    return updating.length === 0 ? lineId === lines[0] : updating.includes(lineId);
  });
}

/** `photoImportChangeDecision`: a change is applied when one of its lines is published; a removal never is. */
export function changeDecision(change: Pick<ProposedChange, "changeType" | "extractedItemId" | "extractedItemIds">, published: ReadonlySet<string>): "apply" | "ignore" {
  const ids = change.extractedItemIds.length > 0 ? change.extractedItemIds : [change.extractedItemId].filter((id): id is string => id !== null);
  return change.changeType !== "remove" && ids.some((id) => published.has(id)) ? "apply" : "ignore";
}

/** The reviewed servings of a card, as `mapConfirmedReviewDecision` sends them. */
export function chosenOptions(card: ReviewCard): ChosenOption[] {
  require(card.options.length > 0 && card.options.length <= MAX_REVIEW_OPTIONS, `${card.name}: 검수 옵션 개수를 확인해 주세요.`);
  require(
    card.options.every((option) => validPrice(option.price) && (option.bottle || card.type === "other" || validVolume(option.volume))),
    `${card.name}: 가격과 용량을 확인해 주세요.`,
  );
  return card.options.map((option) => ({
    extractedOptionId: option.sourceOptionId,
    label: sentLabel(option),
    pourMl: option.bottle ? null : validVolume(option.volume) ? option.volume : null,
    priceKrw: option.price,
  }));
}

/**
 * The review-and-apply body (8.1), as LiveOwnerScreenRepository.kt `publishPhotoImportLive` builds it: a
 * decision for every line in the response's order, and a decision for every proposed change. An owner never
 * creates a catalog product: a whisky without one is published without a product (8.10).
 */
export function reviewBody(review: ImportReview, state: ReviewState, menu: BarMenu): ReviewAndApply {
  const cards = new Map(state.cards.map((card) => [card.id, card]));
  const lines = [...review.images]
    .sort((a, b) => a.imageOrder - b.imageOrder)
    .flatMap((image) => [...image.items].sort((a, b) => a.itemOrder - b.itemOrder));
  const defaultPour = state.defaultPour;

  type Plan = { line: ReviewLine; card: ReviewCard; chosen: ChosenOption[]; target: string; whisky: boolean; name: string };
  const plans = new Map<string, Plan>();
  for (const line of lines) {
    const card = cards.get(line.extractedItemId);
    require(card !== undefined, "확인하지 않은 메뉴가 있어요.");
    if (card.excluded) continue;
    require(card.name.trim().length >= 1 && card.name.trim().length <= 200, "메뉴 이름은 1~200자로 입력해 주세요.");
    const name = card.name.trim();
    const target = card.linkedProductId !== null ? `product:${card.linkedProductId}` : `name:${normalizedUnlinkedMenuName(name)}`;
    plans.set(line.extractedItemId, { line, card, chosen: chosenOptions(card), target, whisky: card.linkedProductId !== null || card.type === "whisky", name });
  }
  const groups = new Map<string, string[]>();
  const reviewedKeys = new Map<string, Set<string>>();
  for (const plan of plans.values()) {
    groups.set(plan.target, [...(groups.get(plan.target) ?? []), plan.line.extractedItemId]);
    reviewedKeys.set(plan.line.extractedItemId, new Set(finalReviewOptions(plan.line, plan.chosen, defaultPour, plan.whisky).map(keyOf)));
  }
  const retained = (plan: Plan, saved: readonly SavedOption[]) =>
    retainedForGroupedLine(plan.line.extractedItemId, groups.get(plan.target) ?? [], reviewedKeys, saved);

  const itemDecisions = lines.map((line): ItemDecision => {
    const plan = plans.get(line.extractedItemId);
    if (!plan) return { action: "reject", extractedItemId: line.extractedItemId, finalLineType: line.effectiveLineType };
    const { card, chosen, name } = plan;
    if (card.linkedProductId !== null) {
      const saved = existingOptionsForProduct(menu, review.proposedChanges, line.extractedItemId, card.linkedProductId);
      return {
        action: "select_existing_product",
        extractedItemId: line.extractedItemId,
        finalLineType: "product",
        productId: card.linkedProductId,
        correctedProductName: name !== line.extractedProductName ? name : null,
        options: finalReviewOptions(line, chosen, defaultPour, true, retained(plan, saved)),
      };
    }
    require(card.type === "other" || (card.newConfirmed && card.nameSaved), `${card.name}: 신규 위스키 이름을 확인해 주세요.`);
    const kind = card.type === "whisky" ? "whisky" : "other";
    return {
      action: "publish_without_product",
      extractedItemId: line.extractedItemId,
      finalLineType: "product",
      kind,
      correctedProductName: name,
      options: finalReviewOptions(line, chosen, defaultPour, kind === "whisky", retained(plan, existingUnlinkedOptions(menu, name))),
    };
  });
  const published = new Set(plans.keys());
  const changeDecisions = review.proposedChanges.map(
    (change): ChangeDecision => ({ changeId: change.changeId, decision: changeDecision(change, published) }),
  );
  return { reviewVersion: review.reviewVersion, itemDecisions, changeDecisions };
}
