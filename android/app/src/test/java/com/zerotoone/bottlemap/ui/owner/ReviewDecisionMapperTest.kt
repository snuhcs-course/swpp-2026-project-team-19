// AI-generated with ChatGPT (Hojin Nam, 2026-10-06, PR #15). Reviewed by Hojin Nam.
package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.network.ChangeDecisionDto
import com.zerotoone.bottlemap.network.MenuImportStatusDto
import com.zerotoone.bottlemap.network.NewProductDraftDto
import com.zerotoone.bottlemap.network.ProposedChangeDto
import com.zerotoone.bottlemap.network.ReviewImageDto
import com.zerotoone.bottlemap.network.ReviewItemDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ReviewDecisionMapperTest {
    @Test
    fun defaultReview_coversEveryItemAndChangeUsingBackendPolicy() {
        val response = MenuImportStatusDto(
            menuImportId = "import-1",
            barId = "bar-1",
            mode = "partial_update",
            status = "ready_for_review",
            reviewVersion = 7,
            images = listOf(
                ReviewImageDto(
                    imageId = "image-1",
                    imageOrder = 1,
                    imageUrl = "http://example.test/image.jpg",
                    items = listOf(
                        nonProductItem(),
                        matchedProductItem(),
                        newProductItem(),
                    ),
                ),
            ),
            proposedChanges = listOf(
                ProposedChangeDto(
                    changeId = "change-1",
                    changeType = "add",
                    extractedItemId = "item-new",
                    summary = "새 술 추가",
                    decision = "pending",
                ),
            ),
        )

        val request = response.buildDefaultReviewRequest()

        assertEquals(7, request.reviewVersion)
        assertEquals(3, request.itemDecisions.size)
        assertEquals(1, request.changeDecisions.size)

        val nonProduct = request.itemDecisions[0]
        assertEquals("confirm_non_product", nonProduct["action"])
        assertEquals("section_header", nonProduct["finalLineType"])

        val matched = request.itemDecisions[1]
        assertEquals("select_existing_product", matched["action"])
        assertEquals("product-existing", matched["productId"])

        val created = request.itemDecisions[2]
        assertEquals("create_product", created["action"])
        val brand = created["brand"] as Map<*, *>
        assertEquals("new", brand["type"])
        assertEquals("Unknown Distillery", brand["canonicalName"])
        val product = created["product"] as Map<*, *>
        assertEquals("Mystery 12", product["displayName"])
        assertEquals(12, product["ageYears"])

        assertEquals(
            ChangeDecisionDto(changeId = "change-1", decision = "apply"),
            request.changeDecisions.single(),
        )
    }

    @Test
    fun productWithoutProposalOrDraft_isRejectedBeforeNetworkSubmit() {
        val item = ReviewItemDto(
            extractedItemId = "item-bad",
            itemOrder = 1,
            rawText = "Unresolved",
            extractedLineType = "product",
            effectiveLineType = "product",
            proposedProductId = null,
            newProductDraft = null,
        )

        val error = runCatching { item.defaultDecision() }.exceptionOrNull()

        assertTrue(error is IllegalStateException)
        assertTrue(error?.message?.contains("No product proposal") == true)
    }

    private fun nonProductItem() = ReviewItemDto(
        extractedItemId = "item-header",
        itemOrder = 1,
        rawText = "WHISKY",
        extractedLineType = "section_header",
        effectiveLineType = "section_header",
    )

    private fun matchedProductItem() = ReviewItemDto(
        extractedItemId = "item-existing",
        itemOrder = 2,
        rawText = "Deanston 12",
        extractedLineType = "product",
        effectiveLineType = "product",
        initialResolutionStatus = "exact_match",
        extractedProductName = "Deanston 12",
        proposedProductId = "product-existing",
    )

    private fun newProductItem() = ReviewItemDto(
        extractedItemId = "item-new",
        itemOrder = 3,
        rawText = "Mystery 12",
        extractedLineType = "product",
        effectiveLineType = "product",
        initialResolutionStatus = "unmatched",
        extractedProductName = "Mystery 12",
        proposedProductId = null,
        newProductDraft = NewProductDraftDto(
            brandText = "Unknown Distillery",
            category = "whisky",
            displayName = "Mystery 12",
            ageYears = 12,
        ),
    )
}
