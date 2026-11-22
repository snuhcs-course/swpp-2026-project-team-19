import type { components } from "../api/schema";
import { blockingInactiveMatch, manualEditorCategory, normalizeOwnerCatalogName } from "./catalogMatch";
import { ownerAddMenuIdentity, type AddIdentity } from "./menuIdentity";
import {
  MANUAL_MENU_MAX_OPTIONS,
  MAX_OWNER_MENU_PRICE_KRW,
  MAX_POUR_ML,
  existingBarProductMenu,
  manualMenuCategoryCode,
  manualMenuOptionError,
  menuProductOf,
  type Discount,
  type MenuCategory,
  type MenuItem,
  type MenuOption,
  type MenuProduct,
  type OptionValue,
} from "./menuRules";
import { isBottleServingLabel } from "./servingIdentity";

/**
 * The menu item editor, ported from android/.../ui/owner/OwnerManualMenuScreen.kt (`DraftOption`, `fromSaved`,
 * `toOption`, `edit` and `save`), keeping only what the app does against the real API: an add sends a catalog
 * `productId` or a `kind` (spec 3.14.3), an edit sends the name and the options (3.14.4). Discounts are not
 * edited here (I5-P8): an edit sends each option's discount back as it came, so it is kept (3.14.2).
 */
export type MenuOptionInput = components["schemas"]["MenuOptionInput"];

/** One option row as typed. `id` is the saved option's `menuEntryOptionId`, or a local one for a new row. */
export interface DraftOption {
  id: string;
  bottle: boolean;
  ml: string;
  price: string;
  /** The saved discount, sent back unchanged. */
  discount: Discount | null;
}

let localIds = 0;
export function freshOption(): DraftOption {
  localIds += 1;
  return { id: `local-serving-${localIds}`, bottle: false, ml: "", price: "", discount: null };
}

export function fromSaved(option: MenuOption): DraftOption {
  return {
    id: option.menuEntryOptionId,
    bottle: isBottleServingLabel(option.optionLabel),
    ml: option.pourMl?.toString() ?? "",
    price: String(option.priceKrw),
    discount: option.discount,
  };
}

export const savedOption = (option: MenuOption): OptionValue => ({
  optionId: option.menuEntryOptionId,
  label: option.optionLabel,
  pourMl: option.pourMl,
  priceKrw: option.priceKrw,
  discount: option.discount,
});

const intOf = (text: string): number | null => (/^\d{1,9}$/.test(text) ? Number(text) : null);

/**
 * `toOption`: a whisky option is a pour in ml or a bottle; anything else is a price alone. An unchanged saved
 * option keeps its label and pour as stored ("잔 30" stays "잔 30"); a new one sends no label for a glass and
 * "Bottle" for a bottle. A discount that has already ended is left out (spec 3.14.2 `DISCOUNT_ENDED`).
 */
export function toOption(draft: DraftOption, whisky: boolean, original: OptionValue | undefined, preserveOriginalServing: boolean, now: number): OptionValue {
  const price = intOf(draft.price);
  if (price === null) throw new Error("가격을 숫자로 입력해 주세요.");
  if (!(price >= 1 && price <= MAX_OWNER_MENU_PRICE_KRW) && original?.priceKrw !== price) {
    throw new Error("가격은 1원 이상, 1억 원 미만이어야 해요.");
  }
  const ml = whisky && !draft.bottle ? intOf(draft.ml) : null;
  const unchangedLegacyNullPour =
    preserveOriginalServing &&
    original !== undefined &&
    original.pourMl === null &&
    draft.ml.trim() === "" &&
    !["bottle", "병"].includes(original.label?.trim().toLowerCase() ?? "");
  if (whisky && !draft.bottle && !unchangedLegacyNullPour && !(ml !== null && ml >= 1 && ml <= MAX_POUR_ML)) {
    throw new Error("용량을 입력하거나 Bottle 판매를 선택해 주세요.");
  }
  const discount = draft.discount && Date.parse(draft.discount.endsAt) > now ? draft.discount : null;
  const keepOriginal =
    preserveOriginalServing &&
    original !== undefined &&
    original.optionId === draft.id &&
    (whisky ? (draft.bottle ? isBottleServingLabel(original.label) : (original.pourMl?.toString() ?? "") === draft.ml) : true);
  return {
    optionId: draft.id,
    label: keepOriginal ? original.label : whisky && draft.bottle ? "Bottle" : null,
    pourMl: keepOriginal ? original.pourMl : ml,
    priceKrw: price,
    discount,
  };
}

