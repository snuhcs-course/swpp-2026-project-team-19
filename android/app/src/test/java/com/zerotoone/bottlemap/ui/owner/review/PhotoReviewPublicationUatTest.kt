package com.zerotoone.bottlemap.ui.owner.review

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** UAT 4.5: confirmation numbers must reflect reviewed choices, not raw OCR. */
class PhotoReviewPublicationUatTest {
    @Test fun previewCountsChangedExistingPriceAndUnlinkedMenuSeparately() {
        val key = PhotoReviewRules.servingKey(ReviewOption(30.0, 15000.0))
        val existing = ReviewItem(
            id = "old", name = "아드벡 10", linkedProductId = "product-1",
            price = 15000.0,
            existingServingPricesByProductId = mapOf(
                "product-1" to listOf(ReviewPriceCandidate(
                    servingKey = key, volumeMl = 30, priceKrw = 12000,
                    existing = true,
                )),
            ),
            chosenServingPrices = mapOf(key to 15000),
        )
        val unlinked = ReviewItem(
            id = "new", name = "미등록 위스키", match = ReviewMatch.NEW,
            nameSaved = true, linkedProductId = null, price = 18000.0,
        )
        val excluded = unlinked.copy(id = "excluded", excluded = true)
        val other = ReviewItem(id = "cocktail", name = "칵테일",
            type = ReviewItemType.OTHER, price = 9000.0)
        val state = PhotoReviewState(items = listOf(existing, unlinked, other, excluded))

        assertTrue(PhotoReviewRules.stats(state).canPublish)
        val preview = PhotoReviewRules.publicationPreview(state)
        assertEquals(1, preview.changedExistingPrices)
        assertEquals(1, preview.publishWithoutProduct)
    }

    @Test fun unchangedExistingPriceIsNotCountedAsAnUpdate() {
        val key = PhotoReviewRules.servingKey(ReviewOption(30.0, 12000.0))
        val old = ReviewItem(
            id = "old", name = "아드벡 10", linkedProductId = "product-1",
            price = 12000.0,
            existingServingPricesByProductId = mapOf(
                "product-1" to listOf(ReviewPriceCandidate(
                    servingKey = key, volumeMl = 30, priceKrw = 12000,
                    existing = true,
                )),
            ),
        )
        val counts = PhotoReviewRules.publicationPreview(PhotoReviewState(items = listOf(old)))
        assertEquals(0, counts.changedExistingPrices)
        assertEquals(0, counts.publishWithoutProduct)
    }
    @Test fun existingUnlinkedOtherAndWhiskyCountChangedServingOnlyOncePerCard() {
        val thirty = PhotoReviewRules.servingKey(ReviewOption(30.0, 15000.0))
        val sixty = PhotoReviewRules.servingKey(ReviewOption(60.0, 23000.0))
        val oldThirty = ReviewPriceCandidate(
            servingKey = thirty, volumeMl = 30, priceKrw = 12000, existing = true,
        )
        val oldSixty = ReviewPriceCandidate(
            servingKey = sixty, volumeMl = 60, priceKrw = 20000, existing = true,
        )
        val other = ReviewItem(
            id = "other", name = "바 전용 칵테일", type = ReviewItemType.OTHER,
            price = 15000.0,
            options = listOf(ReviewOption(60.0, 23000.0)),
            priceCandidates = listOf(oldThirty, oldSixty),
            chosenServingPrices = mapOf(thirty to 15000, sixty to 23000),
        )
        val unlinkedWhisky = ReviewItem(
            id = "whisky", name = "바 전용 위스키", match = ReviewMatch.NEW,
            nameSaved = true, newConfirmed = true, price = 15000.0,
            priceCandidates = listOf(oldThirty),
            chosenServingPrices = mapOf(thirty to 15000),
        )
        val state = PhotoReviewState(items = listOf(other, unlinkedWhisky))
        assertEquals(2, PhotoReviewRules.publicationPreview(state).changedExistingPrices)
    }

    @Test fun uat45ChangedPriceExcludedByStep10CorrectlyReportsZero() {
        val serving = PhotoReviewRules.servingKey(ReviewOption(30.0, 15000.0))
        val selected = ReviewItem(
            id = "chosen-price", name = "가격 변경한 위스키", price = 15000.0,
            linkedProductId = "known-product",
            existingServingPricesByProductId = mapOf(
                "known-product" to listOf(ReviewPriceCandidate(
                    servingKey = serving, volumeMl = 30,
                    priceKrw = 12000, existing = true,
                )),
            ),
            chosenServingPrices = mapOf(serving to 15000),
        )
        assertEquals(1, PhotoReviewRules.publicationPreview(
            PhotoReviewState(items = listOf(selected))).changedExistingPrices)
        // In the actual UAT sequence step 10 excluded the same changed card.
        assertEquals(0, PhotoReviewRules.publicationPreview(
            PhotoReviewState(items = listOf(selected.copy(excluded = true)))
        ).changedExistingPrices)
    }

    @Test fun unlinkedExcludedMergedUnchangedAndNewServingsDoNotInflateChangedCount() {
        val thirty = PhotoReviewRules.servingKey(ReviewOption(30.0, 12000.0))
        val sixty = PhotoReviewRules.servingKey(ReviewOption(60.0, 19000.0))
        val saved = ReviewPriceCandidate(
            servingKey = thirty, volumeMl = 30, priceKrw = 12000, existing = true,
        )
        val unchanged = ReviewItem(
            id = "unchanged", name = "그대로", type = ReviewItemType.OTHER,
            price = 12000.0, options = listOf(ReviewOption(60.0, 19000.0)),
            priceCandidates = listOf(saved),
        )
        val excluded = unchanged.copy(id = "excluded", name = "제외", price = 14000.0,
            excluded = true)
        val merged = unchanged.copy(id = "merged", name = "병합", price = 14000.0,
            mergedInto = "unchanged")
        val newlyAdded = unchanged.copy(id = "new-size", name = "새 용량", price = 19000.0,
            volume = 60.0,
            options = emptyList(),
            priceCandidates = listOf(saved),
        )
        assertEquals(sixty, PhotoReviewRules.servingKey(ReviewOption(60.0, 19000.0)))
        val preview = PhotoReviewRules.publicationPreview(
            PhotoReviewState(items = listOf(unchanged, excluded, merged, newlyAdded)))
        assertEquals(0, preview.changedExistingPrices)
    }

}
