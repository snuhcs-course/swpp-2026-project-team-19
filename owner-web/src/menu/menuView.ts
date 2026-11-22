import { monthDay, seoulClock } from "../bar/seoulTime";
import type { BarDetail } from "../owner/queries";
import { MANUAL_MENU_CATEGORIES, manualMenuMatches, menuProductOf, ownerV4Category, type MenuItem, type MenuOption } from "./menuRules";

/**
 * How the owner's menu is shown, from android/.../ui/owner/OwnerManualMenuScreen.kt (the list) and
 * OwnerSharedMenuRow.kt (a row).
 */

/** OwnerManualMenuScreen.kt: nothing on the menu changes while a menu photo import is unfinished (spec 3.14.7). */
export const MENU_LOCKED = "사진으로 메뉴 등록 작업 중에는 메뉴를 수정할 수 없어요.";

/** `ownerOptionDiscountActive`: the discounted price applies from `startsAt` until `endsAt` (spec 3.9). */
export function discountActive(option: MenuOption, now: number): boolean {
  const discount = option.discount;
  return discount !== null && now >= Date.parse(discount.startsAt) && now < Date.parse(discount.endsAt);
}

export const displayPrice = (option: MenuOption, now: number): number =>
  discountActive(option, now) && option.discount ? option.discount.discountedPriceKrw : option.priceKrw;

export const won = (price: number): string => `${price.toLocaleString("ko-KR")}원`;

/** `ownerDisplayDate`: "MM.dd" in Seoul, or "없음". */
export const menuDate = (at: string | null | undefined): string => (at ? monthDay(seoulClock(Date.parse(at)).date) : "없음");

/** The home's last update: the later of the last publish and the last confirmation (spec 3.6 `currentMenu`). */
export function lastMenuUpdate(currentMenu: BarDetail["currentMenu"]): string | null {
  if (!currentMenu) return null;
  const { publishedAt, confirmedAt } = currentMenu;
  return confirmedAt && Date.parse(confirmedAt) > Date.parse(publishedAt) ? confirmedAt : publishedAt;
}

export interface MenuGroup {
  category: string;
  /** Whisky is listed by brand ("기타 브랜드" without one); other kinds in one list (brand ""). */
  brands: { brand: string; items: MenuItem[] }[];
}

/** The menu's items matching `query`, by kind (the editor's four first) and, for whisky, by brand. */
export function groupMenu(items: readonly MenuItem[], query: string): { visible: number; groups: MenuGroup[] } {
  const visible = items.filter((item) => manualMenuMatches(item, menuProductOf(item), item.brandName ?? "", query));
  const categoryOf = (item: MenuItem) => ownerV4Category(menuProductOf(item).category);
  const categories = [...MANUAL_MENU_CATEGORIES, ...new Set(visible.map(categoryOf))].filter((value, index, all) => all.indexOf(value) === index);
  const groups = categories.flatMap((category) => {
    const rows = visible.filter((item) => categoryOf(item) === category);
    if (rows.length === 0) return [];
    if (category !== "위스키") return [{ category, brands: [{ brand: "", items: rows }] }];
    const brands = new Map<string, MenuItem[]>();
    for (const item of rows) {
      const brand = item.brandName ?? "";
      brands.set(brand, [...(brands.get(brand) ?? []), item]);
    }
    return [{ category, brands: [...brands].map(([brand, list]) => ({ brand: brand || "기타 브랜드", items: list })) }];
  });
  return { visible: visible.length, groups };
}
