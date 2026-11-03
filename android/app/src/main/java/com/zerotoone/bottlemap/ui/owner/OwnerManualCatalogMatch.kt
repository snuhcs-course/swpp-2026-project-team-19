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

/** After brand confirmation, propose the single catalog product with matching age. */
internal fun manualProductProposal(
    products: List<MockCatalogProduct>, menuName: String, category: String,
    brandId: String?, rejectedProductId: String?,
): MockCatalogProduct? {
    val name=normalizeOwnerCatalogName(menuName)
    if(name.isEmpty()) return null
    val available=products.filter {
        it.isActive && it.catalogMatched && it.productId!=rejectedProductId &&
            manualMenuCategoryLabel(it.category)==category
    }
    val exact=available.firstOrNull {
        normalizeOwnerCatalogName(it.displayName)==name
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
