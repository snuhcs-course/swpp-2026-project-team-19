import type { MenuProduct } from "./menuRules";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type AddIdentity = { productId: string } | { kind: "whisky" | "other" };

/**
 * What an add sends to name the item (spec 3.14.3), ported from android/.../data/owner/OwnerMenuIdentityContract.kt
 * `ownerAddMenuIdentity`: exactly one of a catalog `productId` and a `kind` for an item without a product.
 * A catalog product found by a fresh search may not be on the menu yet, so `catalogMatched` decides, not where
 * the product came from. Never a made-up ID, never a new catalog product (`newProduct` is for operators).
 */
export function ownerAddMenuIdentity(productId: string, staged: MenuProduct | null, snapshot: MenuProduct | null): AddIdentity {
  const product = staged ?? snapshot;
  if (!product) throw new Error("선택한 상품 정보를 확인하지 못했어요. 다시 검색해 주세요.");
  if (product.productId !== productId) throw new RangeError("다른 상품의 ID로 메뉴를 등록할 수 없어요.");
  if (product.catalogMatched) {
    if (!UUID.test(productId)) throw new RangeError("카탈로그 상품 ID를 확인하지 못했어요. 다시 선택해 주세요.");
    return { productId };
  }
  return { kind: product.category === "whisky" ? "whisky" : "other" };
}
