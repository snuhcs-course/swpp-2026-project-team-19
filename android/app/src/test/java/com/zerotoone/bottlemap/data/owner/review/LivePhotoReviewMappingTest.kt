package com.zerotoone.bottlemap.data.owner.review

import com.zerotoone.bottlemap.data.owner.MockBar
import com.zerotoone.bottlemap.data.owner.MockBarMenuItem
import com.zerotoone.bottlemap.data.owner.MockMenuOption
import com.zerotoone.bottlemap.data.owner.MockOwnerSnapshot
import com.zerotoone.bottlemap.data.owner.MockDecisionKind
import com.zerotoone.bottlemap.network.MenuImportStatusDto
import com.zerotoone.bottlemap.network.NewProductDraftDto
import com.zerotoone.bottlemap.network.ReviewCandidateDto
import com.zerotoone.bottlemap.network.ReviewImageDto
import com.zerotoone.bottlemap.network.ReviewItemDto
import com.zerotoone.bottlemap.network.ReviewOptionDto
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewRules
import com.zerotoone.bottlemap.ui.owner.review.PriceChoice
import com.zerotoone.bottlemap.ui.owner.review.ReviewMatch
import org.junit.Assert.*
import org.junit.Test

class LivePhotoReviewMappingTest {
    private fun fixture() = MockOwnerSnapshot(
        bars = listOf(MockBar("bar-1","Whisky Bar","서울",
            defaultPourMl=30)),
        menuItems = listOf(MockBarMenuItem("row-1","bar-1","product-1",
            listOf(MockMenuOption("saved-30",pourMl=30,priceKrw=12000)))),
        selectedBarId="bar-1",
    )
    private fun option(id: String, ml: Int?, price: Int?) =
        ReviewOptionDto(id, optionOrder=1, extractedPourMl=ml,extractedPriceKrw=price)
    private fun item(
        options: List<ReviewOptionDto> = listOf(option("opt-1",30,15000)),
        status: String = "exact_match",
        proposedId: String? = "product-1",
        lineType: String = "product",
    ) = ReviewItemDto(
        extractedItemId="line-1",itemOrder=1,rawText="위스키 30ml 15,000",
        extractedLineType=lineType,effectiveLineType=lineType,
        extractedProductName="위스키 12년",extractedBrandName="Brand",
        initialResolutionStatus=status,proposedProductId=proposedId,
        options=options,candidates=listOf(ReviewCandidateDto(
            productId="product-1",candidateRank=1,displayName="Whisky 12",
            brandId="brand-1",brandName="Brand",category="whisky",
            matchMethod="alias",score=1.0,
        )),
        newProductDraft=NewProductDraftDto(brandText="Brand",
            category="whisky",displayName="위스키 12년"),
    )
    private fun response(vararg items: ReviewItemDto) = MenuImportStatusDto(
        menuImportId="import-1",barId="bar-1",status="ready_for_review",
        reviewVersion=3,images=listOf(ReviewImageDto(
            imageId="photo-1",imageOrder=1,imageUrl="https://signed.example/photo",
            items=items.toList(),
        )),
    )

    @Test fun mapsRealExtractedIdsAndExistingPriceConflictWithoutDemoProducts() {
        val dto=item()
        val state=mapServerPhotoReview(response(dto),fixture())
        assertEquals(1,state.items.size)
        val card=state.items.single()
        assertEquals(dto.extractedItemId,card.id)
        assertEquals("product-1",card.linkedProductId)
        assertEquals(ReviewMatch.EXACT,card.match)
        assertEquals(PriceChoice.NONE,card.priceChoice)
        assertEquals(12000.0,card.oldPrice!!,0.0)
        assertEquals(15000.0,card.photoPrice!!,0.0)
        assertEquals(1,PhotoReviewRules.stats(state).pending.size)
        assertEquals(30.0,card.volume,0.0)
        assertEquals(30.0,state.defaultPour,0.0)
    }

    @Test fun firstOcrOptionIdentitySurvivesReviewAndCanPublishWithoutFalseNewOptionError() {
        val dto = item()
        val card = mapServerPhotoReview(response(dto), fixture()).items.single()
        assertEquals("opt-1", PhotoReviewRules.optionSummary(card).single().sourceOptionId)
        val confirmed = card.copy(priceChoice = PriceChoice.PHOTO)
        val decision = mapConfirmedReviewDecision(confirmed, dto, 30.0, emptyMap())
        assertEquals(listOf("opt-1"), decision.correctedOptions!!.map { it.optionId })
    }

    @Test fun linkingAmbiguousCatalogProductPromptsForExistingBarPriceDifference() {
        val dto = item(status = "ambiguous", proposedId = null)
        val card = mapServerPhotoReview(response(dto), fixture()).items.single()
        assertNull(card.oldPrice)
        val linked = PhotoReviewRules.markLinked(
            card, com.zerotoone.bottlemap.ui.owner.review.CatalogProduct("product-1", "Whisky 12")
        )
        assertEquals(PriceChoice.NONE, linked.priceChoice)
        assertEquals(12000.0, linked.oldPrice!!, 0.0)
        assertTrue(
            com.zerotoone.bottlemap.ui.owner.review.ReviewIssue.PRICE_CHOICE in
                PhotoReviewRules.problems(linked)
        )
    }

    @Test fun publicationUsesCorrectOptionIdAndSelectedPriceWithoutFakeFields() {
        val dto=item()
        val card=mapServerPhotoReview(response(dto),fixture()).items.single()
            .copy(price=12000.0,priceChoice=PriceChoice.OLD,
                name="표시 이름 수정")
        val decision=mapConfirmedReviewDecision(card,dto,30.0,
            mapOf("brand" to "brand-1"))
        assertEquals(MockDecisionKind.SELECT_PRODUCT,decision.kind)
        assertEquals("product-1",decision.productId)
        assertEquals("표시 이름 수정",decision.displayNameOverride)
        assertEquals("opt-1",decision.correctedOptions!!.single().optionId)
        assertEquals(12000,decision.correctedOptions!!.single().priceKrw)
    }

