import type { components } from "../api/schema";
import { addDays, isSeoulMidnight, seoulClock, seoulStartOf } from "../bar/seoulTime";
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
import { isBottleServingLabel, servingIdentityKey } from "./servingIdentity";

/**
 * The menu item editor, ported from android/.../ui/owner/OwnerManualMenuScreen.kt (`DraftOption`, `fromSaved`,
 * `toOption`, `edit` and `save`), keeping only what the app does against the real API: an add sends a catalog
 * `productId` or a `kind` (spec 3.14.3), an edit sends the name and the options (3.14.4). Each option carries
 * its discount (3.14.2): set, changed or removed in the editor's discount sheet, and otherwise sent back as it
 * came, so it is kept.
 */
export type MenuOptionInput = components["schemas"]["MenuOptionInput"];

/**
 * One option row as typed. `id` is the saved option's `menuEntryOptionId`, or a local one for a new row. The
 * discount is typed as in the app: a price and Seoul dates ("YYYY-MM-DD", the last day included), with the
 * saved discount's own instants kept to send back while its days are unchanged. No discount: all "".
 */
export interface DraftOption {
  id: string;
  bottle: boolean;
  ml: string;
  price: string;
  sale: string;
  start: string;
  end: string;
  originalStartsAt: string;
  originalEndsAt: string;
}

/** The discount part of a row, cleared by "할인 제거" or a discount that has ended. */
export const NO_DISCOUNT = { sale: "", start: "", end: "", originalStartsAt: "", originalEndsAt: "" } as const;
export type DraftDiscount = Pick<DraftOption, keyof typeof NO_DISCOUNT>;
export const discountOf = ({ sale, start, end, originalStartsAt, originalEndsAt }: DraftOption): DraftDiscount => ({ sale, start, end, originalStartsAt, originalEndsAt });

let localIds = 0;
export function freshOption(): DraftOption {
  localIds += 1;
  return { id: `local-serving-${localIds}`, bottle: false, ml: "", price: "", ...NO_DISCOUNT };
}

/** `localDiscountEndDay`: the last day of a discount ending at `endsAt`; one ending at midnight ends the day before. */
export function localDiscountEndDay(endsAt: string): string {
  const at = Date.parse(endsAt);
  const day = seoulClock(at).date;
  return isSeoulMidnight(at) ? addDays(day, -1) : day;
}