export const EDIT_BLOCKED = "이 메뉴는 가격 옵션이 4개 이상이어서 직접 수정할 수 없어요. 기존 메뉴는 유지됩니다.";
/** The app's message, with a comma for its middle dot. */
export const ALREADY_ON_MENU = "이미 등록한 상품이에요. 기존 메뉴에서 용량, 가격을 수정해 주세요.";
export const MAX_NAME_LENGTH = 80;

/** What the editor holds: the name, the kind and the option rows. */
export interface Draft {
  name: string;
  category: MenuCategory;
  options: DraftOption[];
}

/** `edit(item)`: the kind and options an item opens with; null when it has more options than the editor takes. */
export function editDraftOf(item: MenuItem): Draft | null {
  if (item.options.length > MANUAL_MENU_MAX_OPTIONS) return null;
  const category = manualEditorCategory(menuProductOf(item));
  const limit = category === "위스키" ? MANUAL_MENU_MAX_OPTIONS : 1;
  return { name: item.displayName, category, options: item.options.slice(0, limit).map(fromSaved) };
}

const sameTyping = (a: DraftOption, b: DraftOption) => a.bottle === b.bottle && a.ml === b.ml && a.price === b.price;

/**
 * After MENU_OUTDATED (spec 3.14.1), the edit is moved onto the item as it is now (`fresh`, its `editDraftOf`),
 * so that saving again does not undo what changed elsewhere: what the owner changed since `start` stays as
 * typed, and the rest takes the new values. A saved row keeps the option's discount as it is now, which this
 * editor does not change (I5-P8). A row whose option was removed elsewhere goes too, unless the owner typed
 * in it; then it stays as a new option. Options added elsewhere are added after the rows. Not in the app,
 * which does not handle MENU_OUTDATED (Codex review on #199).
 */
export function rebaseDraft(start: Draft, current: Draft, fresh: Draft): Draft {
  const before = new Map(start.options.map((option) => [option.id, option]));
  const now = new Map(fresh.options.map((option) => [option.id, option]));
  const rows = current.options.flatMap((row) => {
    const opened = before.get(row.id);
    if (!opened) return [row];
    const saved = now.get(row.id);
    if (saved) return [sameTyping(row, opened) ? saved : { ...row, discount: saved.discount }];
    return sameTyping(row, opened) ? [] : [{ ...freshOption(), bottle: row.bottle, ml: row.ml, price: row.price }];
  });
  return {
    name: current.name === start.name ? fresh.name : current.name,
    category: current.category === start.category ? fresh.category : current.category,
    options: [...rows, ...fresh.options.filter((option) => !before.has(option.id))],
  };
}

export interface SaveInput {
  items: readonly MenuItem[];
  /** The item edited; undefined for an add. */
  editing?: MenuItem;
  name: string;
  category: MenuCategory;
  options: readonly DraftOption[];
  /** The product confirmed with "맞아요" (adds only). */
  linkedId: string | null;
  rejectedId: string | null;
  /** The products the proposals came from: catalog search results and the menu's own. */
  candidates: readonly MenuProduct[];
  now: number;
  /** Saved options whose discount the server said has ended (422 DISCOUNT_ENDED), left out from now on. */
  endedDiscounts?: readonly string[];
}

export type SaveRequest =
  | { kind: "add"; body: { displayName: string; options: MenuOptionInput[] } & AddIdentity; shown: number }
  | { kind: "edit"; barMenuItemId: string; body: { displayName: string; options: MenuOptionInput[] }; shown: number };

/** A refused save: the message, and the item already on the menu when that is why. */
export class SaveRefused extends Error {
  constructor(
    message: string,
    readonly existingItemId?: string,
  ) {
    super(message);
    this.name = "SaveRefused";
  }
}

const sameName = (a: string, b: string) => a.replaceAll(" ", "").toLowerCase() === b.replaceAll(" ", "").toLowerCase();

const toInput = (option: OptionValue): MenuOptionInput => ({
  optionLabel: option.label,
  pourMl: option.pourMl,
  priceKrw: option.priceKrw,
  discount: option.discount,
});

/**
 * `save`: checks the item as the app does and builds the request, or throws SaveRefused with the app's
 * message. `shown` is how many of the options sent are the editor's rows; the rest are saved options the
 * editor does not show (a non-whisky item keeps the extra prices it was imported with), sent back as they are.
 */
