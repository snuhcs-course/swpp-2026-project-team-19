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
        assertEquals(PriceChoice.PHOTO,card.priceChoice)
        assertNull(card.oldPrice)
        assertEquals(listOf(12000,15000),
            card.priceCandidates.map { it.priceKrw }.sorted())
        assertEquals(1,PhotoReviewRules.stats(state).pending.size)
        assertEquals(30.0,card.volume,0.0)
        assertEquals(30.0,state.defaultPour,0.0)
    }

    @Test fun sameSizeDifferentLabelMatchesExistingWhiskyPriceByMl() {
        val saved=fixture().copy(menuItems=listOf(MockBarMenuItem(
            "row-1","bar-1","product-1",
            listOf(MockMenuOption("old-30",label="잔",pourMl=30,priceKrw=12000)))))
        val shot=item(options=listOf(ReviewOptionDto(
            "ocr-shot",1,"샷",30,15000)))
        val otherServing=mapServerPhotoReview(response(shot),saved).items.single()
        assertEquals(listOf(12000,15000),
            otherServing.priceCandidates.map { it.priceKrw }.sorted())
        assertEquals(1,com.zerotoone.bottlemap.ui.owner.review.PhotoReviewRules.pendingPriceServings(otherServing).size)
        val glass=shot.copy(options=listOf(ReviewOptionDto(
            "ocr-glass",1,"잔",30,15000)))
        val sameServing=mapServerPhotoReview(response(glass),saved).items.single()
        assertEquals(listOf(12000,15000),
            sameServing.priceCandidates.map { it.priceKrw }.sorted())
    }

    @Test fun koreanAndEnglishBottleShareExistingBarPrice() {
        val saved=fixture().copy(menuItems=listOf(MockBarMenuItem(
            "row-1","bar-1","product-1",
            listOf(MockMenuOption("saved-bottle",label="Bottle",priceKrw=120000)))))
        val korean=item(options=listOf(ReviewOptionDto(
            "ocr-korean-bottle",1,"병",null,150000)))
        val normalized=mapServerPhotoReview(response(korean),saved).items.single()
        assertEquals(listOf(120000,150000),
            normalized.priceCandidates.map { it.priceKrw }.sorted())
        val english=korean.copy(options=listOf(ReviewOptionDto(
            "ocr-english-bottle",1,"Bottle",null,150000)))
        val matched=mapServerPhotoReview(response(english),saved).items.single()
        assertEquals(listOf(120000,150000),
            matched.priceCandidates.map { it.priceKrw }.sorted())
    }

    @Test fun sameWhiskyOcrLinesBecomeOneCardWithOne30mlChoice() {
        val a=item(options=listOf(
            ReviewOptionDto("ocr-glass-30",1,"잔",30,12000),
            ReviewOptionDto("ocr-60",2,"잔",60,22000),
            ReviewOptionDto("ocr-bottle",3,"병",null,130000)))
        val b=item(options=listOf(
            ReviewOptionDto("ocr-shot-30",1,"샷",30,15000)))
            .copy(extractedItemId="line-2",itemOrder=2,rawText="Whisky 샷 30ml 15,000")
        val state=mapServerPhotoReview(response(a,b),fixture())
        assertEquals(2,state.items.size)
        assertEquals(1,PhotoReviewRules.stats(state).pending.size)
        assertEquals(0,PhotoReviewRules.stats(state).excluded.size)
        val master=state.items.first()
        assertEquals("line-1",state.items[1].mergedInto)
        assertEquals(3,PhotoReviewRules.countOptions(master))
        assertEquals(listOf(12000,12000,15000),
            master.priceCandidates.filter { it.servingKey=="ml:30" }
                .map { it.priceKrw }.sorted())
        assertEquals(setOf("ml:30"),PhotoReviewRules.pendingPriceServings(master))
        assertTrue(master.options.any { it.bottle })
        assertTrue(master.options.any { it.volume == 60.0 })
        val chosen=PhotoReviewRules.chooseServingPrice(master,"ml:30",15000)
        assertTrue(PhotoReviewRules.pendingPriceServings(chosen).isEmpty())
        assertEquals(15000.0,chosen.price,0.0)
        val parent=mapConfirmedReviewDecision(chosen,a,30.0,emptyMap())
        assertEquals(3,parent.correctedOptions!!.size)
        assertEquals(listOf("ocr-glass-30","ocr-60","ocr-bottle"),
            parent.correctedOptions!!.map { it.optionId })
        val child=mapConfirmedReviewDecision(state.items[1],b,30.0,emptyMap())
        assertEquals(MockDecisionKind.EXCLUDE,child.kind)
    }

    @Test fun newServingFromAnotherOcrLineNeverUsesForeignExtractedOptionId() {
        val parent=item(options=listOf(
            ReviewOptionDto("ocr-main",1,"잔",30,15000)))
        val second=item(options=listOf(
            ReviewOptionDto("ocr-child",1,"잔",60,26000)))
            .copy(extractedItemId="line-child",itemOrder=2)
        val state=mapServerPhotoReview(response(parent,second),fixture())
        val review=state.items.first()
        assertEquals(2,PhotoReviewRules.countOptions(review))
        val decision=mapConfirmedReviewDecision(review,parent,30.0,emptyMap())
        assertEquals(listOf("ocr-main",null),
            decision.correctedOptions!!.map {
                it.optionId.takeIf { id -> id=="ocr-main" }
            })
        assertTrue(decision.correctedOptions!![1].optionId.startsWith("manual-"))
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
        assertEquals(PriceChoice.PHOTO, linked.priceChoice)
        assertEquals(12000.0, linked.oldPrice!!, 0.0)
        assertEquals(setOf("ml:30"),PhotoReviewRules.pendingPriceServings(linked))
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

    @Test fun fourWhiskySizesRequireExplicitSelectionOfUpToThree() {
        val options=(1..4).map { option("opt-$it",it*15,10000+it*1000)
            .copy(optionOrder=it) }
        val dto = item(options=options)
        val review = mapServerPhotoReview(response(dto),fixture())
        val card = review.items.single()
        assertFalse(card.volumeChoicesConfirmed)
        assertEquals(4,card.volumeChoices.size)
        val selected=card.copy(chosenVolumeKeys=card.volumeChoices.take(3)
            .map(PhotoReviewRules::servingKey).toSet())
        val confirmed = PhotoReviewRules.confirmVolumeChoices(selected)
        assertEquals(3,PhotoReviewRules.countOptions(confirmed))
        assertTrue(PhotoReviewRules.problems(confirmed).isEmpty())
        val decision = mapConfirmedReviewDecision(confirmed,dto,30.0,emptyMap())
        assertEquals(listOf("opt-1","opt-2","opt-3"),
            decision.correctedOptions!!.map { it.optionId })
        assertEquals(listOf("opt-4"),decision.excludedOptionIds)
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
        // Two OCR prices without ml both inherit 30ml: the same serving
        // is ONE option with a required price choice, not two 30ml rows.
        assertTrue(card.options.isEmpty())
        assertEquals(2, card.priceCandidates.size)
        assertEquals(setOf(18000,22000),card.priceCandidates.map { it.priceKrw }.toSet())
        assertEquals(1,PhotoReviewRules.pendingPriceServings(card).size)
        assertEquals("30",PhotoReviewRules.optionFieldText(card,
            PhotoReviewRules.OptionField.VOLUME,null))
    }

    @Test fun newWhiskyIsPublishedUnlinkedEvenWhenBrandIsMissing() {
        val dto=item(status="unmatched",proposedId=null)
        val card=mapServerPhotoReview(response(dto),fixture()).items.single()
            .copy(newConfirmed=true,nameSaved=true,name="위스키 새 상품",
                newProductName="위스키 새 상품")
        val decision=mapConfirmedReviewDecision(card,dto,30.0,
            mapOf("brand" to "brand-1"))
        assertEquals(MockDecisionKind.CREATE_PRODUCT,decision.kind)
        assertEquals("brand-1",decision.newProduct?.brandId)
        assertEquals("위스키 새 상품",decision.newProduct?.name)
        // The owner never creates a catalog brand or product; brand is optional.
        val missing=dto.copy(extractedBrandName=null,
            newProductDraft=dto.newProductDraft?.copy(brandText=null))
        val unlinked=mapConfirmedReviewDecision(card,missing,30.0,emptyMap())
        assertEquals("whisky",unlinked.newProduct?.category)
        assertNull(unlinked.newProduct?.brandId)
        assertNull(unlinked.newProduct?.brandName)
    }

    @Test fun ownerEditedOtherNameOverridesStaleNewProductDraft() {
        val dto=item(status="unmatched",proposedId=null)
            .copy(extractedKind="other",candidates=emptyList(),newProductDraft=null)
        val original=mapServerPhotoReview(response(dto),fixture()).items.single()
        val ownerEdited=original.copy(name="사장님이 수정한 맥주 이름",
            newProductName="OCR 이전 이름",nameSaved=true)
        val decision=mapConfirmedReviewDecision(ownerEdited,dto,30.0,emptyMap())
        assertEquals("사장님이 수정한 맥주 이름",decision.displayNameOverride)
        assertEquals("사장님이 수정한 맥주 이름",decision.newProduct?.name)
    }

    @Test fun unnamedNonWhiskyMustReceiveOwnerNameInsteadOfRawOcrPriceLine() {
        val dto=item(options=listOf(ReviewOptionDto("cola-1",1,null,null,5000)),
            status="unmatched",proposedId=null)
            .copy(extractedKind="other",candidates=emptyList(),
                extractedProductName=null,newProductDraft=null,
                rawText="콜라 5,000원")
        val review=mapServerPhotoReview(response(dto),fixture())
        val card=review.items.single()
        assertEquals("",card.name)
        assertEquals("콜라 5,000원",card.raw)
        assertFalse(card.nameSaved)
        assertTrue(com.zerotoone.bottlemap.ui.owner.review.ReviewIssue.NAME in
            PhotoReviewRules.problems(card))
        assertFalse(PhotoReviewRules.stats(review).canPublish)
        val named=card.copy(name="콜라",nameSaved=true)
        assertTrue(PhotoReviewRules.problems(named).isEmpty())
        val decision=mapConfirmedReviewDecision(named,dto,30.0,emptyMap())
        assertEquals("콜라",decision.newProduct?.name)
        assertEquals("콜라",decision.displayNameOverride)
    }

    @Test fun nonWhiskyOcrMenuCanPublishWithoutCatalogConfirmationOrBrand() {
        val dto=item(
            options=listOf(ReviewOptionDto("beer-1",1,"잔",null,8000)),
            status="unmatched",proposedId=null,
        ).copy(extractedProductName="맥주 1",extractedBrandName=null,
            extractedKind="other",candidates=emptyList(),newProductDraft=null)
        val card=mapServerPhotoReview(response(dto),fixture()).items.single()
        assertEquals(com.zerotoone.bottlemap.ui.owner.review.ReviewItemType.OTHER,card.type)
        assertNull(card.linkedProductId)
        assertFalse(card.excluded)
        assertTrue(PhotoReviewRules.stats(
            mapServerPhotoReview(response(dto),fixture())).canPublish)
        val decision=mapConfirmedReviewDecision(card,dto,30.0,emptyMap())
        assertEquals(MockDecisionKind.CREATE_PRODUCT,decision.kind)
        assertEquals("other",decision.newProduct?.category)
        assertEquals("맥주 1",decision.newProduct?.name)
        assertEquals(1,decision.correctedOptions!!.size)
        assertEquals("beer-1",decision.correctedOptions!!.single().optionId)
        // "잔" with a missing OCR pour inherits the displayed bar default.
        assertEquals(30,decision.correctedOptions!!.single().pourMl)
        assertEquals("잔",decision.correctedOptions!!.single().label)
        assertEquals(8000,decision.correctedOptions!!.single().priceKrw)
    }

    @Test fun koreanBottleIsPublishedAsBottleWithoutLosingOcrIdentity() {
        val dto=item(options=listOf(ReviewOptionDto("ocr-bottle",1,"병",null,88000)),
            status="unmatched",proposedId=null)
        val card=mapServerPhotoReview(response(dto),fixture()).items.single()
            .copy(newConfirmed=true,nameSaved=true)
        val mapped=mapConfirmedReviewDecision(card,dto,30.0,emptyMap())
        val option=requireNotNull(mapped.correctedOptions).single()
        assertEquals("Bottle",option.label)
        assertNull(option.pourMl)
        assertEquals("ocr-bottle",option.optionId)
    }

    @Test fun unknownOtherLabelCanSavePriceWithoutInventingPour() {
        val dto=item(options=listOf(ReviewOptionDto("ocr-other",1,null,null,1500)),
            status="unmatched",proposedId=null)
            .copy(extractedKind="other",candidates=emptyList(),newProductDraft=null)
        val card=mapServerPhotoReview(response(dto),fixture()).items.single()
        assertTrue(card.volume.isNaN())
        val option=requireNotNull(mapConfirmedReviewDecision(card,dto,30.0,emptyMap())
            .correctedOptions).single()
        assertNull(option.label)
        assertNull(option.pourMl)
    }

    @Test fun overlongNameIsRejectedRatherThanTruncatedOrPublished() {
        val dto=item(status="unmatched",proposedId=null)
        val longName="가".repeat(201)
        val card=mapServerPhotoReview(response(dto),fixture()).items.single()
            .copy(name=longName,nameSaved=true,newConfirmed=true)
        assertTrue(com.zerotoone.bottlemap.ui.owner.review.ReviewIssue.NAME in
            PhotoReviewRules.problems(card))
        try {
            mapConfirmedReviewDecision(card,dto,30.0,emptyMap())
            fail("overlong name must not be sent to the server")
        } catch (_: IllegalArgumentException) { }
    }

    @Test fun statusRecoveryOnlyAcceptsAppliedStatusForTheSameImport() {
        val applied=response(item()).copy(status="applied")
        assertTrue(isAppliedReviewImport(applied,"import-1"))
        assertFalse(isAppliedReviewImport(applied,"other-import"))
        assertFalse(isAppliedReviewImport(applied.copy(status="ready_for_review"),"import-1"))
    }

    @Test fun nonWhiskyOcrMultiplePricesArePreservedInsteadOfTruncated() {
        val options=(1..4).map {
            ReviewOptionDto("beer-$it",it,if(it==4) "병" else "잔 $it",
                null,8000+it*1000)
        }
        val dto=item(options=options,status="unmatched",proposedId=null)
            .copy(extractedKind="other",candidates=emptyList(),newProductDraft=null)
        val card=mapServerPhotoReview(response(dto),fixture()).items.single()
            .copy(price=15000.0)
        val decision=mapConfirmedReviewDecision(card,dto,30.0,emptyMap())
        val actual=requireNotNull(decision.correctedOptions)
        assertEquals(4,actual.size)
        assertEquals(options.map { it.extractedOptionId },actual.map { it.optionId })
        assertEquals(15000,actual.first().priceKrw)
        assertEquals(options.last().extractedPriceKrw,actual.last().priceKrw)
        assertEquals(null,actual.last().pourMl)
    }

    @Test fun missingSecondaryBeerPriceBlocksPublishUntilOwnerEditsThatOption() {
        val first=ReviewOptionDto("beer-price-1",1,"잔",null,8000)
        val missing=ReviewOptionDto("beer-price-2",2,"병",null,null)
        val dto=item(options=listOf(first,missing),status="unmatched",proposedId=null)
            .copy(extractedKind="other",candidates=emptyList(),newProductDraft=null)
        val review=mapServerPhotoReview(response(dto),fixture())
        val card=review.items.single()
        assertEquals(2,PhotoReviewRules.countOptions(card))
        assertFalse(PhotoReviewRules.stats(review).canPublish)
        val fixed=PhotoReviewRules.editOption(card,
            PhotoReviewRules.OptionField.PRICE,0,"13000")
        assertTrue(PhotoReviewRules.problems(fixed).isEmpty())
        val decision=mapConfirmedReviewDecision(fixed,dto,30.0,emptyMap())
        val options=requireNotNull(decision.correctedOptions)
        assertEquals(listOf("beer-price-1","beer-price-2"),options.map { it.optionId })
        assertEquals(listOf(8000,13000),options.map { it.priceKrw })
        assertNull(options[1].pourMl)
    }

    @Test fun nonWhiskyKindNeverUsesStaleCatalogSuggestion() {
        val dto=item().copy(extractedKind="other")
        val card=mapServerPhotoReview(response(dto),fixture()).items.single()
        assertEquals(com.zerotoone.bottlemap.ui.owner.review.ReviewItemType.OTHER,card.type)
        assertNull(card.linkedProductId)
        val decision=mapConfirmedReviewDecision(card,dto,30.0,emptyMap())
        assertEquals(MockDecisionKind.CREATE_PRODUCT,decision.kind)
        assertNull(decision.productId)
        assertEquals("other",decision.newProduct?.category)
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
