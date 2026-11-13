package com.zerotoone.bottlemap.ui.owner.review

import com.zerotoone.bottlemap.data.owner.review.MockPhotoReviewRepository
import com.zerotoone.bottlemap.data.owner.review.MockPhotoReviewScenario
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** The v18 prototype's rules: problems(), groups, stats() and the card transitions. */
class PhotoReviewRulesTest {
    private fun item(scenario: MockPhotoReviewScenario, id: String) =
        scenario.initialState().items.first { it.id == id }

    @Test fun basicScenarioHasFiveCardsToCheckAndCannotPublish() {
        val stats = PhotoReviewRules.stats(MockPhotoReviewScenario.BASIC.initialState())
        assertEquals(listOf("glendronach", "hakushu", "arran", "bookers", "glen15"), stats.pending.map { it.id })
        assertEquals(listOf("ardbeg", "glen12"), stats.ready.map { it.id })
        assertEquals(3, stats.other.size)
        assertEquals(0, stats.done)
        assertEquals(5, stats.total)
        assertFalse(stats.canPublish)
    }

    @Test fun eachSeedLineShowsTheIssueOfItsScenario() {
        val s = MockPhotoReviewScenario.BASIC
        assertEquals(listOf(ReviewIssue.PRICE_CHOICE), PhotoReviewRules.problems(item(s, "glendronach")))
        assertEquals(listOf(ReviewIssue.MATCH), PhotoReviewRules.problems(item(s, "hakushu")))
        assertEquals(listOf(ReviewIssue.CANDIDATE), PhotoReviewRules.problems(item(s, "arran")))
        assertEquals(listOf(ReviewIssue.NEW), PhotoReviewRules.problems(item(s, "bookers")))
        assertEquals(listOf(ReviewIssue.PRICE), PhotoReviewRules.problems(item(s, "glen15")))
        assertEquals(listOf(ReviewIssue.MATCH, ReviewIssue.PRICE),
            PhotoReviewRules.problems(item(MockPhotoReviewScenario.MULTI_ISSUE, "hakushu")))
    }

    @Test fun readyScenarioCanPublish() {
        val stats = PhotoReviewRules.stats(MockPhotoReviewScenario.READY.initialState())
        assertTrue(stats.pending.isEmpty())
        assertEquals(100, stats.percent)
        assertTrue(stats.canPublish)
    }

    @Test fun missingDefaultPourBlocksPublishingEvenWhenEverythingIsChecked() {
        val ready = MockPhotoReviewScenario.READY.initialState()
        val stats = PhotoReviewRules.stats(ready.copy(defaultPour = 0.0))
        assertTrue(stats.noDefault)
        assertFalse(stats.canPublish)
        assertTrue(MockPhotoReviewScenario.NO_DEFAULT.initialState().items.first { it.id == "glen12" }
            .let { ReviewIssue.VOLUME in PhotoReviewRules.problems(it) })
    }

    @Test fun numberParsingFollowsThePrototype() {
        assertEquals(15000.0, priceValue("15,000원"), 0.0)
        assertTrue(priceValue("15000원원").isNaN())
        assertTrue(priceValue("12.5").isNaN())
        assertEquals(22.5, readNumeric("22.5"), 0.0)
        assertFalse(validVolume(22.5))
        assertFalse(validVolume(1000.0))
        assertTrue(validVolume(999.0))
        assertFalse(validPrice(100_000_000.0))
        assertEquals("15,000원", won(15000.0))
        assertEquals("—", won(0.0))
        assertEquals("—", won(Double.NaN))
    }

    @Test fun decimalVolumeIsReported() {
        assertTrue(ReviewIssue.VOLUME in PhotoReviewRules.problems(item(MockPhotoReviewScenario.BAD_INPUTS, "glen12")))
    }

    @Test fun duplicateServingsAndMoreThanTenOptionsNeedOptionReview() {
        val base = item(MockPhotoReviewScenario.BASIC, "ardbeg")
        val duplicate = base.copy(options = listOf(ReviewOption(30.0, 16000.0)))
        assertEquals(listOf(ReviewIssue.OPTION), PhotoReviewRules.problems(duplicate))
        val four = base.copy(options = listOf(ReviewOption(45.0, 1.0), ReviewOption(60.0, 1.0), ReviewOption(0.0, 1.0, true)))
        assertTrue(PhotoReviewRules.problems(four).isEmpty())
        val eleven = base.copy(options = (1..10).map { ReviewOption(it * 10.0 + 100.0, 20000.0) })
        assertEquals(listOf(ReviewIssue.OPTION), PhotoReviewRules.problems(eleven))
    }