export function fromSaved(option: MenuOption): DraftOption {
  const discount = option.discount;
  return {
    id: option.menuEntryOptionId,
    bottle: isBottleServingLabel(option.optionLabel),
    ml: option.pourMl?.toString() ?? "",
    price: String(option.priceKrw),
    ...(discount
      ? {
          sale: String(discount.discountedPriceKrw),
          start: seoulClock(Date.parse(discount.startsAt)).date,
          end: localDiscountEndDay(discount.endsAt),
          originalStartsAt: discount.startsAt,
          originalEndsAt: discount.endsAt,
        }
      : NO_DISCOUNT),
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

const DATE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * `toOption`'s discount: a price from 1 won and lower than the option's price, from the start day's midnight
 * in Seoul until the midnight after the end day. A saved discount whose days were not changed keeps its own
 * instants (an imported one may start or end mid-day). The app lets the discounted price equal the price;
 * spec 3.14.2 refuses it (`DISCOUNT_NOT_LOWER`), so it is refused here (data/android 수정 필요 사항.md).
 */
export function draftDiscount(draft: DraftOption, price: number, original: OptionValue | undefined): Discount | null {
  if (draft.sale === "") return null;
  const sale = intOf(draft.sale);
  if (sale === null) throw new Error("할인 가격을 숫자로 입력해 주세요.");
  if (!(sale >= 1 && sale < price && (sale <= MAX_OWNER_MENU_PRICE_KRW || original?.discount?.discountedPriceKrw === sale))) {
    throw new Error(DISCOUNT_NOT_LOWER);
  }
  if (!DATE.test(draft.start)) throw new Error("시작일은 YYYY-MM-DD 형식이에요.");
  if (!DATE.test(draft.end)) throw new Error("종료일은 YYYY-MM-DD 형식이에요.");
  if (draft.end < draft.start) throw new Error("할인 종료일을 확인해 주세요.");
  const unchangedDays =
    draft.originalStartsAt !== "" &&
    draft.originalEndsAt !== "" &&
    draft.start === seoulClock(Date.parse(draft.originalStartsAt)).date &&
    draft.end === localDiscountEndDay(draft.originalEndsAt);
  return unchangedDays
    ? { discountedPriceKrw: sale, startsAt: draft.originalStartsAt, endsAt: draft.originalEndsAt }
    : { discountedPriceKrw: sale, startsAt: seoulStartOf(draft.start), endsAt: seoulStartOf(addDays(draft.end, 1)) };
}

export const DISCOUNT_NOT_LOWER = "할인 가격은 1원 이상, 원래 가격보다 낮아야 해요.";

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
  const typed = draftDiscount(draft, price, original);
  const discount = typed && Date.parse(typed.endsAt) > now ? typed : null;
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

const sameServing = (a: DraftOption, b: DraftOption) => a.bottle === b.bottle && a.ml === b.ml && a.price === b.price;
const sameDiscount = (a: DraftOption, b: DraftOption) => JSON.stringify(discountOf(a)) === JSON.stringify(discountOf(b));

/** A row's serving as `servingIdentityKey` tells servings apart: a bottle, or the pour in ml. */
const draftServingKey = (row: DraftOption) => servingIdentityKey(row.ml === "" ? null : Number(row.ml), row.bottle ? "Bottle" : null);

/**
 * After MENU_OUTDATED (spec 3.14.1), the edit is moved onto the item as it is now (`fresh`, its `editDraftOf`),
 * so that saving again does not undo what changed elsewhere: what the owner changed since `start` stays as
 * typed, and the rest takes the new values. A row's serving and price, and its discount, are taken apart: the
 * owner's discount stays when only the price changed elsewhere, and the reverse.
 *
 * Each row opened is found in `fresh` by its option ID, or else by the serving it opened with: an edit
 * elsewhere replaces every option of the item with new IDs (spec 3.14.4, backend `menu_edit.py`), while an
 * edit of another item keeps them. A row found takes the option's new ID. A row not found was removed
 * elsewhere and goes too, unless the owner typed in it; then it stays as a new option. Options added elsewhere
 * come after the rows. Not in the app, which does not handle MENU_OUTDATED (Codex reviews on #199 and #209).
 */
export function rebaseDraft(start: Draft, current: Draft, fresh: Draft): Draft {
  const taken = new Set<string>();
  const found = new Map<string, DraftOption>();
  const claim = (row: DraftOption, match: (option: DraftOption) => boolean) => {
    const option = fresh.options.find((candidate) => !taken.has(candidate.id) && match(candidate));
    if (option) (taken.add(option.id), found.set(row.id, option));
  };
  // By ID first, so that an option kept elsewhere is never taken by another row's serving.
  for (const row of start.options) claim(row, (option) => option.id === row.id);
  for (const row of start.options) if (!found.has(row.id)) claim(row, (option) => draftServingKey(option) === draftServingKey(row));
  const before = new Map(start.options.map((option) => [option.id, option]));
  const rows = current.options.flatMap((row) => {
    const opened = before.get(row.id);
    if (!opened) return [row];
    const saved = found.get(row.id);
    if (saved) {
      const serving = sameServing(row, opened) ? saved : row;
      return [{ ...serving, ...discountOf(sameDiscount(row, opened) ? saved : row), id: saved.id }];
    }
    if (sameServing(row, opened) && sameDiscount(row, opened)) return [];
    // Kept as a new option: its saved discount instants go with the saved option.
    return [{ ...freshOption(), bottle: row.bottle, ml: row.ml, price: row.price, ...(row.sale ? { ...discountOf(row), originalStartsAt: "", originalEndsAt: "" } : {}) }];
  });
  return {
    name: current.name === start.name ? fresh.name : current.name,
    category: current.category === start.category ? fresh.category : current.category,
    // A row the owner removed takes its option along, found or not.
    options: [...rows, ...fresh.options.filter((option) => !taken.has(option.id))],
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
