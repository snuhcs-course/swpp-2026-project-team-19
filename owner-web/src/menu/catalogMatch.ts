import { MANUAL_MENU_CATEGORIES, manualMenuCategoryLabel, type MenuBrand, type MenuCategory, type MenuProduct } from "./menuRules";

/**
 * Proposing a catalog product for a menu name being added, ported from android/.../ui/owner/OwnerManualCatalogMatch.kt.
 * The candidates come from the catalog searches (spec 6, 7) and the bar's own menu; the owner confirms a
 * proposal with "맞아요" before it is linked, so nothing is linked from the text alone.
 */
export function normalizeOwnerCatalogName(name: string): string {
  return Array.from(name)
    .filter((char) => /[\p{L}\p{Nd}]/u.test(char))
    .join("")
    .toLowerCase();
}

/** "글렌 피딕12년" searches brands for "글렌피딕"; the server's brand aliases handle local spellings. */
export function manualBrandSearchQuery(menuName: string, enteredBrand: string): string {
  if (enteredBrand.trim()) return enteredBrand.trim();
  const prefix = menuName
    .trim()
    .replace(/\d.*$/, "")
    .replace(/[ \-·.()]+$/, "")
    .replace(/[ \t\n\v\f\r]+/g, "");
  return prefix.length >= 2 ? prefix : "";
}

/** Offers an existing brand; never assigns one from the text without the owner. */
export function manualBrandProposal(
  brands: readonly MenuBrand[],
  menuName: string,
  enteredBrand: string,
  rejectedBrandId: string | null,
): MenuBrand | null {
  const productText = normalizeOwnerCatalogName(menuName);
  const brandText = normalizeOwnerCatalogName(enteredBrand);
  let best: MenuBrand | null = null;
  let bestLength = -1;
  for (const brand of brands) {
    if (brand.brandId === rejectedBrandId) continue;
    const alias = normalizeOwnerCatalogName(brand.matchedAlias ?? brand.name);
    const canonical = normalizeOwnerCatalogName(brand.name);
    const matches =
      (brandText !== "" && (brandText === alias || brandText === canonical || alias.startsWith(brandText))) ||
      (brandText === "" && alias.length >= 2 && productText.startsWith(alias));
    if (matches && alias.length > bestLength) {
      best = brand;
      bestLength = alias.length;
    }
  }
  return best;
}

/** The editor shows four kinds; any other product category is "기타 주류". */
export function manualEditorCategory(product: Pick<MenuProduct, "category">): MenuCategory {
  const label = manualMenuCategoryLabel(product.category);
  return (MANUAL_MENU_CATEGORIES as readonly string[]).includes(label) ? (label as MenuCategory) : "기타 주류";
}

/** An inactive catalog product named like the menu: shown, but it cannot be chosen. */
export function inactiveOwnerCatalogMatch(products: readonly MenuProduct[], menuName: string): MenuProduct | null {
  const normalized = normalizeOwnerCatalogName(menuName);
  if (!normalized) return null;
  return (
    products.find(
      (product) =>
        product.catalogMatched &&
        !product.isActive &&
        (normalizeOwnerCatalogName(product.displayName) === normalized ||
          normalizeOwnerCatalogName(product.matchedAlias ?? "") === normalized),
    ) ?? null
  );
}

/**
 * The inactive product that stops a name from being added: only when no active catalog product has that exact
 * name or alias. The catalog search returns inactive rows beside active ones (spec 7.2: shown, not chosen), so
 * an inactive duplicate must not hide the active product it duplicates. The app checks the inactive match alone
 * (OwnerManualMenuScreen.kt); see data/android 수정 필요 사항.md item 12.
 */
export function blockingInactiveMatch(products: readonly MenuProduct[], menuName: string): MenuProduct | null {
  const inactive = inactiveOwnerCatalogMatch(products, menuName);
  if (!inactive) return null;
  const normalized = normalizeOwnerCatalogName(menuName);
  const active = products.some(
    (product) =>
      product.catalogMatched &&
      product.isActive &&
      (normalizeOwnerCatalogName(product.displayName) === normalized || normalizeOwnerCatalogName(product.matchedAlias ?? "") === normalized),
  );
  return active ? null : inactive;
}

/**
 * The one product to propose for a menu name: an exact name or alias, else a single product whose name holds
 * a name of 4 or more characters, else (with the brand known) the single product of that brand and age.
 */
export function manualProductProposal(
  products: readonly MenuProduct[],
  menuName: string,
  category: MenuCategory,
  brandId: string | null,
  rejectedProductId: string | null,
): MenuProduct | null {
  const name = normalizeOwnerCatalogName(menuName);
  if (!name) return null;
  // Items of this bar without a product are offered too, so the same name does not become a second item.
  const available = products.filter(
    (product) =>
      ((product.catalogMatched && product.isActive) || !product.catalogMatched) &&
      product.productId !== rejectedProductId &&
      manualEditorCategory(product) === category,
  );
  const exact = available.find(
    (product) =>
      normalizeOwnerCatalogName(product.displayName) === name || normalizeOwnerCatalogName(product.matchedAlias ?? "") === name,
  );
  if (exact) return exact;
  const near = available.filter((product) => name.length >= 4 && normalizeOwnerCatalogName(product.displayName).includes(name));
  if (near.length === 1) return near[0] ?? null;
  if (brandId === null) return null;
  const years = [...new Set([...menuName.matchAll(/\d{1,3}/g)].map((match) => Number(match[0])))];
  if (years.length !== 1) return null;
  const year = years[0];
  const sameAge = available.filter(
    (product) =>
      product.brandId === brandId &&
      (product.ageYears === year || (product.ageYears === null && new RegExp(`(?<!\\d)${year}(?!\\d)`).test(product.displayName))),
  );
  return sameAge.length === 1 ? (sameAge[0] ?? null) : null;
}
