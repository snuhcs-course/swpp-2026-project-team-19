package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.MockBrand
import com.zerotoone.bottlemap.data.owner.MockCatalogProduct
import com.zerotoone.bottlemap.data.owner.manualMenuCategoryLabel

internal fun normalizeOwnerCatalogName(name: String): String =
    name.filter(Char::isLetterOrDigit).lowercase()

/** "글렌 피딕12년" -> "글렌피딕"; existing server brand aliases handle local spellings. */
internal fun manualBrandSearchQuery(menuName: String, enteredBrand: String): String {
    if(enteredBrand.isNotBlank()) return enteredBrand.trim()
    val prefix=menuName.trim().replace(Regex("""\d.*$"""),"")
        .trimEnd(' ','-','·','.','(',')')
        .replace(Regex("""\s+"""),"")
    return prefix.takeIf { it.length>=2 }.orEmpty()
}

/** Offer the existing brand, never silently assign an identity from the text. */
internal fun manualBrandProposal(
    brands: List<MockBrand>, menuName: String, enteredBrand: String,
    rejectedBrandId: String?,
): MockBrand? {
    val productText=normalizeOwnerCatalogName(menuName)
    val brandText=normalizeOwnerCatalogName(enteredBrand)
    return brands.filter { it.brandId!=rejectedBrandId }
        .filter { brand ->
            val alias=normalizeOwnerCatalogName(brand.matchedAlias ?: brand.name)
            val canonical=normalizeOwnerCatalogName(brand.name)
            (brandText.isNotEmpty() &&
                (brandText==alias || brandText==canonical ||
                    alias.startsWith(brandText))) ||
                (brandText.isEmpty() && alias.length>=2 && productText.startsWith(alias))
        }.maxByOrNull { normalizeOwnerCatalogName(it.matchedAlias ?: it.name).length }
}

/** The menu editor only exposes the four top-level UI categories.
 * Custom alcohol labels (e.g. "맥주") remain the stored product category.
 */
internal fun manualEditorCategory(product: MockCatalogProduct): String =
    manualMenuCategoryLabel(product.category).takeIf {
        it in com.zerotoone.bottlemap.data.owner.MANUAL_MENU_CATEGORIES
    } ?: "기타 주류"

internal fun manualEditorAlcoholKind(product: MockCatalogProduct): String =
    product.otherAlcoholKind?.takeIf { it.isNotBlank() } ?: if (
        manualEditorCategory(product) == "기타 주류" &&
        product.category != "otherAlcohol"
    ) ownerV4Category(product) else ""

/** An inactive server catalogue match stays visible but cannot be selected. */
internal fun inactiveOwnerCatalogMatch(
    products: List<MockCatalogProduct>, menuName: String,
): MockCatalogProduct? {
    val normalized = normalizeOwnerCatalogName(menuName)
    if(normalized.isEmpty()) return null
    return products.firstOrNull { it.catalogMatched && !it.isActive &&
        (normalizeOwnerCatalogName(it.displayName) == normalized ||
            normalizeOwnerCatalogName(it.matchedAlias.orEmpty()) == normalized) }
}

/** Fresh server name check must never block a local beer with an old canonical beer row. */
internal fun manualFreshCatalogExactMatch(
    products: List<MockCatalogProduct>, name: String,
    category: String, rejectedProductId: String?,
): MockCatalogProduct? {
    if (category != "위스키") return null
    val normalized = normalizeOwnerCatalogName(name)
    if (normalized.isBlank()) return null
    return products.firstOrNull {
        it.isActive && it.catalogMatched && it.category == "whisky" &&
            it.productId != rejectedProductId &&
            (normalizeOwnerCatalogName(it.displayName) == normalized ||
                normalizeOwnerCatalogName(it.matchedAlias.orEmpty()) == normalized)
    }
}

/** After brand confirmation, propose the single catalog product with matching age. */
internal fun manualProductProposal(
    products: List<MockCatalogProduct>, menuName: String, category: String,
    brandId: String?, rejectedProductId: String?,
): MockCatalogProduct? {
    val name=normalizeOwnerCatalogName(menuName)
    if(name.isEmpty()) return null
    // Local unverified products (including deleted menu rows) must be offered for
    // explicit re-linking, otherwise the screen silently creates a second product.
    // Production candidates are catalogMatched and still require isActive.
    val available=products.filter {
        ((it.catalogMatched && it.isActive && it.category == "whisky") ||
            !it.catalogMatched) &&
            it.productId!=rejectedProductId &&
            manualEditorCategory(it)==category
    }
    val exact=available.firstOrNull {
        normalizeOwnerCatalogName(it.displayName)==name ||
            normalizeOwnerCatalogName(it.matchedAlias.orEmpty())==name
    }
    if(exact!=null) return exact
    val near=available.filter {
        name.length>=4 && normalizeOwnerCatalogName(it.displayName).contains(name)
    }
    if(near.size==1) return near.single()
    if(brandId==null) return null
    val years=Regex("""\d{1,3}""").findAll(menuName).mapNotNull {
        it.value.toIntOrNull()
    }.toList().distinct()
    if(years.size!=1) return null
    val sameAge=available.filter {
        it.brandId==brandId &&
            (it.ageYears==years.single() ||
                (it.ageYears==null &&
                    Regex("""(?<!\d)""" + years.single().toString() + """(?!\d)""")
                        .containsMatchIn(it.displayName)))
    }
    return sameAge.singleOrNull()
}
