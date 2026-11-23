import { canonicalServingLabel, isBottleServingLabel, servingIdentityKey } from "../../menu/servingIdentity";
import {
  validDefaultPour,
  validPrice,
  validVolume,
  priceValue,
  readNumeric,
  type CatalogChoice,
  type PriceCandidate,
  type ReviewCard,
  type ReviewGroup,
  type ReviewIssue,
  type ReviewOption,
  type ReviewState,
} from "./model";

/**
 * The review rules, ported from android/.../ui/owner/review/PhotoReviewRules.kt (problems, groups, counts and
 * the card actions). Pure functions: the screen only calls them.
 */

/** The app publishes at most three servings per card from the review (`MAX_OPTIONS`, `MAX_PICKED_VOLUMES`). */
export const MAX_REVIEW_OPTIONS = 3;

/** `servingKey`: one serving per ml whatever the menu calls it, and one bottle. */
export function servingKey(option: Pick<ReviewOption, "bottle" | "volume" | "label">): string {
  return servingIdentityKey(
    option.bottle ? null : validVolume(option.volume) ? option.volume : null,
    option.bottle ? "Bottle" : option.label,
  );
}

/**
 * `normalizedUnlinkedMenuName`: the name key the server compares menu items without a product by (3.14.1),
 * for checks before publishing only; the server decides.
 */
export function normalizedUnlinkedMenuName(value: string): string {
  return value
    .normalize("NFKC")
    .replace(/[‐-‒–—―−]/g, "-")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim()
    .replace(/(?<=\d) ?(?:years? old|years?|yo|y|년|年)(?![a-z])/g, "")
    .replace(/[^\p{L}\p{N}\s.-]|_/gu, "")
    .replace(/(?<!\d)\.|\.(?!\d)/g, "")
    .replace(/\s+/g, "");
}

/** A menu name the server can publish: 1 to 200 characters with something left after normalizing. */
export function validMenuName(name: string): boolean {
  const trimmed = name.trim();
  return trimmed.length >= 1 && trimmed.length <= 200 && normalizedUnlinkedMenuName(trimmed) !== "";
}

/** `priceCandidatesForServing`: the prices to choose from for one serving of the card. */
export function priceCandidatesForServing(card: ReviewCard, key: string, saved: ReviewState["savedByProduct"]): PriceCandidate[] {
  const current = card.options.find((option) => servingKey(option) === key);
  const candidates = card.priceCandidates.filter((candidate) => candidate.servingKey === key);
  if (card.linkedProductId !== null) {
    for (const old of saved[card.linkedProductId] ?? []) {
      if (old.servingKey === key && !candidates.some((c) => c.existing && c.priceKrw === old.priceKrw)) candidates.push(old);
    }
  }
  if (current && validPrice(current.price) && !candidates.some((c) => !c.existing && c.priceKrw === current.price)) {
    candidates.push({
      servingKey: key,
      volumeMl: validVolume(current.volume) ? current.volume : null,
      bottle: current.bottle,
      label: current.label,
      priceKrw: current.price,
      existing: false,
      sourceItemId: card.id,
    });
  }
  return candidates;
}

/** `pendingPriceServings`: servings with several prices whose choice the owner has not made. */
export function pendingPriceServings(card: ReviewCard, saved: ReviewState["savedByProduct"]): string[] {
  if (!card.volumeChoicesConfirmed) return [];
  const keys = [...new Set(card.options.map(servingKey))];
  return keys.filter((key) => {
    const prices = new Set(priceCandidatesForServing(card, key, saved).map((c) => c.priceKrw));
    const current = card.options.find((option) => servingKey(option) === key);
    return prices.size > 1 && card.chosenServingPrices[key] !== current?.price;
  });
}

/** `chooseServingPrice`. */
export function chooseServingPrice(card: ReviewCard, key: string, price: number, saved: ReviewState["savedByProduct"]): ReviewCard {
  if (!priceCandidatesForServing(card, key, saved).some((c) => c.priceKrw === price)) return card;
  return {
    ...card,
    chosenServingPrices: { ...card.chosenServingPrices, [key]: price },
    options: card.options.map((option) => (servingKey(option) === key ? { ...option, price } : option)),
  };
}

