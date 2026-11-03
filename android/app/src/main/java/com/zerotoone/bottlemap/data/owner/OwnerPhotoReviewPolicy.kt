package com.zerotoone.bottlemap.data.owner

/**
 * Owner photo policy: conflicting prices for one canonical product and one
 * option identity must be entered by the owner, not resolved by photo order.
 *
 * A server exact-match identity is accepted; only its conflicting prices lose
 * auto-acceptance. Each affected line keeps the real extractedOptionId so that
 * the current review-and-apply contract can accept correctedPriceKrw.
 */
internal fun requirePhotoPriceReviewOnConflict(
    images: List<MockPhotoExtraction>,
): List<MockPhotoExtraction> {
    val pricesByOption = mutableMapOf<Pair<String, String>, MutableSet<Int>>()
    images.flatMap { it.lines }.filter { line ->
        line.kind == MockLineKind.PRODUCT &&
            line.mockAutoAccepted &&
            line.suggestedProductId != null &&
            line.decision?.kind == MockDecisionKind.SELECT_PRODUCT
    }.forEach { line ->
        val productId = requireNotNull(line.suggestedProductId)
        line.options.forEach { option ->
            if (option.priceKrw > 0) pricesByOption
                .getOrPut(productId to option.identityKey()) { mutableSetOf() }
                .add(option.priceKrw)
        }
    }
    val conflicts = pricesByOption.filterValues { it.size > 1 }.keys
    if(conflicts.isEmpty()) return images
    return images.map { image ->
        image.copy(lines = image.lines.map { line ->
            val productId = line.suggestedProductId
            if(productId == null || !line.mockAutoAccepted ||
                line.decision?.kind != MockDecisionKind.SELECT_PRODUCT) line
            else {
                val conflictingOptions = line.options.map { option ->
                    if((productId to option.identityKey()) in conflicts)
                        option.copy(priceKrw = 0) else option
                }
                if(conflictingOptions == line.options) line else line.copy(
                    options = conflictingOptions,
                    decision = null,
                    needsPriceEntry = true,
                    mockAutoAccepted = false,
                    // Exact-match products don't need to be re-matched:
                    // route directly to the existing price input page.
                    candidateProductIds = listOf(productId),
                )
            }
        })
    }
}

/**
 * Never let photo ordering choose a price silently after owner review.
 * The same existing product / pour size must have one agreed final price
 * across all photos before the first irreversible publish API call.
 */
internal fun conflictingReviewedPhotoPrices(job: MockMenuImport): Set<String> {
    val prices = mutableMapOf<Pair<String, String>, MutableSet<Int>>()
    job.images.flatMap { it.lines }.forEach { line ->
        val decision = line.decision ?: return@forEach
        if(decision.kind != MockDecisionKind.SELECT_PRODUCT) return@forEach
        val productId = decision.productId ?: return@forEach
        (decision.correctedOptions ?: line.options).forEach { option ->
            if(option.priceKrw > 0) prices
                .getOrPut(productId to option.identityKey()) { mutableSetOf() }
                .add(option.priceKrw)
        }
    }
    return prices.filterValues { it.size > 1 }
        .keys.mapTo(mutableSetOf()) { it.first }
}
