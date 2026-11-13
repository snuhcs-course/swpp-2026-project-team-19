package com.zerotoone.bottlemap.data.owner

import com.zerotoone.bottlemap.network.ReviewItemDto
import com.zerotoone.bottlemap.network.ReviewOptionDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test

class OwnerReviewOptionContractTest {
    private val firstId = "11111111-1111-4111-8111-111111111111"
    private val secondId = "22222222-2222-4222-8222-222222222222"

    private fun item() = ReviewItemDto(
        extractedItemId = "33333333-3333-4333-8333-333333333333",
        itemOrder = 1,
        rawText = "Whisky 30ml 20000",
        extractedLineType = "product",
        effectiveLineType = "product",
        options = listOf(
            ReviewOptionDto(firstId, 1, "잔", null, 20_000),
            ReviewOptionDto(secondId, 2, "병", null, 180_000),
        ),
    )

    @Test fun fullFinalListKeepsActualOcrIdAndMarksNewOptionAsUnlinked() {
        val decision = MockReviewDecision(
            kind = MockDecisionKind.SELECT_PRODUCT,
            correctedOptions = listOf(
                MockMenuOption(firstId, "잔", 45, 21_000),
                MockMenuOption("manual-added", "다른 잔", 60, 35_000),
            ),
        )
        val result = ownerFinalReviewOptions(item(), decision, 30, whisky = true)
        assertEquals(2, result.size)
        assertEquals(firstId, result[0]["extractedOptionId"])
        assertEquals(45, result[0]["pourMl"])
        assertEquals(21_000, result[0]["priceKrw"])
        assertNull(result[1]["extractedOptionId"])
        assertEquals(60, result[1]["pourMl"])
        assertEquals(35_000, result[1]["priceKrw"])
        // Omitted OCR options are omitted from this final list. No excludedOptionIds.
        assertEquals(false, result.any { it["extractedOptionId"] == secondId })
    }

    @Test fun defaultPourOnlyAppliesToUnspecifiedWhiskyGlass() {
        val decision = MockReviewDecision(
            kind = MockDecisionKind.SELECT_PRODUCT,
            correctedOptions = listOf(
                MockMenuOption(firstId, "잔", null, 20_000),
                MockMenuOption(secondId, "병", null, 180_000),
            ),
        )
        val whisky = ownerFinalReviewOptions(item(), decision, 35, whisky = true)
        assertEquals(35, whisky[0]["pourMl"])
        assertNull(whisky[1]["pourMl"])
        val other = ownerFinalReviewOptions(item(), decision, 35, whisky = false)
        assertNull(other[0]["pourMl"])
    }

    @Test fun duplicateOcrIdentityIsRejectedBeforeNetworkWrite() {
        val decision = MockReviewDecision(
            kind = MockDecisionKind.SELECT_PRODUCT,
            correctedOptions = listOf(
                MockMenuOption(firstId, "잔", 30, 20_000),
                MockMenuOption(firstId, "잔", 45, 25_000),
            ),
        )
        assertThrows(IllegalArgumentException::class.java) {
            ownerFinalReviewOptions(item(), decision, 30, whisky = true)
        }
    }

    @Test fun invalidPricesAndMoreThanTenOptionsAreRejected() {
        val noPrice = MockReviewDecision(
            kind = MockDecisionKind.SELECT_PRODUCT,
            correctedOptions = listOf(MockMenuOption(firstId, "잔", 30, 0)),
        )
        assertThrows(IllegalArgumentException::class.java) {
            ownerFinalReviewOptions(item(), noPrice, 30, whisky = true)
        }
        val tooMany = MockReviewDecision(
            kind = MockDecisionKind.CREATE_PRODUCT,
            correctedOptions = (1..11).map {
                MockMenuOption("manual-$it", "잔 $it", it * 10, it * 1000)
            },
        )
        assertThrows(IllegalArgumentException::class.java) {
            ownerFinalReviewOptions(item(), tooMany, 30, whisky = true)
        }
    }
}
