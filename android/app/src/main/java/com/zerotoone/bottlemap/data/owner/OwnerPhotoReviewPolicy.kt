package com.zerotoone.bottlemap.data.owner

/** Product identity within a photo import; avoid guessing from one shared brand word. */
private fun candidateIdentity(line: MockExtractedLine): String? =
    line.decision?.productId ?: line.suggestedProductId ?: line.candidateProductIds.singleOrNull()

private val reviewServingRegex = Regex("""(?i)\b\d{1,4}\s*(?:ml|mℓ|㎖|밀리리터)\b""")
private val reviewPriceRegex = Regex("""(?:₩\s*|￦\s*)?\d{1,3}(?:,\d{3})+\s*원?|\b\d{4,9}\s*원""")
private val reviewNonWordRegex = Regex("""[^\p{L}\p{N}]""")

/** Fallback only when canonical IDs are missing. Retain ages/editions. */
private fun photoProductName(line: MockExtractedLine): String? {
    val base=line.sourceText
        .replace(reviewServingRegex,"")
        .replace(reviewPriceRegex,"")
        .lowercase()
        .replace(reviewNonWordRegex,"")
    return base.takeIf { it.length >= 4 }
}

private fun sameReviewProduct(a: MockExtractedLine, b: MockExtractedLine): Boolean {
    if(a.kind != MockLineKind.PRODUCT || b.kind != MockLineKind.PRODUCT) return false
    val x=candidateIdentity(a)
    val y=candidateIdentity(b)
    if(x!=null && y!=null) return x==y
    val name=photoProductName(a)
    return name!=null && name==photoProductName(b)
}

/** Stable serving identity across OCR lines, reviewed options and saved menu rows. */
internal fun reviewServingKey(pourMl: Int?, label: String?): String =
    servingIdentityKey(pourMl, label)

private fun reviewServing(option: MockMenuOption): String =
    reviewServingKey(option.pourMl, option.label)

/**
 * Exclude a *product* from the whole upload (all its serving rows/photos), not
 * only one extracted 30 ml or 60 ml option row. Unrelated products remain.
 */
internal fun relatedPhotoProductLineIds(
    job: MockMenuImport, selectedLineId: String,
): List<String> {
    val lines=job.images.flatMap { it.lines }
    val selected=lines.firstOrNull { it.extractedItemId==selectedLineId }
        ?: return emptyList()
    if(selected.kind!=MockLineKind.PRODUCT) return listOf(selectedLineId)
    return lines.filter { sameReviewProduct(selected,it) }
        .map { it.extractedItemId }.ifEmpty { listOf(selectedLineId) }
}

/**
 * If the same product/serving has two recognized prices, the Owner must enter
 * one value: never choose the last photo silently. Handles exact and ambiguous
 * server matching, multiple serving rows and differing OCR option labels.
 */
internal fun requirePhotoPriceReviewOnConflict(
    images: List<MockPhotoExtraction>,
): List<MockPhotoExtraction> {
    val all=images.flatMap { it.lines }.filter { it.kind==MockLineKind.PRODUCT }
    val conflicted=mutableMapOf<String,MutableSet<String>>()
    for(line in all) for(option in line.options) {
        if(option.priceKrw<=0) continue
        if(all.any { other ->
            sameReviewProduct(line,other) && other.options.any { candidate ->
                reviewServing(option)==reviewServing(candidate) &&
                    candidate.priceKrw>0 && candidate.priceKrw!=option.priceKrw
            }
        }) {
            conflicted.getOrPut(line.extractedItemId){mutableSetOf()}
                .add(reviewServing(option))
        }
    }
    if(conflicted.isEmpty()) return images
    return images.map { image ->
        image.copy(lines=image.lines.map { line ->
            val servingIds=conflicted[line.extractedItemId].orEmpty()
            if(servingIds.isEmpty()) line else {
                val updatedOptions=line.options.map { option ->
                    if(reviewServing(option) in servingIds) option.copy(priceKrw=0)
                    else option
                }
                // Only auto-confirm when every recognized price agrees.
                val selected=candidateIdentity(line)
                line.copy(options=updatedOptions,decision=null,
                    needsPriceEntry=true,mockAutoAccepted=false,priceConflict=true,
                    candidateProductIds=if(selected!=null &&
                        (line.suggestedProductId==selected ||
                            line.candidateProductIds.size==1))
                        listOf(selected) else line.candidateProductIds)
            }
        })
    }
}

/** Post-review safety check before sending the irreversible review publish. */
internal fun conflictingReviewedPhotoPrices(job: MockMenuImport): Set<String> {
    val all=job.images.flatMap { it.lines }.filter { line ->
        line.kind==MockLineKind.PRODUCT &&
            line.decision?.kind==MockDecisionKind.SELECT_PRODUCT
    }
    val conflicted=mutableSetOf<String>()
    for(line in all) {
        val decision=line.decision ?: continue
        for(option in (decision.correctedOptions ?: line.options)) {
            val id=decision.productId ?: continue
            if(option.priceKrw>0 && all.any { other ->
                other.extractedItemId != line.extractedItemId &&
                    other.decision?.productId==id &&
                    (other.decision?.correctedOptions ?: other.options).any {
                        candidate -> reviewServing(candidate)==reviewServing(option) &&
                            candidate.priceKrw>0 && candidate.priceKrw!=option.priceKrw
                    }
            }) conflicted+=id
        }
    }
    return conflicted
}

/** The import list provides imageCount even when recovered jobs have no photo objects. */
internal fun importPhotoCount(job: MockMenuImport): Int =
    maxOf(job.imageCount,job.images.size)

/** Use the server's completedImages, bounded by the import's actual image count. */
internal fun importCompletedPhotoCount(job: MockMenuImport): Int =
    job.completedImages.coerceIn(0, importPhotoCount(job))