/** Picks or unpicks a serving when more than three were read. */
export function toggleVolumeChoice(card: ReviewCard, key: string): ReviewCard {
  const picked = card.chosenVolumeKeys.includes(key);
  if (!picked && card.chosenVolumeKeys.length >= MAX_REVIEW_OPTIONS) return card;
  return { ...card, chosenVolumeKeys: picked ? card.chosenVolumeKeys.filter((k) => k !== key) : [...card.chosenVolumeKeys, key] };
}

/** `confirmVolumeChoices`: keeps the picked servings, one to three. */
export function confirmVolumeChoices(card: ReviewCard): ReviewCard {
  const picked = card.volumeChoices.filter((option) => card.chosenVolumeKeys.includes(servingKey(option)));
  if (picked.length === 0 || picked.length > MAX_REVIEW_OPTIONS) return card;
  return { ...card, options: picked, volumeChoicesConfirmed: true };
}

/** `applyDefaultPour`: every glass that took the bar's default follows its new value. */
export function applyDefaultPour(card: ReviewCard, defaultPour: number): ReviewCard {
  return {
    ...card,
    options: card.options.map((option) => (option.fromDefault && !option.bottle ? { ...option, volume: defaultPour } : option)),
  };
}

/** `duplicatePhotoPriceConflicts`: lines linked to one product with different prices for one serving (8.12). */
export function duplicatePhotoPriceConflicts(state: ReviewState): Map<string, Set<string>> {
  const buckets = new Map<string, { id: string; price: number; serving: string }[]>();
  for (const card of state.cards) {
    if (card.excluded || card.type !== "whisky" || card.linkedProductId === null) continue;
    for (const option of card.options) {
      const bottle = option.bottle || isBottleServingLabel(option.label);
      if (!validPrice(option.price) || (!bottle && !validVolume(option.volume))) continue;
      const serving = bottle ? "Bottle" : `${option.volume}ml`;
      const key = `${card.linkedProductId}|${servingIdentityKey(bottle ? null : option.volume, option.label ?? (bottle ? "Bottle" : null))}`;
      const bucket = buckets.get(key) ?? [];
      bucket.push({ id: card.id, price: option.price, serving });
      buckets.set(key, bucket);
    }
  }
  const conflicts = new Map<string, Set<string>>();
  for (const values of buckets.values()) {
    if (new Set(values.map((v) => v.id)).size > 1 && new Set(values.map((v) => v.price)).size > 1) {
      for (const value of values) conflicts.set(value.id, (conflicts.get(value.id) ?? new Set()).add(value.serving));
    }
  }
  return conflicts;
}

/** `duplicateOtherPrices`: same-name lines of other menus with different prices for one serving (8.12). */
export function duplicateOtherPrices(state: ReviewState): Set<string> {
  const collisions = new Set<string>();
  const groups = new Map<string, ReviewCard[]>();
  for (const card of state.cards) {
    if (card.excluded || card.mergedInto !== null || card.type !== "other" || card.linkedProductId !== null) continue;
    const key = normalizedUnlinkedMenuName(card.name);
    if (key === "") continue;
    groups.set(key, [...(groups.get(key) ?? []), card]);
  }
  for (const group of groups.values()) {
    if (group.length < 2) continue;
    const byServing = new Map<string, { id: string; price: number }[]>();
    for (const card of group) {
      for (const option of card.options) {
        if (!validPrice(option.price)) continue;
        const bottle = option.bottle || isBottleServingLabel(option.label);
        const key = servingIdentityKey(bottle ? null : validVolume(option.volume) ? option.volume : null, bottle ? "Bottle" : option.label);
        byServing.set(key, [...(byServing.get(key) ?? []), { id: card.id, price: option.price }]);
      }
    }
    for (const entries of byServing.values()) {
      if (new Set(entries.map((e) => e.id)).size > 1 && new Set(entries.map((e) => e.price)).size > 1) {
        for (const entry of entries) collisions.add(entry.id);
      }
    }
  }
  return collisions;
}

/** Conflicts across the whole review, computed once for a render. */
export interface ReviewConflicts {
  photo: Map<string, Set<string>>;
  other: Set<string>;
}

