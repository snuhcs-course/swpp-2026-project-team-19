package com.zerotoone.bottlemap.network

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Spec 5.4 / backend ReviewItem: extractedKind is read-only; correctedKind is not a field. */
class OwnerMenuReviewContractTest {
    private val adapter = Moshi.Builder()
        .addLast(KotlinJsonAdapterFactory()).build()
        .adapter(ReviewItemDto::class.java)

    @Test fun nonWhiskyProductDecodesFromPublishedSpecFields() {
        val response = """
            {
              "extractedItemId": "line-1",
              "itemOrder": 1,
              "rawText": "Suntory Highball 10000",
              "extractedLineType": "product",
              "extractedKind": "other",
              "correctedLineType": null,
              "effectiveLineType": "product",
              "options": [{
                "extractedOptionId": "opt-1",
                "optionOrder": 1,
                "extractedOptionLabel": "Glass",
                "extractedPourMl": null,
                "extractedPriceKrw": 10000
              }]
            }
        """.trimIndent()
        val review = requireNotNull(adapter.fromJson(response))
        assertEquals("other", review.extractedKind)
        assertEquals("product", review.effectiveLineType)
        assertNull(review.correctedLineType)
        assertEquals(10000, review.options.single().extractedPriceKrw)
        assertFalse(adapter.toJson(review).contains("correctedKind"))
    }

    @Test fun nonProductCanHaveNullExtractedKind() {
        val review = requireNotNull(adapter.fromJson("""
            {
              "extractedItemId":"line-2",
              "itemOrder":2,
              "rawText":"HIGHBALL",
              "extractedLineType":"section_header",
              "extractedKind":null,
              "effectiveLineType":"section_header"
            }
        """.trimIndent()))
        assertNull(review.extractedKind)
        assertTrue(review.options.isEmpty())
    }
}
