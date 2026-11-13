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

private fun mapServerReviewItem(
    dto: ReviewItemDto, photoOrder: Int, photoUrl: String, bar: MockBar,
    snapshot: MockOwnerSnapshot, defaultPour: Int,
): ReviewItem {
    val recognized = dto.options.sortedBy { it.optionOrder }
    // Keep ALL OCR options visible for owner review, including 4+.
    // PhotoReviewRules.problems() prevents publication until at most 3 remain.
    val selectedCandidate = dto.candidates.firstOrNull {
        it.productId == dto.proposedProductId
    }
    val category = selectedCandidate?.category ?: dto.newProductDraft?.category ?: "whisky"
    val nonProduct = dto.effectiveLineType !in setOf("product", "unknown")
    val other = nonProduct || !category.equals("whisky", ignoreCase = true)
    val match = when {
        dto.initialResolutionStatus == "exact_match" && dto.proposedProductId != null ->
            ReviewMatch.EXACT
        dto.candidates.size > 1 -> ReviewMatch.CANDIDATE
        dto.candidates.size == 1 -> ReviewMatch.AMBIGUOUS
        else -> ReviewMatch.NEW
    }
    val linkedId = dto.proposedProductId.takeIf {
        match == ReviewMatch.EXACT && !nonProduct
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
                else (option.extractedPourMl ?: defaultPour).toDouble(),
            price = (option.extractedPriceKrw ?: 0).toDouble(),
            bottle = bottle,
            sourceOptionId = option.extractedOptionId,
        )
    }
    val first = options.firstOrNull()
    val firstServerOption = recognized.firstOrNull()
    val oldPrice = linkedId?.let(existingPrices::get)
    val photoPrice = firstServerOption?.extractedPriceKrw?.toDouble()
    val displayName = dto.extractedProductName?.trim()?.ifBlank { null }
        ?: dto.newProductDraft?.displayName?.trim()?.ifBlank { null }
        ?: dto.rawText.trim().take(200)
    return ReviewItem(
        id = dto.extractedItemId,
        name = displayName,
        type = if (other) ReviewItemType.OTHER else ReviewItemType.WHISKY,
        match = match,
        matchConfirmed = linkedId != null,
        newConfirmed = linkedId != null,
        linkedProductId = linkedId,
        linkedProductName = selectedCandidate?.displayName.takeIf { linkedId != null },
        newProductName = dto.newProductDraft?.displayName ?: displayName,
        price = first?.price ?: 0.0,
        volume = first?.volume ?: defaultPour.toDouble(),
        bottle = first?.bottle ?: false,
        volumeSource = if (firstServerOption?.extractedPourMl == null)
            VolumeSource.DEFAULT else VolumeSource.PHOTO,
        primaryHasOption = first != null,
        primarySourceOptionId = first?.sourceOptionId,
        existingPriceByProductId = existingPrices,
        options = if (other) emptyList() else options.drop(1),
        oldPrice = oldPrice,
        photoPrice = photoPrice,
        priceChoice = if (oldPrice != null && photoPrice != null &&
            oldPrice != photoPrice) PriceChoice.NONE else PriceChoice.PHOTO,
        nameSaved = linkedId != null || nonProduct,
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
    val raw = extracted.options.sortedBy { it.optionOrder }
    val choices = if (card.type == ReviewItemType.OTHER) {
        listOf(ReviewOption(price = card.price,
            sourceOptionId = raw.firstOrNull()?.extractedOptionId))
    } else PhotoReviewRules.optionSummary(card)
    require(choices.isNotEmpty() && choices.all {
        validPrice(it.price) &&
            (it.bottle || (card.type == ReviewItemType.OTHER || validVolume(it.volume)))
    }) { "${card.name}: 가격과 용량을 확인해 주세요." }
    require(choices.size <= PhotoReviewRules.MAX_OPTIONS) {
        "${card.name}: 용량 옵션은 최대 3개입니다. 불필요한 옵션을 제거해 주세요."
    }
    val byId = raw.associateBy { it.extractedOptionId }
    require(choices.mapNotNull { it.sourceOptionId }.distinct().size ==
        choices.count { it.sourceOptionId != null }) {
        "${card.name}: 중복된 OCR 옵션을 선택할 수 없어요."
    }
    require(choices.all { choice ->
        choice.sourceOptionId == null || choice.sourceOptionId in byId
    }) { "${card.name}: 검수 옵션이 서버와 일치하지 않아요." }
    // A manually added option has no OCR ID. The agreed API field
    // addedOptions publishes it without inventing an extractedOptionId.
    val retainedIds = choices.mapNotNull { it.sourceOptionId }.toSet()
    val excludedOptionIds = raw.map { it.extractedOptionId }
        .filterNot { it in retainedIds }
    val mapped = choices.mapIndexed { index, chosen ->
        // An owner-added option must never borrow a different OCR option ID.
        val source = chosen.sourceOptionId?.let(byId::get)
        val bottle = card.type == ReviewItemType.WHISKY && chosen.bottle
        val label = if (bottle) "Bottle" else source?.extractedOptionLabel
        require(source?.extractedOptionLabel == null || label != null) {
            "${card.name}: 기존 옵션 이름은 삭제할 수 없어요."
        }
        MockMenuOption(
            optionId = source?.extractedOptionId ?: "manual-${card.id}-$index",
            label = label,
            pourMl = if (bottle) null else if (card.type == ReviewItemType.OTHER)
                source?.extractedPourMl
            else chosen.volume.toInt(),
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
    require(card.newConfirmed && card.nameSaved) {
        "${card.name}: 신규 상품 정보를 확인해 주세요."
    }
    val sourceDraft = extracted.newProductDraft
    val brandText = (extracted.extractedBrandName
        ?: sourceDraft?.brandText)?.trim().orEmpty()
    require(brandText.isNotBlank()) {
        "${card.name}: 브랜드 정보가 없어 자동 등록할 수 없어요."
    }
    val category = sourceDraft?.category?.takeIf { it.isNotBlank() }
        ?: if (card.type == ReviewItemType.WHISKY) "whisky" else
            error("${card.name}: 상품 분류를 확인해 주세요.")
    val brandId = existingBrands[brandText.lowercase()]
    return MockReviewDecision(
        MockDecisionKind.CREATE_PRODUCT,
        correctedOptions = mapped,
        displayNameOverride = override,
        excludedOptionIds = excludedOptionIds,
        newProduct = MockNewProductDraft(
            name = card.newProductName?.trim()?.ifBlank { null } ?: card.name.trim(),
            brandId = brandId,
            brandName = if (brandId == null) brandText else null,
            category = category,
            ageYears = sourceDraft?.ageYears,
            editionName = sourceDraft?.editionName,
            abvPercent = sourceDraft?.abv,
        ),
    )
}
