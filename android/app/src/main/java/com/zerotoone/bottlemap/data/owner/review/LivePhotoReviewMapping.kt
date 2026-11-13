package com.zerotoone.bottlemap.data.owner.review

import com.zerotoone.bottlemap.data.owner.MockBar
import com.zerotoone.bottlemap.data.owner.MockMenuOption
import com.zerotoone.bottlemap.data.owner.MockNewProductDraft
import com.zerotoone.bottlemap.data.owner.MockOwnerSnapshot
import com.zerotoone.bottlemap.data.owner.MockReviewDecision
import com.zerotoone.bottlemap.data.owner.MockDecisionKind
import com.zerotoone.bottlemap.data.owner.reviewServingKey
import com.zerotoone.bottlemap.network.MenuImportStatusDto
import com.zerotoone.bottlemap.network.ReviewItemDto
import com.zerotoone.bottlemap.ui.owner.review.CatalogProduct
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewRules
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import com.zerotoone.bottlemap.ui.owner.review.PriceChoice
import com.zerotoone.bottlemap.ui.owner.review.RecognizedOffer
import com.zerotoone.bottlemap.ui.owner.review.ReviewItem
import com.zerotoone.bottlemap.ui.owner.review.ReviewItemType
import com.zerotoone.bottlemap.ui.owner.review.ReviewMatch
import com.zerotoone.bottlemap.ui.owner.review.ReviewOption
import com.zerotoone.bottlemap.ui.owner.review.VolumeSource
import com.zerotoone.bottlemap.ui.owner.review.validPrice
import com.zerotoone.bottlemap.ui.owner.review.validVolume

/** Recovery after an uncertain network response must use this exact import ID. */
internal fun isAppliedReviewImport(status: MenuImportStatusDto, expectedId: String): Boolean =
    status.menuImportId == expectedId && status.status == "applied"

/** The agreed server DTO is the sole source of extracted IDs and option counts. */
internal fun mapServerPhotoReview(
    response: MenuImportStatusDto, snapshot: MockOwnerSnapshot,
): PhotoReviewState {
    require(response.status == "ready_for_review" && response.reviewVersion != null) {
        "검수할 수 없는 메뉴판 작업이에요."
    }
    val bar = snapshot.bars.firstOrNull { it.barId == response.barId }
        ?: error("검수할 매장 정보를 불러오지 못했어요.")
    val defaultPour = bar.defaultPourMl ?: 30
    val lines = response.images.sortedBy { it.imageOrder }.flatMap { image ->
        image.items.sortedBy { it.itemOrder }.map { dto ->
            mapServerReviewItem(dto, image.imageOrder, image.imageUrl, bar, snapshot, defaultPour)
        }
    }
    require(lines.map { it.id }.distinct().size == lines.size) {
        "서버에서 중복된 메뉴 검수 항목을 받았어요."
    }
    return PhotoReviewState(items = lines, defaultPour = defaultPour.toDouble())
}

private fun isBottle(label: String?): Boolean =
    label?.trim()?.lowercase() in setOf("bottle", "병")

/** A missing OCR pour only inherits the bar default for an explicit glass. */
private fun isGlass(label: String?): Boolean {
    val text = label?.trim()?.lowercase().orEmpty()
    return text.startsWith("잔") || text.startsWith("샷") ||
        text.startsWith("glass") || text.startsWith("shot")
}

