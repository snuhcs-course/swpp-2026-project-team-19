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
        val state = PhotoReviewState(items = listOf(existing, unlinked, excluded))

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
}