export function reviewConflicts(state: ReviewState): ReviewConflicts {
  return { photo: duplicatePhotoPriceConflicts(state), other: duplicateOtherPrices(state) };
}

/** `problems`: what keeps a card in "확인 필요". */
export function problems(card: ReviewCard, state: ReviewState, conflicts: ReviewConflicts = reviewConflicts(state)): ReviewIssue[] {
  if (card.excluded) return [];
  const issues: ReviewIssue[] = [];
  const keysOf = (options: readonly ReviewOption[]) => options.map((option) => servingKey(option));
  const hasDuplicates = (keys: string[]) => new Set(keys).size !== keys.length;
  if (card.type === "whisky") {
    if (card.searchMode) issues.push("catalogSearch");
    else if (card.match === "ambiguous" && !card.nameSaved) issues.push("match");
    else if (card.match === "candidate" && !card.matchConfirmed) issues.push("candidate");
    else if (card.match === "new" && !card.nameSaved) issues.push("new");
    if (pendingPriceServings(card, state.savedByProduct).length > 0) issues.push("priceChoice");
    if (!card.volumeChoicesConfirmed && card.volumeChoices.length > 0) issues.push("option");
    else if (card.options.length === 0) issues.push("price");
    else {
      if (card.options.some((option) => !option.bottle && !validVolume(option.volume))) issues.push("volume");
      if (card.options.some((option) => !validPrice(option.price))) issues.push("price");
      if (card.options.length > MAX_REVIEW_OPTIONS || hasDuplicates(keysOf(card.options))) issues.push("option");
    }
  } else {
    if (card.priceCandidates.length > 0 && pendingPriceServings(card, state.savedByProduct).length > 0) issues.push("priceChoice");
    if (card.options.length === 0 || card.options.some((option) => !validPrice(option.price))) issues.push("price");
    if (card.options.length > MAX_REVIEW_OPTIONS || hasDuplicates(keysOf(card.options))) issues.push("option");
  }
  if (card.nameEditing || !validMenuName(card.name)) issues.push("name");
  if (conflicts.photo.has(card.id) || conflicts.other.has(card.id)) issues.push("duplicatePrice");
  return [...new Set(issues)];
}

/** `itemGroup`. */
export function cardGroup(card: ReviewCard, state: ReviewState, conflicts?: ReviewConflicts): ReviewGroup {
  if (card.excluded) return "excluded";
  if (problems(card, state, conflicts).length > 0) return "pending";
  return card.type === "other" ? "other" : "ready";
}

export interface ReviewStats {
  pending: ReviewCard[];
  ready: ReviewCard[];
  other: ReviewCard[];
  excluded: ReviewCard[];
  total: number;
  done: number;
  percent: number;
  canPublish: boolean;
  noDefault: boolean;
}

/** `stats`: the groups (merged lines are shown inside their card), the progress and whether it can be published. */
export function reviewStats(state: ReviewState): ReviewStats {
  const conflicts = reviewConflicts(state);
  const shown = state.cards.filter((card) => card.mergedInto === null);
  const groups: Record<ReviewGroup, ReviewCard[]> = { pending: [], ready: [], other: [], excluded: [] };
  const issueCount = new Map<string, number>();
  for (const card of shown) {
    const issues = problems(card, state, conflicts);
    issueCount.set(card.id, issues.length);
    groups[card.excluded ? "excluded" : issues.length > 0 ? "pending" : card.type === "other" ? "other" : "ready"].push(card);
  }
  const required = shown.filter((card) => card.required || (issueCount.get(card.id) ?? 0) > 0);
  const done = required.filter((card) => card.excluded || issueCount.get(card.id) === 0).length;
  const total = required.length;
  const noDefault = !validDefaultPour(state.defaultPour);
  return {
    ...groups,
    total,
    done,
    percent: total > 0 ? Math.round((done / total) * 100) : 100,
    canPublish: groups.pending.length === 0 && groups.ready.length + groups.other.length > 0 && !noDefault,
    noDefault,
  };
}

