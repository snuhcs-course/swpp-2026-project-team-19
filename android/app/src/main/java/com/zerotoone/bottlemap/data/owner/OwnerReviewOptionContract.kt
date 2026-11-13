package com.zerotoone.bottlemap.data.owner

import com.zerotoone.bottlemap.network.ReviewItemDto

/**
 * Serializes PR #164's final options[] contract. This never manufactures an
 * OCR source ID: options added by the reviewer send extractedOptionId=null.
 */
internal fun ownerFinalReviewOptions(
    item: ReviewItemDto,
    decision: MockReviewDecision,
    defaultPourMl: Int,
    whisky: Boolean,
): List<Map<String, Any?>> {
    val rawIds = item.options.mapTo(mutableSetOf()) { it.extractedOptionId }
    val selected = decision.correctedOptions ?: item.options.map { option ->
        MockMenuOption(
            optionId = option.extractedOptionId,
            label = option.extractedOptionLabel,
            pourMl = option.extractedPourMl,
            priceKrw = option.extractedPriceKrw ?: 0,
        )
    }
    require(selected.size in 1..10) { "검수 메뉴의 가격 옵션은 1~10개여야 해요." }
    val retained = selected.mapNotNull { it.optionId.takeIf(rawIds::contains) }
    require(retained.distinct().size == retained.size) {
        "동일한 OCR 옵션을 두 번 게시할 수 없어요."
    }
    return selected.map { option ->
        require(option.priceKrw in 1..99_999_999) { "가격을 확인해 주세요." }
        val isBottle = option.label?.lowercase() in listOf("bottle", "병")
        mapOf(
            "extractedOptionId" to option.optionId.takeIf(rawIds::contains),
            "optionLabel" to option.label,
            "pourMl" to (option.pourMl ?: if (whisky && !isBottle) defaultPourMl else null),
            "priceKrw" to option.priceKrw,
        )
    }
}