    @Test fun zeroOptionLineAsksForAPrice() {
        val x = item(MockPhotoReviewScenario.ZERO_OPTION, "glen15")
        assertEquals(listOf(ReviewIssue.PRICE), PhotoReviewRules.problems(x))
        assertEquals(listOf(RecognizedOffer()), PhotoReviewRules.recognizedOffers(x))
        assertEquals("가격 미인식", PhotoReviewRules.offerPriceLabel(x, RecognizedOffer()))
    }

    @Test fun mergedNoticeCountsTheRealNumberOfLines() {
        val two = item(MockPhotoReviewScenario.MERGED_LINES, "glen12")
        assertEquals("같은 위스키가 두 줄 있어 하나로 합쳤어요.", PhotoReviewRules.mergedNotice(two))
        val source = two.mergeSources.first()
        val three = two.copy(mergeSources = listOf(source, source))
        assertEquals("같은 위스키가 세 줄 있어 하나로 합쳤어요.", PhotoReviewRules.mergedNotice(three))
        val eleven = two.copy(mergeSources = List(10) { source })
        assertEquals("같은 위스키가 11줄 있어 하나로 합쳤어요.", PhotoReviewRules.mergedNotice(eleven))
        assertNull(PhotoReviewRules.mergedNotice(item(MockPhotoReviewScenario.BASIC, "glen12")))
    }

    @Test fun sameVolumeConflictShowsTheVolumeOnceWithoutPrices() {
        val x = item(MockPhotoReviewScenario.MERGED_CONFLICT, "glen12")
        assertEquals(listOf(ReviewIssue.PHOTO_CONFLICT), PhotoReviewRules.problems(x))
        val offers = PhotoReviewRules.recognizedOffers(x)
        assertEquals(1, offers.size)
        assertNull(PhotoReviewRules.offerPriceLabel(x, offers[0]))
        assertNull(PhotoReviewRules.itemDisplayPrice(x))
    }

    @Test fun sourceLocationCountsLinesPerPhoto() {
        val s = MockPhotoReviewScenario.BASIC.initialState()
        assertEquals("3번째 장 1번째 줄", PhotoReviewRules.sourceLocation(s, s.items.first { it.id == "glen15" }))
        val noBox = MockPhotoReviewScenario.SOURCE_NO_BOX.initialState()
        assertEquals("4번째 장 · 위치 정보 없음",
            PhotoReviewRules.sourceLocation(noBox, noBox.items.first { it.id == "arran" }))
    }

    @Test fun renameToTheSameProductKeepsTheLink() {
        val x = item(MockPhotoReviewScenario.BASIC, "glen12")
        val (y, outcome) = PhotoReviewRules.applyRematch(x, listOf(MockPhotoReviewRepository.product("gf12")))
        assertEquals(PhotoReviewRules.RematchOutcome.SAME, outcome)
        assertEquals("gf12", y.linkedProductId)
        assertFalse(y.operatorPending)
    }

    @Test fun renameToAnotherSingleProductLinksItForOperatorCheck() {
        val x = item(MockPhotoReviewScenario.BASIC, "glen12").copy(name = "글렌피딕 15")
        val (y, outcome) = PhotoReviewRules.applyRematch(x, listOf(MockPhotoReviewRepository.product("gf15")))
        assertEquals(PhotoReviewRules.RematchOutcome.CHANGED, outcome)
        assertEquals("gf15", y.linkedProductId)
        assertEquals(OperatorReason.CHANGED, y.operatorReason)
    }

    @Test fun renameWithNoOrManyMatchesUnlinksForTheOperator() {
        val x = item(MockPhotoReviewScenario.BASIC, "glen12").copy(name = "글렌피딕")
        val (none, outcome) = PhotoReviewRules.applyRematch(x, emptyList())
        assertEquals(PhotoReviewRules.RematchOutcome.OPERATOR, outcome)
        assertNull(none.linkedProductId)
        assertEquals(OperatorReason.UNLINKED, none.operatorReason)
        assertTrue(PhotoReviewRules.problems(none).isEmpty())
        val many = PhotoReviewRules.applyRematch(x, listOf(MockPhotoReviewRepository.product("gf12"),
            MockPhotoReviewRepository.product("gf15"))).first
        assertNull(many.linkedProductId)
    }