/** `publicationPreview`: existing prices this publish changes, and new whiskies published without a product. */
export function publicationPreview(state: ReviewState): { changedExistingPrices: number; publishWithoutProduct: number } {
  const conflicts = reviewConflicts(state);
  const approved = state.cards.filter((card) => card.mergedInto === null && !card.excluded && problems(card, state, conflicts).length === 0);
  const changedExistingPrices = approved.filter((card) => {
    const saved = card.linkedProductId !== null ? (state.savedByProduct[card.linkedProductId] ?? []) : card.priceCandidates;
    const existing = saved.filter((candidate) => candidate.existing);
    return card.options.some((option) => {
      const old = existing.find((candidate) => candidate.servingKey === servingKey(option));
      return old !== undefined && validPrice(option.price) && old.priceKrw !== option.price;
    });
  }).length;
  return {
    changedExistingPrices,
    publishWithoutProduct: approved.filter((card) => card.type === "whisky" && card.linkedProductId === null).length,
  };
}

/** "같은 위스키가 두 줄 있어 하나로 합쳤어요." with the real number of lines. */
export function mergedNotice(card: ReviewCard): string | null {
  const count = 1 + card.mergeSources.length;
  if (count < 2) return null;
  const words: Record<number, string> = { 2: "두", 3: "세", 4: "네", 5: "다섯", 6: "여섯", 7: "일곱", 8: "여덟", 9: "아홉", 10: "열" };
  return `같은 위스키가 ${words[count] ? `${words[count]} 줄` : `${count}줄`} 있어 하나로 합쳤어요.`;
}

/** `sourceLocation`. */
export function sourceLocation(card: Pick<ReviewCard, "photoIndex" | "sourceLine" | "sourceBox">): string {
  return card.sourceBox?.length === 4 ? `${card.photoIndex}번째 장 ${card.sourceLine}번째 줄` : `${card.photoIndex}번째 장, 위치 정보 없음`;
}

// ---- Product links (PhotoReviewRules.kt markLinked, markAsNewForOperator, applyRematch) ----

const SEARCH_RESET = { searchMode: false, nameEditing: false } as const;

/** `markLinked`: links the card to a catalog product; that product's saved prices join the price choice. */
export function markLinked(card: ReviewCard, product: Pick<CatalogChoice, "productId" | "name">, saved: ReviewState["savedByProduct"]): ReviewCard {
  const active = new Set(card.options.map(servingKey));
  const fromPhoto = card.priceCandidates.filter((candidate) => !candidate.existing);
  const fromMenu = (saved[product.productId] ?? []).filter((candidate) => active.has(candidate.servingKey));
  return {
    ...card,
    ...SEARCH_RESET,
    priceCandidates: [...fromPhoto, ...fromMenu],
    chosenServingPrices: {},
    linkedProductId: product.productId,
    linkedProductName: product.name,
    match: "exact",
    matchConfirmed: true,
    nameSaved: true,
    newConfirmed: false,
    operatorReason: null,
  };
}

/**
 * `rebindUnlinkedPrices`: after a new name, the saved prices of the bar's item without a product of that name
 * (by name key) take part in the price choice, and those of the old name no longer do.
 */
