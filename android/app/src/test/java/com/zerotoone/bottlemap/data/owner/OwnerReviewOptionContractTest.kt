package com.zerotoone.bottlemap.data.owner

import com.zerotoone.bottlemap.network.ReviewItemDto
import com.zerotoone.bottlemap.network.ReviewOptionDto
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
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
    @Test fun glassLabelsAreIgnoredInFinalServerOptionsButOcrIdsRemain() {
        val decision = MockReviewDecision(
            kind = MockDecisionKind.SELECT_PRODUCT,
            correctedOptions = listOf(
                MockMenuOption(firstId, "샷", 30, 20_000),
                MockMenuOption(secondId, "잔", 60, 35_000),
            ),
        )
        val options = ownerFinalReviewOptions(item(), decision, 35, whisky = true)
        assertEquals(listOf(firstId, secondId), options.map { it["extractedOptionId"] })
        assertEquals(listOf(30, 60), options.map { it["pourMl"] })
        assertEquals(listOf(null, null), options.map { it["optionLabel"] })
    }

    @Test fun sameMlWithDifferentLabelsCannotBePublishedTwice() {
        val decision = MockReviewDecision(
            kind = MockDecisionKind.SELECT_PRODUCT,
            correctedOptions = listOf(
                MockMenuOption(firstId, "잔", 30, 20_000),
                MockMenuOption(secondId, "샷", 30, 25_000),
            ),
        )
        assertThrows(IllegalArgumentException::class.java) {
            ownerFinalReviewOptions(item(), decision, 30, whisky = true)
        }
        val onePour = decision.copy(correctedOptions = listOf(
            MockMenuOption(firstId, "샷", 30, 20_000),
            MockMenuOption(secondId, "병", null, 180_000),
        ))
        val options = ownerFinalReviewOptions(item(), onePour, 30, whisky = true)
        assertNull(options[0]["optionLabel"])
        assertEquals("Bottle", options[1]["optionLabel"])
        assertNull(options[1]["pourMl"])
    }

    @Test fun manualMenuValidationAlsoRejectsDuplicateVolumeLabels() {
        val sameVolume = listOf(
            MockMenuOption("glass-a", "잔", 30, 20_000),
            MockMenuOption("glass-b", "샷", 30, 24_000),
        )
        assertEquals(
            "같은 제품에 동일한 용량 옵션을 중복 등록할 수 없어요.",
            manualMenuOptionError(sameVolume, "whisky"),
        )
        assertNull(manualMenuOptionError(
            sameVolume.mapIndexed { i, o -> if (i == 1) o.copy(pourMl = 60) else o },
            "whisky",
        ))
    }

    @Test fun existingServerOptionIsUpdatedByMlWithoutChangingItsStoredLabel() {
        val decision = MockReviewDecision(
            MockDecisionKind.SELECT_PRODUCT,
            correctedOptions = listOf(MockMenuOption(firstId, "잔", 30, 22_000)),
        )
        val saved = listOf(MockMenuOption("server-option", "샷", 30, 19_000))
        val result = ownerFinalReviewOptions(item(), decision, 30, whisky = true,
            existingOptions = saved)
        assertEquals("샷", result.single()["optionLabel"])
        assertEquals(30, result.single()["pourMl"])
        assertEquals(firstId, result.single()["extractedOptionId"])
        assertEquals(22_000, result.single()["priceKrw"])
    }

    @Test fun ambiguousLegacySameMlOptionsCannotBeSilentlyOverwritten() {
        val decision = MockReviewDecision(
            MockDecisionKind.SELECT_PRODUCT,
            correctedOptions = listOf(MockMenuOption(firstId, "잔", 30, 22_000)),
        )
        val saved = listOf(
            MockMenuOption("saved-one", "잔", 30, 18_000),
            MockMenuOption("saved-two", "샷", 30, 19_000),
        )
        assertThrows(IllegalArgumentException::class.java) {
            ownerFinalReviewOptions(item(), decision, 30, whisky = true,
                existingOptions = saved)
        }
    }

    @Test fun existingLegacySizedBottleKeepsItsServerKey() {
        val decision = MockReviewDecision(
            MockDecisionKind.SELECT_PRODUCT,
            correctedOptions = listOf(MockMenuOption(secondId, "Bottle", null, 130_000)),
        )
        val saved = listOf(MockMenuOption("saved-bottle", "병", 700, 100_000))
        val result = ownerFinalReviewOptions(item(), decision, 30, whisky = true,
            existingOptions = saved)
        assertEquals("병", result.single()["optionLabel"])
        assertEquals(700, result.single()["pourMl"])
    }

    @Test fun partialUpdateKeepsUnphotographedServingsAndTheirServerIdentity() {
        val decision = MockReviewDecision(MockDecisionKind.SELECT_PRODUCT,
            correctedOptions = listOf(MockMenuOption(firstId, "잔", 30, 22000)))
        val saved = listOf(
            MockMenuOption("saved-30", "잔", 30, 18000),
            MockMenuOption("saved-60", "샷", 60, 34000,
                discount = MockDiscount(30000, 100L, 900L)),
            MockMenuOption("saved-bottle", "병", 700, 130000),
        )
        val final = ownerFinalReviewOptions(item(), decision, 30, whisky = true,
            existingOptions = saved)
        assertEquals(3, final.size)
        assertEquals(listOf("잔","샷","병"), final.map { it["optionLabel"] })
        assertEquals(listOf(30,60,700), final.map { it["pourMl"] })
        assertEquals(listOf(22000,34000,130000), final.map { it["priceKrw"] })
        assertEquals(listOf(firstId,null,null), final.map { it["extractedOptionId"] })
    }

    @Test fun partialUpdateRefusesToDropServingIfCombinedOptionsExceedBackendLimit() {
        val decision = MockReviewDecision(MockDecisionKind.SELECT_PRODUCT,
            correctedOptions = listOf(MockMenuOption(firstId, "잔", 30, 22000)))
        val saved = (1..10).map { i ->
            MockMenuOption("saved-$i", "잔", i * 30 + 30, 10000 + i)
        }
        assertThrows(IllegalArgumentException::class.java) {
            ownerFinalReviewOptions(item(), decision, 30, whisky = true,
                existingOptions = saved)
        }
    }

    @Test fun unlinkedPhotoUpdatePreservesSavedServingOptionsByBarAndNormalizedName() {
        val snapshot = MockOwnerSnapshot(
            products = listOf(MockCatalogProduct("unlinked:row1", "", "글렌피딕 12년",
                catalogMatched = false)),
            menuItems = listOf(MockBarMenuItem("row1", "bar1", "unlinked:row1",
                listOf(MockMenuOption("old-30", "잔", 30, 15000),
                    MockMenuOption("old-60", "샷", 60, 26000)),
                displayNameOverride = "글렌피딕 12년")),
        )
        val old = ownerExistingUnlinkedOptions(snapshot, "bar1", " 글렌피딕12 ")
        assertEquals(listOf(30,60),old.map { it.pourMl })
        assertEquals(emptyList<MockMenuOption>(),
            ownerExistingUnlinkedOptions(snapshot,"bar2","글렌피딕 12년"))
    }

    @Test fun appliedInSecondPreflightIsSuccessfulWithoutAnotherPost() {
        val applied = com.zerotoone.bottlemap.network.MenuImportStatusDto(
            menuImportId = "same-import", barId = "bar-1",
            status = "applied", reviewVersion = 4,
        )
        assertFalse(photoImportNeedsApply(applied, "same-import", 3))
        try {
            photoImportNeedsApply(applied.copy(status = "ready_for_review"),
                "same-import", 3)
            org.junit.Assert.fail("Old reviewVersion must be rejected")
        } catch (_: com.zerotoone.bottlemap.data.owner.review.ReviewVersionConflictException) { }
        assertTrue(photoImportNeedsApply(
            applied.copy(status = "ready_for_review", reviewVersion = 3),
            "same-import", 3))
    }

    @Test fun groupedProposedChangeAppliesWhenOnlyLaterOcrLineIsPublished() {
        val grouped = com.zerotoone.bottlemap.network.ProposedChangeDto(
            changeId = "change-a", changeType = "update", extractedItemId = "line-a",
            summary = "두 줄 같은 메뉴", decision = "apply",
            extractedItemIds = listOf("line-a", "line-b"),
        )
        assertEquals("apply", photoImportChangeDecision(grouped, setOf("line-b")))
        assertEquals("ignore", photoImportChangeDecision(grouped, emptySet()))
        assertEquals("apply", photoImportChangeDecision(
            grouped.copy(extractedItemIds = emptyList()), setOf("line-a")))
        assertEquals("ignore", photoImportChangeDecision(
            grouped.copy(changeType = "remove"), setOf("line-a", "line-b")))
    }

    @Test fun groupedOtherRetentionDoesNotReintroduceOldPriceInBottleLine() {
        val saved = listOf(
            MockMenuOption("old-30", "샷", 30, 8_000),
            MockMenuOption("old-60", "잔", 60, 20_000),
        )
        val group = listOf("photo-30", "photo-bottle")
        val keys = mapOf(
            "photo-30" to setOf("ml:30"),
            "photo-bottle" to setOf("bottle"),
        )
        val retained30 = ownerRetainedOptionsForGroupedLine(
            "photo-30", group, keys, saved)
        val retainedBottle = ownerRetainedOptionsForGroupedLine(
            "photo-bottle", group, keys, saved)
        assertEquals(listOf("old-30", "old-60"), retained30.map { it.optionId })
        assertTrue(retainedBottle.isEmpty())
        // The first line can overwrite 30ml while preserving 60ml's discount
        // identity. The second Bottle-only line must not re-add old 30ml.
        val photo30 = item().copy(options = listOf(
            ReviewOptionDto(firstId, 1, "잔", 30, 9_000),
        ))
        val firstDecision = MockReviewDecision(
            MockDecisionKind.CREATE_PRODUCT,
            correctedOptions = listOf(MockMenuOption(firstId, "잔", 30, 9_000)),
        )
        val posted30 = ownerFinalReviewOptions(
            photo30, firstDecision, 30, false, retained30)
        assertEquals(setOf(9_000, 20_000),
            posted30.map { it["priceKrw"] as Int }.toSet())
        assertTrue(posted30.none { it["priceKrw"] == 8_000 })
        assertTrue(retainedBottle.isEmpty())
    }

    @Test fun catalogLinkToExistingUnlinkedMenuRetainsUnseenOptions() {
        val row = MockBarMenuItem("existing-x", "bar-1", "unlinked:existing-x",
            listOf(
                MockMenuOption("old-30", "샷", 30, 12_000),
                MockMenuOption("old-bottle", "병", null, 130_000),
            ))
        val snapshot = MockOwnerSnapshot(menuItems = listOf(row))
        val original = com.zerotoone.bottlemap.network.MenuImportStatusDto(
            menuImportId = "import-1", barId = "bar-1",
            status = "ready_for_review", reviewVersion = 4,
            proposedChanges = listOf(com.zerotoone.bottlemap.network.ProposedChangeDto(
                changeId = "change-1", changeType = "update",
                barMenuItemId = "existing-x", extractedItemId = "photo-30",
                extractedItemIds = listOf("photo-30", "photo-bottle"),
                summary = "상품 연결", decision = "apply",
            )),
        )
        val options = ownerPhotoSelectionExistingOptions(
            snapshot, original, "bar-1", "photo-bottle", "catalog-p")
        assertEquals(listOf("old-30", "old-bottle"), options.map { it.optionId })
        val changed = ownerFinalReviewOptions(
            item().copy(options = listOf(ReviewOptionDto(firstId, 1, "잔", 30, 15_000))),
            MockReviewDecision(MockDecisionKind.SELECT_PRODUCT,
                productId = "catalog-p",
                correctedOptions = listOf(MockMenuOption(firstId, "잔", 30, 15_000))),
            30, true, options)
        assertEquals(2, changed.size)
        assertEquals(130_000, changed.last()["priceKrw"])
        assertEquals("병", changed.last()["optionLabel"])
    }

}