    @Test fun largeOptionSetShowsAllAndBlocksPublishUntilThreeRemain() {
        val options=(1..4).map { option("opt-$it",it*15,10000+it*1000)
            .copy(optionOrder=it) }
        val dto = item(options=options)
        val review = mapServerPhotoReview(response(dto),fixture())
        val card = review.items.single()
        assertEquals(4,PhotoReviewRules.countOptions(card))
        assertFalse(PhotoReviewRules.stats(review).canPublish)
        assertTrue(com.zerotoone.bottlemap.ui.owner.review.ReviewIssue.OPTION in
            PhotoReviewRules.problems(card))
        val trimmed = PhotoReviewRules.removeOption(card,0)
        assertEquals(3,PhotoReviewRules.countOptions(trimmed))
        val decision = mapConfirmedReviewDecision(
            trimmed.copy(priceChoice=PriceChoice.PHOTO),dto,30.0,emptyMap())
        assertEquals(listOf("opt-2"),decision.excludedOptionIds)
        assertEquals(listOf("opt-1","opt-3","opt-4"),
            decision.correctedOptions!!.map { it.optionId })
    }

    @Test fun replacingOcrServingWithManualOneKeepsExclusionAndNewIdentity() {
        val dto = item(options = listOf(
            option("opt-1", 30, 15000),
            option("opt-2", 45, 22000).copy(optionOrder = 2),
        ))
        val original = mapServerPhotoReview(response(dto), fixture()).items.single()
        val updated = PhotoReviewRules.removeOption(original, 0).copy(
            options = listOf(
                com.zerotoone.bottlemap.ui.owner.review.ReviewOption(60.0, 27000.0)
            ), priceChoice = PriceChoice.PHOTO,
        )
        val decision = mapConfirmedReviewDecision(updated, dto, 30.0, emptyMap())
        assertEquals(listOf("opt-2"), decision.excludedOptionIds)
        assertEquals("opt-1", decision.correctedOptions!![0].optionId)
        assertTrue(decision.correctedOptions!![1].optionId.startsWith("manual-"))
        assertEquals(60, decision.correctedOptions!![1].pourMl)
    }

    @Test fun missingPourUsesConfiguredBarDefaultInEveryOption() {
        val options=listOf(option("opt-a",null,18000),
            option("opt-b",null,22000).copy(optionOrder=2))
        val card=mapServerPhotoReview(response(item(options=options)),fixture()).items.single()
        assertEquals(30.0,card.volume,0.0)
        assertEquals(30.0,card.options.single().volume,0.0)
        assertEquals("30",PhotoReviewRules.optionFieldText(card,
            PhotoReviewRules.OptionField.VOLUME,null))
        assertEquals("30",PhotoReviewRules.optionFieldText(card,
            PhotoReviewRules.OptionField.VOLUME,0))
    }

    @Test fun newProductRequiresBrandAndHonorsConfirmedProductFields() {
        val dto=item(status="unmatched",proposedId=null)
        val card=mapServerPhotoReview(response(dto),fixture()).items.single()
            .copy(newConfirmed=true,nameSaved=true,name="위스키 새 상품",
                newProductName="위스키 새 상품")
        val decision=mapConfirmedReviewDecision(card,dto,30.0,
            mapOf("brand" to "brand-1"))
        assertEquals(MockDecisionKind.CREATE_PRODUCT,decision.kind)
        assertEquals("brand-1",decision.newProduct?.brandId)
        assertEquals("위스키 새 상품",decision.newProduct?.name)
        val missing=dto.copy(extractedBrandName=null,
            newProductDraft=dto.newProductDraft?.copy(brandText=null))
        try {
            mapConfirmedReviewDecision(card,missing,30.0,emptyMap())
            fail("Must not invent a missing catalog brand")
        } catch (_: IllegalArgumentException) { }
    }

    @Test fun ownerAddedOptionHasNoExtractedIdAndIsSentSeparately() {
        val dto = item()
        val card = mapServerPhotoReview(response(dto), fixture()).items.single()
            .copy(options = listOf(
                com.zerotoone.bottlemap.ui.owner.review.ReviewOption(60.0, 22000.0)
            ), priceChoice = PriceChoice.PHOTO)
        val decision = mapConfirmedReviewDecision(card, dto, 30.0, emptyMap())
        assertEquals("opt-1", decision.correctedOptions!![0].optionId)
        assertTrue(decision.correctedOptions!![1].optionId.startsWith("manual-"))
        assertEquals(2, decision.correctedOptions!!.size)
    }

    @Test fun excludedLineMapsToRejectWithoutProductWrites() {
        val dto=item(status="unmatched",proposedId=null).copy(
            extractedLineType="description",effectiveLineType="description")
        val card=mapServerPhotoReview(response(dto),fixture()).items.single()
        assertTrue(card.excluded)
        val decision=mapConfirmedReviewDecision(card,dto,30.0,emptyMap())
        assertEquals(MockDecisionKind.EXCLUDE,decision.kind)
    }

    @Test fun staleOrIncompleteStatusCannotMasqueradeAsReadyReview() {
        val dto=response(item()).copy(status="processing")
        try {
            mapServerPhotoReview(dto,fixture())
            fail("Must reject incomplete OCR status")
        } catch (_: IllegalArgumentException) { }
    }
}