private fun mapServerReviewItem(
    dto: ReviewItemDto, photoOrder: Int, photoUrl: String, bar: MockBar,
    snapshot: MockOwnerSnapshot, defaultPour: Int,
): ReviewItem {
    val recognized = dto.options.sortedBy { it.optionOrder }
    // Keep ALL OCR options visible for owner review, including 4+.
    // Legacy UI review limit may be smaller than the server's 1..10 bound; never drop OCR options silently.
    val selectedCandidate = dto.candidates.firstOrNull {
        it.productId == dto.proposedProductId
    }
    val category = dto.extractedKind ?: selectedCandidate?.category ?: dto.newProductDraft?.category ?: "whisky"
    val nonProduct = dto.effectiveLineType !in setOf("product", "unknown")
    val other = nonProduct || !category.equals("whisky", ignoreCase = true)
    val match = when {
        other -> ReviewMatch.NEW
        dto.initialResolutionStatus == "exact_match" && dto.proposedProductId != null ->
            ReviewMatch.EXACT
        dto.candidates.size > 1 -> ReviewMatch.CANDIDATE
        dto.candidates.size == 1 -> ReviewMatch.AMBIGUOUS
        else -> ReviewMatch.NEW
    }
    val linkedId = dto.proposedProductId.takeIf {
        match == ReviewMatch.EXACT && !other && !nonProduct
    }
    // Keep the current bar price for each matching catalog product.
    // A candidate linked after initial review still needs a price-choice prompt.
    val firstScanned = recognized.firstOrNull()
    val existingPrices = snapshot.menuItems.filter { it.barId == bar.barId }
        .mapNotNull { row ->
            val match = row.options.firstOrNull { saved ->
                (isBottle(saved.label) && isBottle(firstScanned?.extractedOptionLabel)) ||
                    (!isBottle(saved.label) && !isBottle(firstScanned?.extractedOptionLabel) &&
                        saved.pourMl != null &&
                        saved.pourMl == (firstScanned?.extractedPourMl ?: defaultPour))
            } ?: row.options.singleOrNull().takeIf {
                firstScanned?.extractedPourMl == null && it != null && !isBottle(it.label)
            }
            match?.let { row.productId to it.priceKrw.toDouble() }
        }.toMap()
    val options = recognized.map { option ->
        val bottle = isBottle(option.extractedOptionLabel)
        ReviewOption(
            volume = if (bottle) 0.0
                else (option.extractedPourMl
                    ?: defaultPour.takeIf { !other || isGlass(option.extractedOptionLabel) })
                    ?.toDouble() ?: Double.NaN,
            price = (option.extractedPriceKrw ?: 0).toDouble(),
            bottle = bottle,
            sourceOptionId = option.extractedOptionId,
            label = option.extractedOptionLabel,
            volumeFromDefault = option.extractedPourMl == null && !bottle &&
                (!other || isGlass(option.extractedOptionLabel)),
        )
    }
    val first = options.firstOrNull()
    val firstServerOption = recognized.firstOrNull()
    val oldPrice = linkedId?.let(existingPrices::get)
    val photoPrice = firstServerOption?.extractedPriceKrw?.toDouble()
    // Raw OCR text is evidence, not a publishable menu name: it can contain
    // price/volume tokens. A missing name must remain blank until Owner input.
    val displayName = dto.extractedProductName?.trim()?.ifBlank { null }
        ?: dto.newProductDraft?.displayName?.trim()?.ifBlank { null }
        ?: ""
    return ReviewItem(
        id = dto.extractedItemId,
        name = displayName,
        type = if (other) ReviewItemType.OTHER else ReviewItemType.WHISKY,
        match = match,
        matchConfirmed = linkedId != null,
        newConfirmed = linkedId != null || other,
        linkedProductId = linkedId,
        linkedProductName = selectedCandidate?.displayName.takeIf { linkedId != null },
        newProductName = dto.newProductDraft?.displayName ?: displayName,
        price = first?.price ?: 0.0,
        volume = first?.volume ?: defaultPour.toDouble(),
        bottle = first?.bottle ?: false,
        volumeSource = if (first?.volumeFromDefault == true)
            VolumeSource.DEFAULT else VolumeSource.PHOTO,
        primaryHasOption = first != null,
        primarySourceOptionId = first?.sourceOptionId,
        primaryOptionLabel = first?.label,
        existingPriceByProductId = existingPrices,
        options = options.drop(1),
        oldPrice = oldPrice,
        photoPrice = photoPrice,
        priceChoice = if (oldPrice != null && photoPrice != null &&
            oldPrice != photoPrice) PriceChoice.NONE else PriceChoice.PHOTO,
        nameSaved = displayName.isNotBlank() && (linkedId != null || other || nonProduct),
        excluded = nonProduct,
        raw = dto.rawText,
        photoIndex = photoOrder,
        hasSourceBox = dto.sourceBox?.size == 4,
        required = !nonProduct,
        recognizedName = displayName,
        sourcePhotoUrl = photoUrl,
        sourceBox = dto.sourceBox,
        recognizedOffers = recognized.map {
            RecognizedOffer(volumeMl = it.extractedPourMl,
                bottle = isBottle(it.extractedOptionLabel),
                priceKrw = it.extractedPriceKrw)
        },
        candidates = dto.candidates.sortedBy { it.candidateRank }
            .map { CatalogProduct(it.productId, it.displayName) },
    )
}

/**
 * Convert an owner-confirmed v20 card to an existing Stage-8 decision.
 * The existing production adapter owns the single 8.1 transaction,
 * add-only policy, discount preservation, and post-publish warnings.
 */