    @Test fun notFoundWhiskyBecomesANewMenuWithoutCatalogFields() {
        val x = PhotoReviewRules.markAsNewForOperator(item(MockPhotoReviewScenario.BASIC, "arran"), "")
        assertEquals(ReviewMatch.NEW, x.match)
        assertTrue(x.nameEditMode)
        assertEquals(OperatorReason.NEW, x.operatorReason)
        assertEquals(listOf(ReviewIssue.NEW), PhotoReviewRules.problems(x))
    }

    @Test fun switchingCatalogWhiskyToOtherNeverLeavesAProductLink() {
        val linked = ReviewItem(
            id = "changed-to-other", name = "맥주 1",
            type = ReviewItemType.WHISKY,
            match = ReviewMatch.EXACT, linkedProductId = "old-whisky-product",
            linkedProductName = "Old Whisky",
            options = listOf(ReviewOption(60.0, 25000.0)),
            operatorPending = true, operatorReason = OperatorReason.CHANGED,
        )
        val other = PhotoReviewRules.reclassify(linked,30.0)
        assertEquals(ReviewItemType.OTHER,other.type)
        assertNull(other.linkedProductId)
        assertNull(other.linkedProductName)
        assertFalse(other.operatorPending)
        assertEquals(ReviewMatch.NEW,other.match)
        val restored = PhotoReviewRules.reclassify(other,30.0)
        assertEquals(ReviewItemType.WHISKY,restored.type)
        assertEquals("old-whisky-product",restored.linkedProductId)
        assertEquals(linked.options,restored.options)
    }

    @Test fun reclassifyingBackRestoresTheOptions() {
        val x = item(MockPhotoReviewScenario.RECLASSIFY, "glen12")
        val other = PhotoReviewRules.reclassify(x, 30.0)
        assertEquals(ReviewItemType.OTHER, other.type)
        assertEquals(PhotoReviewRules.optionSummary(x).size,
            PhotoReviewRules.optionSummary(other).size)
        val back = PhotoReviewRules.reclassify(other, 30.0)
        assertEquals(ReviewItemType.WHISKY, back.type)
        assertEquals(x.options, back.options)
        assertEquals(x.linkedProductId, back.linkedProductId)
        assertNull(back.classificationSnapshot)
    }

    @Test fun invalidOptionTextStaysVisibleUntilFixed() {
        val x = item(MockPhotoReviewScenario.BASIC, "glen12")
        val typed = PhotoReviewRules.editOption(x, PhotoReviewRules.OptionField.VOLUME, null, "22.5")
        assertEquals("22.5", PhotoReviewRules.optionFieldText(typed, PhotoReviewRules.OptionField.VOLUME, null))
        assertTrue(ReviewIssue.VOLUME in PhotoReviewRules.problems(typed))
        val fixed = PhotoReviewRules.editOption(typed, PhotoReviewRules.OptionField.VOLUME, null, "45")
        assertTrue(fixed.rawOptionEdits.isEmpty())
        assertEquals(VolumeSource.MANUAL, fixed.volumeSource)
    }

    @Test fun bottleOptionsNeedNoVolume() {
        val x = item(MockPhotoReviewScenario.BASIC, "glen12")
        val bottle = PhotoReviewRules.toggleBottle(x, null, 30.0)
        assertTrue(bottle.bottle)
        assertTrue(PhotoReviewRules.problems(bottle).isEmpty())
        val glass = PhotoReviewRules.toggleBottle(bottle, null, 30.0)
        assertEquals(30.0, glass.volume, 0.0)
    }

    @Test fun selectedProductWithDifferentEditionGoesToTheOperator() {
        assertTrue(MockPhotoReviewRepository.productConflicts("아란 셰리 캐스크", "아란 포트 캐스크"))
        assertFalse(MockPhotoReviewRepository.productConflicts("아란 셰리 캐스크", "아란 셰리 캐스크"))
        assertFalse(MockPhotoReviewRepository.productConflicts("하쿠슈 DR", "하쿠슈 Distiller’s Reserve"))
        assertTrue(MockPhotoReviewRepository.productConflicts("글렌피딕 15", "글렌피딕 12년"))
        val linked = PhotoReviewRules.linkChosenProduct(item(MockPhotoReviewScenario.BASIC, "arran"),
            MockPhotoReviewRepository.product("arran-port"), operatorCheck = true)
        assertEquals(OperatorReason.SELECTED_PRODUCT_CONFLICT, linked.operatorReason)
        assertTrue(PhotoReviewRules.problems(linked).isEmpty())
    }

