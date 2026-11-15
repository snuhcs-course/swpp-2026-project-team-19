package com.zerotoone.bottlemap.data.owner

import java.util.UUID

/**
 * PR #164 (API §3.14.3): a direct Owner menu add MUST send exactly one
 * canonical productId or bar-only kind. A newly looked-up canonical product
 * may not be in the menu snapshot yet; catalogMatched is the identity source,
 * not whether the UI happened to stage it as newProduct.
 *
 * Never send synthetic local IDs, create global catalog products, or
 * downgrade an explicit catalog selection to an unlinked whisky.
 */
internal fun ownerAddMenuIdentity(
    productId: String,
    stagedProduct: MockCatalogProduct?,
    snapshotProduct: MockCatalogProduct?,
): Map<String, String> {
    val product = stagedProduct ?: snapshotProduct
        ?: error("선택한 상품 정보를 확인하지 못했어요. 다시 검색해 주세요.")
    require(product.productId == productId) {
        "다른 상품의 ID로 메뉴를 등록할 수 없어요."
    }
    if (product.catalogMatched) {
        require(runCatching { UUID.fromString(productId) }.isSuccess) {
            "카탈로그 상품 ID를 확인하지 못했어요. 다시 선택해 주세요."
        }
        return mapOf("productId" to productId)
    }
    return mapOf("kind" to if (product.category == "whisky") "whisky" else "other")
}