internal fun mapConfirmedReviewDecision(
    card: ReviewItem, extracted: ReviewItemDto, defaultPour: Double,
    existingBrands: Map<String, String>,
): MockReviewDecision {
    if (card.excluded) return MockReviewDecision(MockDecisionKind.EXCLUDE)
    require(card.name.trim().length in 1..200) {
        "메뉴 이름은 1~200자로 입력해 주세요."
    }
    val raw = extracted.options.sortedBy { it.optionOrder }
    // Both whisky and other preserve every reviewer-edited OCR option, not
    // a hidden, uneditable reconstruction from the initial server response.
    val choices = PhotoReviewRules.optionSummary(card)
    require(choices.isNotEmpty() && choices.all {
        validPrice(it.price) &&
            (it.bottle || (card.type == ReviewItemType.OTHER || validVolume(it.volume)))
    }) { "${card.name}: 가격과 용량을 확인해 주세요." }
    require(choices.size <= PhotoReviewRules.MAX_OPTIONS) {
        "${card.name}: 검수 옵션 개수를 확인해 주세요."
    }
    val byId = raw.associateBy { it.extractedOptionId }
    require(choices.mapNotNull { it.sourceOptionId }.distinct().size ==
        choices.count { it.sourceOptionId != null }) {
        "${card.name}: 중복된 OCR 옵션을 선택할 수 없어요."
    }
    require(choices.all { choice ->
        choice.sourceOptionId == null || choice.sourceOptionId in byId
    }) { "${card.name}: 검수 옵션이 서버와 일치하지 않아요." }
    // A manually added option has no OCR ID. The final options[] request
    // sends null extractedOptionId, not a fabricated server identity.
    val retainedIds = choices.mapNotNull { it.sourceOptionId }.toSet()
    val excludedOptionIds = raw.map { it.extractedOptionId }
        .filterNot { it in retainedIds }
    val mapped = choices.mapIndexed { index, chosen ->
        // An owner-added option must never borrow a different OCR option ID.
        val source = chosen.sourceOptionId?.let(byId::get)
        // Preserve original Korean OCR labels (including "병"). A reviewer
        // switching an OCR glass to bottle explicitly changes it to "Bottle";
        // switching an OCR bottle back to glass clears its bottle-only label.
        val originalLabel = source?.extractedOptionLabel
        val bottle = chosen.bottle ||
            (card.type == ReviewItemType.OTHER && isBottle(originalLabel))
        val label = when {
            bottle -> originalLabel?.takeIf(::isBottle) ?: "Bottle"
            isBottle(originalLabel) -> null
            else -> chosen.label ?: originalLabel
        }
        MockMenuOption(
            optionId = source?.extractedOptionId ?: "manual-${card.id}-$index",
            label = label,
            pourMl = when {
                bottle -> null
                card.type == ReviewItemType.WHISKY -> chosen.volume.toInt()
                source?.extractedPourMl != null -> source.extractedPourMl
                isGlass(label) -> chosen.volume.takeIf(::validVolume)?.toInt()
                else -> null
            },
            priceKrw = chosen.price.toInt(),
        )
    }
    val override = card.name.trim().takeIf {
        it.isNotEmpty() && it != extracted.extractedProductName
    }
    if (card.linkedProductId != null) {
        return MockReviewDecision(
            MockDecisionKind.SELECT_PRODUCT,
            productId = card.linkedProductId,
            correctedOptions = mapped,
            displayNameOverride = override,
            excludedOptionIds = excludedOptionIds,
        )
    }
    // A non-whisky item is published to this bar only: neither a product
    // confirmation nor a catalog search/brand is required by §8.1.
    require(card.type == ReviewItemType.OTHER || (card.newConfirmed && card.nameSaved)) {
        "${card.name}: 신규 위스키 이름을 확인해 주세요."
    }
    val sourceDraft = extracted.newProductDraft
    val brandText = (extracted.extractedBrandName
        ?: sourceDraft?.brandText)?.trim().orEmpty()
    // PR #164 publishes new lines on the bar without any catalog product.
    // Brand metadata is optional and never sent to the server for owner adds.
    val category = if (card.type == ReviewItemType.WHISKY) "whisky" else "other"
    val brandId = existingBrands[brandText.lowercase()]
    // The owner-confirmed on-screen name is authoritative. newProductName
    // can be a stale OCR draft after editing the detail name.
    val finalName = card.name.trim()
    require(finalName.isNotBlank()) { "게시할 메뉴 이름을 입력해 주세요." }
    return MockReviewDecision(
        MockDecisionKind.CREATE_PRODUCT,
        correctedOptions = mapped,
        displayNameOverride = override,
        excludedOptionIds = excludedOptionIds,
        newProduct = MockNewProductDraft(
            name = finalName,
            brandId = brandId,
            brandName = brandText.takeIf { brandId == null && it.isNotBlank() },
            category = category,
            ageYears = sourceDraft?.ageYears,
            editionName = sourceDraft?.editionName,
            abvPercent = sourceDraft?.abv,
        ),
    )
}
