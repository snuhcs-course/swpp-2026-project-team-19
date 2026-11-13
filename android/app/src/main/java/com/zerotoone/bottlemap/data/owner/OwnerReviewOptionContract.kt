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
    existingOptions: List<MockMenuOption> = emptyList(),
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
    // The server currently compares (optionLabel, pourMl), so use a single
    // stable wire representation for newly reviewed glass servings. Original
    // OCR option IDs remain intact; prior persisted bar options are untouched.
    val finalOptions = selected.map { option ->
        require(option.priceKrw in 1..99_999_999) { "가격을 확인해 주세요." }
        val bottle = isBottleServingLabel(option.label)
        val pour = if (bottle) null
            else option.pourMl ?: if (whisky) defaultPourMl else null
        require(pour == null || pour in 1..32767) { "용량을 확인해 주세요." }
        // Backend #164 still uses (label,pour) literally. For an ALREADY
        // published serving, reuse its literal label so a 30ml "샷" does not
        // become a second 30ml option beside that saved row. New servings
        // use a null glass label; the UI always renders their ml.
        val sameVolume = existingOptions.filter {
            servingIdentityKey(it.pourMl, it.label) ==
                servingIdentityKey(pour, if (bottle) "Bottle" else option.label)
        }
        require(sameVolume.size <= 1) {
            "기존 매장에 같은 용량이 중복 등록되어 있어요. 기존 메뉴를 확인해 주세요."
        }
        val label = when {
            sameVolume.isNotEmpty() -> sameVolume.single().label
            bottle -> "Bottle"
            pour != null -> null // not "잔" or "샷": option is identified by its ml
            else -> option.label
        }
        mapOf(
            "extractedOptionId" to option.optionId.takeIf(rawIds::contains),
            "optionLabel" to label,
            // Legacy bottles may have a stored capacity even though new
            // Bottle options use null pour. Preserve that exact server key
            // when updating an existing row instead of creating a twin.
            "pourMl" to (sameVolume.singleOrNull()?.pourMl ?: pour),
            "priceKrw" to option.priceKrw,
        )
    }
    val keys = finalOptions.map { option ->
        servingIdentityKey(option["pourMl"] as Int?, option["optionLabel"] as String?)
    }
    require(keys.distinct().size == keys.size) {
        "같은 용량의 옵션이 중복됐어요. 가격을 하나로 정리해 주세요."
    }
    return finalOptions
}