export function rebindUnlinkedPrices(card: ReviewCard, saved: readonly PriceCandidate[]): ReviewCard {
  const active = new Set(card.options.map(servingKey));
  const fromPhoto = card.priceCandidates.filter((candidate) => !candidate.existing && active.has(candidate.servingKey));
  const seen = new Set<string>();
  const merged = [...saved.filter((candidate) => active.has(candidate.servingKey)), ...fromPhoto].filter((candidate) => {
    const key = `${candidate.servingKey}|${candidate.priceKrw}|${candidate.existing}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return { ...card, priceCandidates: merged, chosenServingPrices: {} };
}

/** "찾는 위스키가 없어요" (`markAsNewForOperator`): published without a product; the operator links it later. */
export function markAsNewForOperator(card: ReviewCard, typed: string): ReviewCard {
  const name = typed.trim() || card.name;
  return {
    ...card,
    name,
    linkedProductId: null,
    linkedProductName: null,
    match: "new",
    newConfirmed: false,
    nameSaved: false,
    matchConfirmed: false,
    operatorReason: "new",
    searchMode: false,
    nameEditing: true,
  };
}

/** "이 이름으로 등록" (`confirmNew`): the whisky is published under its name, without a product. */
export function confirmNew(card: ReviewCard): ReviewCard {
  return {
    ...card,
    ...SEARCH_RESET,
    nameSaved: true,
    newConfirmed: true,
    matchConfirmed: true,
    linkedProductId: null,
    linkedProductName: null,
    match: "new",
    operatorReason: "new",
  };
}

export type RematchOutcome = "same" | "changed" | "operator" | "other";

/**
 * `applyRematch` (decision 2): a renamed whisky is matched again by its new name. One exact product keeps or
 * changes the link; none or several leave it without a product for the operator. The server matches again on
 * publishing (8.11); this shows the likely result.
 */
export function applyRematch(
  card: ReviewCard,
  exactMatches: readonly Pick<CatalogChoice, "productId" | "name">[],
  saved: ReviewState["savedByProduct"],
): [ReviewCard, RematchOutcome] {
  if (card.type !== "whisky") return [card, "other"];
  const oldProductId = card.linkedProductId;
  const only = exactMatches.length === 1 ? exactMatches[0] : undefined;
  if (only) {
    const linked = markLinked(card, only, saved);
    return oldProductId !== null && oldProductId !== only.productId
      ? [{ ...linked, operatorReason: "changed" }, "changed"]
      : [linked, "same"];
  }
  return [
    {
      ...card,
      ...SEARCH_RESET,
      linkedProductId: null,
      linkedProductName: null,
      match: "new",
      newConfirmed: true,
      matchConfirmed: true,
      nameSaved: true,
      operatorReason: oldProductId !== null ? "unlinked" : "new",
    },
    "operator",
  ];
}

/** The catalog products whose name or matched alias is the typed name (LivePhotoReviewRepository.kt `exactMatches`). */
export function exactCatalogMatches<T extends { productId: string; displayName: string; matchedAlias: string | null; isActive: boolean }>(
  results: readonly T[],
  name: string,
): T[] {
  const normalized = (value: string) => value.trim().normalize("NFKC").toLowerCase();
  const key = normalized(name);
  const seen = new Set<string>();
  return results.filter((product) => {
    if (!product.isActive || seen.has(product.productId)) return false;
    if (normalized(product.displayName) !== key && normalized(product.matchedAlias ?? "") !== key) return false;
    seen.add(product.productId);
    return true;
  });
}

// ---- Classification (PhotoReviewRules.kt reclassify) ----

const explicitGlass = (label: string | null): boolean => /^(잔|샷|glass|shot)/.test(label?.trim().toLowerCase() ?? "");

/** "위스키로 분류" or "그 외 메뉴로 분류"; changing back restores the card as it was. */
export function reclassify(card: ReviewCard, defaultPour: number): ReviewCard {
  const target = card.type === "whisky" ? "other" : "whisky";
  const previous = card.classificationSnapshot;
  if (previous && previous.type === target) {
    return { ...card, ...previous, type: target, classificationSnapshot: null };
  }
  const snapshot = {
    type: card.type,
    options: card.options,
    match: card.match,
    matchConfirmed: card.matchConfirmed,
    nameSaved: card.nameSaved,
    newConfirmed: card.newConfirmed,
    linkedProductId: card.linkedProductId,
    linkedProductName: card.linkedProductName,
    candidates: card.candidates,
  };
  if (target === "other") {
    return {
      ...card,
      ...SEARCH_RESET,
      type: "other",
      classificationSnapshot: snapshot,
      // A bar default given to an unlabeled whisky glass is not a real size of another menu (sent without pour).
      options: card.options.map((option) =>
        option.bottle
          ? option
          : option.fromDefault && !explicitGlass(option.label)
            ? { ...option, volume: Number.NaN, fromDefault: false }
            : validVolume(option.volume)
              ? option
              : { ...option, volume: Number.NaN },
      ),
      linkedProductId: null,
      linkedProductName: null,
      match: "new",
      matchConfirmed: true,
      newConfirmed: true,
      nameSaved: true,
      operatorReason: null,
    };
  }
  return {
    ...card,
    ...SEARCH_RESET,
    type: "whisky",
    classificationSnapshot: snapshot,
    // The extracted options and prices stay; a glass without a pour takes the bar's default.
    options: card.options.map((option) =>
      option.bottle || validVolume(option.volume) ? option : { ...option, volume: defaultPour, fromDefault: true },
    ),
    match: "new",
    newConfirmed: false,
    nameSaved: false,
    matchConfirmed: false,
    linkedProductId: null,
    linkedProductName: null,
  };
}

// ---- Options (PhotoReviewRules.kt editOption, toggleBottle, addOption, removeOption) ----

export type OptionField = "volume" | "price";

export const rawKey = (field: OptionField, index: number): string => `${field}:${index}`;

/** One change of an option field; text that is not a valid number stays as typed until fixed. */
export function editOption(card: ReviewCard, field: OptionField, index: number, text: string): ReviewCard {
  const option = card.options[index];
  if (!option) return card;
  const n = field === "price" ? priceValue(text) : readNumeric(text);
  const valid = field === "price" ? validPrice(n) : validVolume(n);
  const key = rawKey(field, index);
  const rawEdits = { ...card.rawEdits };
  if (valid) delete rawEdits[key];
  else rawEdits[key] = text;
  const updated = field === "price" ? { ...option, price: n } : { ...option, volume: n, fromDefault: false };
  return { ...card, rawEdits, options: card.options.map((o, i) => (i === index ? updated : o)) };
}

/** The text a field shows: what was typed when it is not valid, else the number. */
export function optionFieldText(card: ReviewCard, field: OptionField, index: number): string {
  const typed = card.rawEdits[rawKey(field, index)];
  if (typed !== undefined) return typed;
  const option = card.options[index];
  if (!option) return "";
  const value = field === "price" ? option.price : option.volume;
  return Number.isNaN(value) || (field === "price" && value === 0) || (field === "volume" && option.bottle) ? "" : String(value);
}

/** "Bottle 판매" on or off for one option. */
export function toggleBottle(card: ReviewCard, index: number, defaultPour: number): ReviewCard {
  const option = card.options[index];
  if (!option) return card;
  const bottle = !option.bottle;
  const updated: ReviewOption = bottle
    ? { ...option, bottle: true, volume: 0, fromDefault: false }
    : {
        ...option,
        bottle: false,
        // An extracted "병" label must not make the serving a bottle again once the owner turned it off.
        label: isBottleServingLabel(option.label) ? null : option.label,
        volume: option.volume > 0 ? option.volume : defaultPour,
        fromDefault: !(option.volume > 0),
      };
  const rawEdits = { ...card.rawEdits };
  if (bottle) delete rawEdits[rawKey("volume", index)];
  return { ...card, rawEdits, options: card.options.map((o, i) => (i === index ? updated : o)) };
}

export function addOption(card: ReviewCard, defaultPour: number): ReviewCard {
  const added: ReviewOption =
    card.type === "other"
      ? { volume: Number.NaN, price: 0, bottle: false, sourceOptionId: null, label: null, fromDefault: false }
      : { volume: defaultPour, price: 0, bottle: false, sourceOptionId: null, label: null, fromDefault: card.options.length === 0 };
  return { ...card, options: [...card.options, added] };
}

export function removeOption(card: ReviewCard, index: number): ReviewCard {
  // Field text kept for later options moves with them.
  const rawEdits: Record<string, string> = {};
  for (const [key, value] of Object.entries(card.rawEdits)) {
    const [field, at] = key.split(":");
    const position = Number(at);
    if (position < index) rawEdits[key] = value;
    else if (position > index) rawEdits[`${field}:${position - 1}`] = value;
  }
  return { ...card, rawEdits, options: card.options.filter((_, i) => i !== index) };
}

/** The label sent for a reviewed option: "Bottle" for a bottle, else the menu's word unless it says bottle. */
export function sentLabel(option: Pick<ReviewOption, "bottle" | "label">): string | null {
  if (option.bottle) return "Bottle";
  const label = canonicalServingLabel(option.label);
  return label !== null && !isBottleServingLabel(label) ? label : null;
}