    @Test fun ocrPriceSummaryUsesDefaultPourOnlyWhenPhotoHasNoSize() {
        val noSize = RecognizedOffer(priceKrw = 18000)
        assertEquals("30ml", PhotoReviewRules.offerVolumeLabel(noSize, 30.0))
        assertEquals("45ml", PhotoReviewRules.offerVolumeLabel(
            RecognizedOffer(volumeMl = 45, priceKrw = 18000), 30.0))
        assertEquals("Bottle", PhotoReviewRules.offerVolumeLabel(
            RecognizedOffer(bottle = true, priceKrw = 18000), 30.0))
        assertEquals("", PhotoReviewRules.offerVolumeLabel(noSize))
        assertEquals("18,000원", won(18000.0))
    }

    @Test fun everyScenarioLoads() {
        MockPhotoReviewScenario.entries.forEach { scenario ->
            val state = scenario.initialState()
            assertEquals(10, state.items.size)
            scenario.focusItemId?.let { id -> assertTrue(scenario.id, state.items.any { it.id == id }) }
            assertEquals(scenario, MockPhotoReviewScenario.fromId(scenario.id))
        }
    }
    @Test fun crossPhotoDuplicateProductServingNeedsExplicitPriceCorrection() {
        val first=ReviewItem(id="photo1",name="동일 위스키",linkedProductId="shared-product",
            volume=30.0,price=18000.0)
        val second=ReviewItem(id="photo2",name="동일 위스키",linkedProductId="shared-product",
            volume=30.0,price=21000.0)
        val review=PhotoReviewState(items=listOf(first,second),defaultPour=30.0)
        assertEquals(setOf("30ml"),PhotoReviewRules.duplicatePhotoPriceConflicts(review)["photo1"])
        assertTrue(ReviewIssue.DUPLICATE_PRICE in PhotoReviewRules.problems(first,review))
        assertFalse(PhotoReviewRules.stats(review).canPublish)
        val chosen=PhotoReviewRules.editOption(second,PhotoReviewRules.OptionField.PRICE,null,"18000")
        val resolved=review.copy(items=listOf(first,chosen))
        assertTrue(PhotoReviewRules.duplicatePhotoPriceConflicts(resolved).isEmpty())
        assertTrue(PhotoReviewRules.stats(resolved).canPublish)
    }

    @Test fun differentProductOrDifferentServingDoesNotCauseFalsePhotoPriceConflict() {
        val a=ReviewItem(id="line1",name="위스키",linkedProductId="product-1",volume=30.0,price=15000.0)
        val b=ReviewItem(id="line2",name="위스키",linkedProductId="product-1",volume=60.0,price=25000.0)
        val c=ReviewItem(id="line3",name="다른 위스키",linkedProductId="product-2",volume=30.0,price=29000.0)
        assertTrue(PhotoReviewRules.duplicatePhotoPriceConflicts(
            PhotoReviewState(items=listOf(a,b,c))).isEmpty())
        assertTrue(PhotoReviewRules.duplicatePhotoPriceConflicts(
            PhotoReviewState(items=listOf(a,a.copy(id="line4",price=18000.0,excluded=true)))).isEmpty())
    }

    @Test fun otherMultiPriceLineRequiresEveryPriceAndSupportsPerOptionEdit() {
        val other=ReviewItem(id="beer",name="맥주",type=ReviewItemType.OTHER,
            price=8000.0,volume=Double.NaN,
            options=listOf(ReviewOption(volume=Double.NaN,price=0.0,sourceOptionId="ocr-2")))
        assertTrue(ReviewIssue.PRICE in PhotoReviewRules.problems(other))
        val fixed=PhotoReviewRules.editOption(other,PhotoReviewRules.OptionField.PRICE,0,"12000")
        assertEquals(12000.0,fixed.options.single().price,0.0)
        assertTrue(PhotoReviewRules.problems(fixed).isEmpty())
        val removed=PhotoReviewRules.removeOption(fixed,0)
        assertEquals(1,PhotoReviewRules.countOptions(removed))
        assertTrue(PhotoReviewRules.problems(removed).isEmpty())
    }

}
