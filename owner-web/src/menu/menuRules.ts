import type { components } from "../api/schema";
import { servingIdentityKey } from "./servingIdentity";

/**
 * The menu editor's rules, ported from android/.../data/owner/OwnerManualMenuRules.kt, with the app's
 * messages. The server's own rules (spec 3.14.2, 3.14.3) are checked again by the server.
 */
export type BarMenu = components["schemas"]["BarMenuResponse"];
export type MenuItem = BarMenu["items"][number];
export type MenuOption = MenuItem["options"][number];
export type Discount = NonNullable<MenuOption["discount"]>;

/** A product as the editor sees it (OwnerMockModels.kt `MockCatalogProduct`). */
export interface MenuProduct {
  productId: string;
  brandId: string;
  displayName: string;
  category: string;
  ageYears: number | null;
  isActive: boolean;
  matchedAlias: string | null;
  /** A catalog product with a real productId; false for an item on this bar without a product. */
  catalogMatched: boolean;
}

/** A brand (OwnerMockModels.kt `MockBrand`). */
export interface MenuBrand {
  brandId: string;
  name: string;
  matchedAlias: string | null;
}

/** An option as the rules see it (OwnerMockModels.kt `MockMenuOption`); `optionId` ties it to the saved one. */
export interface OptionValue {
  optionId: string;
  label: string | null;
  pourMl: number | null;
  priceKrw: number;
  discount: Discount | null;
}

/** Spec 3.14.2: at most three options. */
export const MANUAL_MENU_MAX_OPTIONS = 3;
/** Spec 3.14.2: under 100 million won, at most 8 digits. */
export const MAX_OWNER_MENU_PRICE_KRW = 99_999_999;
export const MAX_OWNER_MENU_PRICE_DIGITS = 8;
export const MAX_POUR_ML = 32_767;

/** `ownerPriceInput`: the digits of what was typed, at most 8. */
export function ownerPriceInput(raw: string): string;
/** Once 8 digits are there, another digit is refused even in the middle; a long paste keeps its first 8. */
export function ownerPriceInput(previous: string, proposed: string): string;
export function ownerPriceInput(first: string, proposed?: string): string {
  if (proposed === undefined) return digitsOf(first).slice(0, MAX_OWNER_MENU_PRICE_DIGITS);
  const digits = digitsOf(proposed);
  if (digits.length <= MAX_OWNER_MENU_PRICE_DIGITS) return digits;
  if (first.length >= MAX_OWNER_MENU_PRICE_DIGITS) return first;
  return digits.slice(0, MAX_OWNER_MENU_PRICE_DIGITS);
}

const digitsOf = (value: string) => value.replace(/\D/g, "");

/** The editor's four kinds. The server keeps only whisky and other (spec 3.14.3 `kind`). */
export const MANUAL_MENU_CATEGORIES = ["위스키", "칵테일", "안주", "기타 주류"] as const;
export type MenuCategory = (typeof MANUAL_MENU_CATEGORIES)[number];

export function manualMenuCategoryCode(label: MenuCategory): string {
  switch (label) {
    case "위스키":
      return "whisky";
    case "칵테일":
      return "cocktail";
    case "안주":
      return "snack";
    case "기타 주류":
      return "otherAlcohol";
  }
}

export function manualMenuCategoryLabel(code: string): string {
  switch (code.toLowerCase()) {
    case "whisky":
    case "whiskey":
      return "위스키";
    case "cocktail":
      return "칵테일";
    case "snack":
      return "안주";
    case "otheralcohol":
      return "기타 주류";
    default:
      return code;
  }
}

/** OwnerPreviewV4Menu.kt `ownerV4Category`: the group a product is listed under. */
export function ownerV4Category(category: string): string {
  switch (category.toLowerCase()) {
    case "whisky":
    case "whiskey":
      return "위스키";
    case "brandy":
      return "브랜디";
    case "cocktail":
      return "칵테일";
    case "snack":
      return "안주";
    case "otheralcohol":
      return "기타 주류";
    case "gin":
      return "진";
    case "rum":
      return "럼";
    case "wine":
      return "와인";
    case "beer":
      return "맥주";
    case "other":
      return "기타";
    default:
      return category;
  }
}

/** A whisky's name without its brand: "라가불린 10년" under 라가불린 reads "10년". */
export function manualMenuShortName(product: Pick<MenuProduct, "displayName" | "category">, brandName: string): string {
  const name = product.displayName.trim();
  if (manualMenuCategoryLabel(product.category) !== "위스키") return name;
  const remaining = name
    .slice(name.startsWith(brandName) ? brandName.length : 0)
    .trim()
    .replace(/^[·:\-—]+/, "")
    .trim();
  return name.startsWith(brandName) && remaining ? remaining : name;
}

