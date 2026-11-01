package com.zerotoone.bottlemap.data.owner

/** Owner Flow 6. Local-only policy: this is NOT a backend request or API contract. */
const val MANUAL_MENU_MAX_OPTIONS = 3
/** Mock UI input policy only; no unagreed Backend price field constraints. */
const val MAX_OWNER_MENU_PRICE_KRW = 99_999_999
const val MAX_OWNER_MENU_PRICE_DIGITS = 8
fun ownerPriceInput(raw: String): String = raw.filter(Char::isDigit)
    .take(MAX_OWNER_MENU_PRICE_DIGITS)

/** Once 8 digits are present, reject insertion (even in the middle), preserving
 * existing digits. An oversized paste before the limit accepts at most 8 digits. */
fun ownerPriceInput(previous: String, proposed: String): String {
    val digits = proposed.filter(Char::isDigit)
    return when {
        digits.length <= MAX_OWNER_MENU_PRICE_DIGITS -> digits
        previous.length >= MAX_OWNER_MENU_PRICE_DIGITS -> previous
        else -> digits.take(MAX_OWNER_MENU_PRICE_DIGITS)
    }
}

val MANUAL_MENU_CATEGORIES = listOf("위스키", "칵테일", "안주", "기타 주류")

fun manualMenuCategoryCode(label: String): String = when (label) {
    "위스키" -> "whisky"
    "칵테일" -> "cocktail"
    "안주" -> "snack"
    "기타 주류" -> "otherAlcohol"
    else -> error("Unknown local menu category")
}
fun manualMenuCategoryLabel(code: String): String = when (code.lowercase()) {
    "whisky", "whiskey" -> "위스키"
    "cocktail" -> "칵테일"
    "snack" -> "안주"
    "otheralcohol" -> "기타 주류"
    else -> code
}
fun manualMenuShortName(product: MockCatalogProduct, brandName: String): String {
    val name = product.displayName.trim()
    if (manualMenuCategoryLabel(product.category) != "위스키") return name
    val remaining = name.removePrefix(brandName).trim().trimStart('·', ':', '-', '—').trim()
    return if (name.startsWith(brandName) && remaining.isNotEmpty()) remaining else name
}
fun manualMenuMatches(
    item: MockBarMenuItem, product: MockCatalogProduct?, brandName: String, query: String
): Boolean {
    val term = query.trim()
    if (term.isEmpty()) return true
    val candidates = listOfNotNull(item.displayNameOverride, product?.displayName,
        brandName, product?.category,
        product?.otherAlcoholKind) + item.options.flatMap { o ->
        listOfNotNull(o.pourMl?.toString(), o.label, o.priceKrw.toString())
    }
    return candidates.any { it.contains(term, ignoreCase = true) }
}
fun manualMenuOptionError(options: List<MockMenuOption>, category: String, original: List<MockMenuOption> = emptyList()): String? {
    if (options.isEmpty() || options.size > MANUAL_MENU_MAX_OPTIONS) return "가격 옵션은 1~3개여야 해요."
    if (manualMenuCategoryLabel(category) != "위스키" && options.size != 1)
        return "이 메뉴는 가격을 하나만 등록할 수 있어요."
    if (options.any { option -> option.priceKrw !in 1..MAX_OWNER_MENU_PRICE_KRW &&
            original.none { it.optionId == option.optionId && it.priceKrw == option.priceKrw } })
        return "가격은 1원 이상, 1억 원 미만이어야 해요."
    if (manualMenuCategoryLabel(category) == "위스키" && options.any {
            it.pourMl != null && it.pourMl !in 1..32767
        }) return "용량을 입력하거나 Bottle 판매를 선택해 주세요."
    if (options.distinctBy { it.identityKey() }.size != options.size)
        return "같은 제품에 동일한 용량 옵션을 중복 등록할 수 없어요."
    if (options.any { it.discount != null && (
            it.discount.discountedPriceKrw <= 0 ||
            it.discount.discountedPriceKrw > it.priceKrw ||
            it.discount.startAtEpochMs >= it.discount.endAtEpochMs
        ) }) return "할인 가격과 기간을 확인해 주세요."
    return null
}

/**
 * IDs, never text, define canonical equality. 30ml and Bottle are options
 * under one product ID, while two ages from one brand have different IDs.
 */
fun existingBarProductMenu(
    items: List<MockBarMenuItem>, barId: String, productId: String,
): MockBarMenuItem? = items.firstOrNull { it.barId == barId && it.productId == productId }
