package com.zerotoone.bottlemap.data.owner

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OwnerPhotoReviewPolicyTest {
    private fun exact(id: String, price: Int, ml: Int = 30) = MockExtractedLine(
        extractedItemId = id,
        sourceText = "글렌피딕 12년",
        kind = MockLineKind.PRODUCT,
        suggestedProductId = "product-glenfiddich",
        candidateProductIds = listOf("product-glenfiddich", "other-candidate"),
        options = listOf(MockMenuOption("option-$id", label = "잔", pourMl = ml, priceKrw = price)),
        decision = MockReviewDecision(
            kind = MockDecisionKind.SELECT_PRODUCT, productId = "product-glenfiddich",
        ),
        mockAutoAccepted = true,
    )
    private fun image(order: Int, vararg lines: MockExtractedLine) =
        MockPhotoExtraction("image-$order", "content://photo/$order", order, lines.toList())

    @Test fun twoPhotosWithDifferentPricesRequireManualInput() {
        val original = listOf(image(1,exact("first",17000)), image(2,exact("second",19000)))
        val adjusted = requirePhotoPriceReviewOnConflict(original)
        adjusted.flatMap { it.lines }.forEach { line ->
            assertEquals(0,line.options.single().priceKrw)
            assertNull(line.decision)
            assertTrue(line.needsPriceEntry)
            assertFalse(line.mockAutoAccepted)
            assertEquals(listOf("product-glenfiddich"),line.candidateProductIds)
        }
        assertEquals(17000,original[0].lines.single().options.single().priceKrw)
    }

    @Test fun identicalPricesStayAutomaticAndPreserveExtractedOptionIdentity() {
        val first=exact("one",18000)
        val lines=requirePhotoPriceReviewOnConflict(
            listOf(image(1,first),image(2,exact("two",18000)))).flatMap { it.lines }
        assertEquals(first,lines.first())
        assertTrue(lines.all { it.mockAutoAccepted })
        assertEquals("option-one",lines.first().options.single().optionId)
    }

    @Test fun differentServingSizesDoNotConflict() {
        val lines=requirePhotoPriceReviewOnConflict(listOf(
            image(1,exact("one",18000,30)), image(2,exact("two",27000,45))
        )).flatMap { it.lines }
        assertTrue(lines.all { it.decision?.kind == MockDecisionKind.SELECT_PRODUCT })
    }

    @Test fun alreadyUnmatchedOrUnpricedLinesRemainOwnerReview() {
        val unresolved=exact("unmatched",17000).copy(
            suggestedProductId=null, decision=null, mockAutoAccepted=false)
        val unpriced=exact("unpriced",0).copy(decision=null,mockAutoAccepted=false,
            needsPriceEntry=true)
        val lines=requirePhotoPriceReviewOnConflict(listOf(
            image(1,unresolved,unpriced),image(2,exact("valid",19000))
        )).flatMap { it.lines }
        assertEquals(unresolved,lines[0])
        assertEquals(unpriced,lines[1])
        assertEquals(19000,lines[2].options.single().priceKrw)
    }

    @Test fun onlyConflictingOptionIsClearedInMultiOptionLine() {
        val first=exact("one",18000).copy(options=listOf(
            MockMenuOption("a",label="잔",pourMl=30,priceKrw=18000),
            MockMenuOption("b",label="잔",pourMl=45,priceKrw=24000)))
        val second=exact("two",19000).copy(options=listOf(
            MockMenuOption("c",label="잔",pourMl=30,priceKrw=19000),
            MockMenuOption("d",label="잔",pourMl=45,priceKrw=24000)))
        val lines=requirePhotoPriceReviewOnConflict(
            listOf(image(1,first),image(2,second))).flatMap { it.lines }
        assertEquals(listOf(0,24000),lines[0].options.map { it.priceKrw })
        assertEquals(listOf(0,24000),lines[1].options.map { it.priceKrw })
    }
    @Test fun manuallyReviewedDifferentPricesMustNotPublishInPhotoOrder() {
        val first=exact("one",17000).copy(mockAutoAccepted=false,
            decision=MockReviewDecision(MockDecisionKind.SELECT_PRODUCT,
                productId="product-glenfiddich",
                correctedOptions=listOf(MockMenuOption("one",label="잔",pourMl=30,priceKrw=17000))))
        val second=exact("two",19000).copy(mockAutoAccepted=false,
            decision=MockReviewDecision(MockDecisionKind.SELECT_PRODUCT,
                productId="product-glenfiddich",
                correctedOptions=listOf(MockMenuOption("two",label="잔",pourMl=30,priceKrw=19000))))
        val job=MockMenuImport("job","bar",MockImportStatus.READY_FOR_REVIEW,1,
            listOf(image(1,first),image(2,second)))
        assertEquals(setOf("product-glenfiddich"),conflictingReviewedPhotoPrices(job))
        assertTrue(conflictingReviewedPhotoPrices(job.copy(images=listOf(
            image(1,first),image(2,second.copy(
                decision=second.decision?.copy(correctedOptions=listOf(
                    MockMenuOption("two",label="잔",pourMl=30,priceKrw=17000)))))))).isEmpty())
    }

}