/**
 * The product of a menu item (LiveOwnerScreenRepository.kt): a linked item is its catalog product; an item
 * without one gets "unlinked:<barMenuItemId>", whisky or other by its `kind` (the server keeps no finer kind).
 */
export function menuProductOf(item: MenuItem): MenuProduct {
  return {
    productId: item.productId ?? `unlinked:${item.barMenuItemId}`,
    brandId: item.brandId ?? "",
    displayName: item.productName ?? item.displayName,
    category: item.category ?? (item.kind === "whisky" ? "whisky" : "otherAlcohol"),
    ageYears: null,
    isActive: true,
    matchedAlias: null,
    catalogMatched: item.productId !== null,
  };
}

/** The brands of the menu's items (LiveOwnerScreenRepository.kt). */
export function menuBrandsOf(items: readonly MenuItem[]): MenuBrand[] {
  const brands = new Map<string, MenuBrand>();
  for (const item of items) {
    if (item.brandId && !brands.has(item.brandId)) {
      brands.set(item.brandId, { brandId: item.brandId, name: item.brandName ?? item.displayName, matchedAlias: null });
    }
  }
  return [...brands.values()];
}

const searchKey = (value: string) => value.normalize("NFKC").toLowerCase().replace(/\s/g, "");

/**
 * `manualMenuMatches`: a search of this bar's own menu, not the catalog. Names without a product ("위스키 1")
 * match "위스키1" whatever the spacing or character width.
 */
export function manualMenuMatches(item: MenuItem, product: MenuProduct | null, brandName: string, query: string): boolean {
  const term = query.trim();
  if (!term) return true;
  const candidates = [item.displayName, product?.displayName, brandName, product?.category, ...item.options.flatMap((option) => [
    option.pourMl?.toString(),
    option.optionLabel,
    option.priceKrw.toString(),
  ])].filter((value): value is string => typeof value === "string");
  const key = searchKey(term);
  return candidates.some((candidate) => candidate.toLowerCase().includes(term.toLowerCase()) || searchKey(candidate).includes(key));
}

const sameOriginal = (original: readonly OptionValue[], option: OptionValue, same: (saved: OptionValue) => boolean) =>
  original.some((saved) => saved.optionId === option.optionId && same(saved));

/**
 * `manualMenuOptionError`: 1 to 3 options; one price for anything but whisky; prices from 1 won to under
 * 100 million won (a saved price above it may stay as it is); whisky pours from 1 to 32767 ml; no two
 * options for one serving (servingIdentityKey); a discount lower than the price and ending after it starts.
 */
export function manualMenuOptionError(options: readonly OptionValue[], category: string, original: readonly OptionValue[] = []): string | null {
  const whisky = manualMenuCategoryLabel(category) === "위스키";
  if (options.length === 0 || options.length > MANUAL_MENU_MAX_OPTIONS) return "가격 옵션은 1~3개여야 해요.";
  if (!whisky && options.length !== 1) return "이 메뉴는 가격을 하나만 등록할 수 있어요.";
  if (
    options.some(
      (option) =>
        !(option.priceKrw >= 1 && option.priceKrw <= MAX_OWNER_MENU_PRICE_KRW) &&
        !sameOriginal(original, option, (saved) => saved.priceKrw === option.priceKrw),
    )
  ) {
    return "가격은 1원 이상, 1억 원 미만이어야 해요.";
  }
  if (whisky && options.some((option) => option.pourMl !== null && !(option.pourMl >= 1 && option.pourMl <= MAX_POUR_ML))) {
    return "용량을 입력하거나 Bottle 판매를 선택해 주세요.";
  }
  if (
    options.some((option) => {
      const price = option.discount?.discountedPriceKrw;
      return (
        price !== undefined &&
        price > MAX_OWNER_MENU_PRICE_KRW &&
        !sameOriginal(original, option, (saved) => saved.discount?.discountedPriceKrw === price)
      );
    })
  ) {
    return "할인 가격은 1억 원 미만이어야 해요.";
  }
  if (new Set(options.map((option) => servingIdentityKey(option.pourMl, option.label))).size !== options.length) {
    return "같은 제품에 동일한 용량 옵션을 중복 등록할 수 없어요.";
  }
  if (
    options.some(
      (option) =>
        option.discount !== null &&
        (option.discount.discountedPriceKrw <= 0 ||
          option.discount.discountedPriceKrw > option.priceKrw ||
          Date.parse(option.discount.startsAt) >= Date.parse(option.discount.endsAt)),
    )
  ) {
    return "할인 가격과 기간을 확인해 주세요.";
  }
  return null;
}

/** `existingBarProductMenu`: the item of a product on this menu. Products are told apart by ID, never by name. */
export function existingBarProductMenu(items: readonly MenuItem[], productId: string): MenuItem | undefined {
  return items.find((item) => menuProductOf(item).productId === productId);
}