export function prepareMenuSave(input: SaveInput): SaveRequest {
  const { items, editing, category, rejectedId, candidates, now } = input;
  const name = input.name.trim();
  if (!editing && category === "위스키" && blockingInactiveMatch(candidates, name)) {
    throw new SaveRefused("운영이 중지된 카탈로그 상품이에요. 운영자에게 문의해 주세요.");
  }
  const persisted = editing ? menuProductOf(editing) : null;
  const linked = editing ? persisted : (candidates.find((product) => product.productId === input.linkedId) ?? null);
  const confirmedExistingName =
    !editing &&
    candidates.some((product) => product.productId === input.linkedId && product.displayName === name && manualEditorCategory(product) === category);
  const length = name.length;
  if (!name || !(length <= MAX_NAME_LENGTH || (length <= 200 && (name === editing?.displayName || confirmedExistingName)))) {
    throw new SaveRefused("메뉴 이름을 확인해 주세요.");
  }
  const sameCategory = linked !== null && manualEditorCategory(linked) === category;
  // The production editor keeps only whisky and other (PR #164): no finer kind is sent or stored.
  const categoryCode = category === "기타 주류" ? "otherAlcohol" : manualMenuCategoryCode(category);
  const whisky = category === "위스키";
  const saved = editing?.options.map(savedOption) ?? [];
  const rows = whisky ? input.options : input.options.slice(0, 1);
  let edited: OptionValue[];
  try {
    edited = rows.map((draft, index) => {
      const parsed = toOption(
        draft,
        whisky,
        saved.find((option) => option.optionId === draft.id),
        sameCategory,
        now,
      );
      // A single-price item keeps its saved serving label and pour.
      const original = !whisky && sameCategory ? saved[index] : undefined;
      return original ? { ...parsed, label: original.label, pourMl: original.pourMl } : parsed;
    });
  } catch (failure) {
    throw new SaveRefused(failure instanceof Error ? failure.message : "저장하지 못했어요.");
  }
  const optionError = manualMenuOptionError(edited, categoryCode, saved);
  if (optionError) throw new SaveRefused(optionError);
  const limit = whisky ? MANUAL_MENU_MAX_OPTIONS : 1;
  // The saved options the editor does not show go back as they are, but without a discount that has ended
  // (spec 3.14.2), as for the options shown.
  const ended = new Set(input.endedDiscounts ?? []);
  const tail = (editing && editing.options.length > limit ? saved.slice(limit) : []).map((option) =>
    option.discount && (Date.parse(option.discount.endsAt) <= now || ended.has(option.optionId)) ? { ...option, discount: null } : option,
  );
  const options = [...edited, ...tail].map(toInput);
  if (editing) {
    return { kind: "edit", barMenuItemId: editing.barMenuItemId, body: { displayName: name, options }, shown: edited.length };
  }
  if (linked === null) {
    // An item of this bar without a product, named the same: edit it rather than adding a second one.
    const existingLocal = items.find((item) => {
      const product = menuProductOf(item);
      return (
        !product.catalogMatched &&
        product.productId !== rejectedId &&
        manualEditorCategory(product) === category &&
        [product.displayName, item.displayName].some((itemName) => sameName(itemName, name))
      );
    });
    if (existingLocal) throw new SaveRefused(ALREADY_ON_MENU, existingLocal.barMenuItemId);
  }
  const product: MenuProduct = linked ?? {
    productId: "local-unverified",
    brandId: "",
    displayName: name,
    category: categoryCode,
    ageYears: null,
    isActive: true,
    matchedAlias: null,
    catalogMatched: false,
  };
  const duplicate = linked ? existingBarProductMenu(items, product.productId) : undefined;
  if (duplicate) throw new SaveRefused(ALREADY_ON_MENU, duplicate.barMenuItemId);
  let identity: AddIdentity;
  try {
    identity = ownerAddMenuIdentity(product.productId, product, null);
  } catch (failure) {
    throw new SaveRefused(failure instanceof Error ? failure.message : "저장하지 못했어요.");
  }
  return { kind: "add", body: { displayName: name, options, ...identity }, shown: edited.length };
}

/**
 * Before adding a whisky without a product, the app searches once more (`searchCatalogLive`): an active
 * product named exactly so must be confirmed or declined first. Returns that product, or null.
 */
export function freshExactMatch(results: readonly MenuProduct[], name: string, category: MenuCategory, rejectedId: string | null): MenuProduct | null {
  const key = normalizeOwnerCatalogName(name);
  return (
    results.find(
      (product) =>
        product.isActive &&
        product.productId !== rejectedId &&
        manualEditorCategory(product) === category &&
        (normalizeOwnerCatalogName(product.displayName) === key || normalizeOwnerCatalogName(product.matchedAlias ?? "") === key),
    ) ?? null
  );
}

/** The app's message for that product. */
export const confirmFirst = (product: MenuProduct) => `“${product.displayName}”이 맞나요? 맞아요 또는 아니에요를 선택해 주세요.`;
