package com.zerotoone.bottlemap.data.owner

import com.zerotoone.bottlemap.network.OwnerApplicationBarDto
import com.zerotoone.bottlemap.network.OwnerApplicationDto
import org.junit.Assert.*
import org.junit.Test

class OwnerLiveSafetyRulesTest {
    private fun rejects(block: () -> Unit) {
        try {
            block()
            fail("Expected safe rejection")
        } catch (_: IllegalArgumentException) {
            // Do not perform an unsafe mutation.
        }
    }

    @Test fun changedAddressNeedsNewCoordinates() {
        val original = MockBar("bar1", "Bar", "Old address",
            latitude = 37.1, longitude = 127.1)
        rejects { requireMovedBarCoordinates(original, original.copy(address = "New address")) }
        rejects { requireMovedBarCoordinates(original,
            original.copy(address = "New address", latitude = null, longitude = null)) }
        assertEquals(37.2 to 127.2, requireMovedBarCoordinates(original,
            original.copy(address = "New address", latitude = 37.2, longitude = 127.2)))
        assertNull(requireMovedBarCoordinates(original, original))
    }

    @Test fun pendingClaimRecoveryMatchesExactExistingBarIdentity() {
        val draft = MockRegistrationDraft(kind = MockApplicationKind.EXISTING_BAR,
            existingBarId = "bar-B", businessNumberDigits = "1234567890")
        fun application(barId: String) = OwnerApplicationDto(
            applicationId = "application-$barId", applicationType = "existing_bar",
            status = "pending", bar = OwnerApplicationBarDto(barId, "Bar", "Address"),
            businessRegistrationNumber = "1234567890",
            createdAt = "2026-11-03T00:00:00Z",
        )
        assertFalse(matchesPendingOwnerApplication(application("bar-A"), draft))
        assertTrue(matchesPendingOwnerApplication(application("bar-B"), draft))
        assertFalse(matchesPendingOwnerApplication(application("bar-B").copy(
            businessRegistrationNumber = "0000000000"), draft))
    }

    @Test fun sourcePhotoUsesFreshSignedUrlButKeepsLocalPickerUri() {
        assertEquals("https://server/new", currentReviewImageUri(
            "https://server/expired", "https://server/new"))
        assertEquals("https://server/new", currentReviewImageUri(
            "http://server/expired", "https://server/new"))
        assertEquals("content://picker/1", currentReviewImageUri(
            "content://picker/1", "https://server/new"))
    }

    @Test fun reviewVersionChangeInvalidatesCachedDecisions() {
        val photo = MockPhotoExtraction("photo", "content://photo", 1,
            listOf(MockExtractedLine("line", "Whisky", MockLineKind.PRODUCT)))
        val ready = MockMenuImport("job", "bar", MockImportStatus.READY_FOR_REVIEW,
            3, listOf(photo))
        assertFalse(needsReviewDetailReload(ready, 3))
        assertTrue(needsReviewDetailReload(ready, 4))
        assertTrue(needsReviewDetailReload(ready.copy(images = emptyList()), 3))
        assertTrue(needsReviewDetailReload(null, 3))
    }

    @Test fun unsupportedOptionFieldClearingIsRejected() {
        val extracted = MockMenuOption("opt", label = "잔", pourMl = 30, priceKrw = 17000)
        rejects { validateReviewOptionClearing(extracted.copy(label = null), extracted) }
        rejects { validateReviewOptionClearing(extracted.copy(pourMl = null), extracted) }
        validateReviewOptionClearing(extracted.copy(priceKrw = 18000), extracted)
        validateReviewOptionClearing(extracted.copy(pourMl = 60, label = "더블"), extracted)
    }

    @Test fun multiplePhotosForOneProductRetainBothServings() {
        fun row(id: String, ml: Int, price: Int) = MockExtractedLine(
            id, "Whisky $ml ml", MockLineKind.PRODUCT,
            options = listOf(MockMenuOption("option-$id", pourMl = ml, priceKrw = price)),
            decision = MockReviewDecision(MockDecisionKind.SELECT_PRODUCT,
                productId = "product", correctedOptions = listOf(
                    MockMenuOption("option-$id", pourMl = ml, priceKrw = price))),
        )
        val job = MockMenuImport("job", "bar", MockImportStatus.READY_FOR_REVIEW,
            1, listOf(
                MockPhotoExtraction("image-1", "content://1", 1,
                    listOf(row("thirty", 30, 17000))),
                MockPhotoExtraction("image-2", "content://2", 2,
                    listOf(row("sixty", 60, 29000))),
            ))
        val grouped = reviewedServingsByProduct(job, setOf("product"))
        assertEquals(listOf(30, 60), grouped.getValue("product").map { it.pourMl })
        assertEquals(listOf(17000, 29000), grouped.getValue("product").map { it.priceKrw })
        assertTrue(reviewedServingsByProduct(job, setOf("other")).isEmpty())
    }

    @Test fun bottleLanguagesAndMatchingGlassVolumesShareServingIdentity() {
        fun line(id: String, label: String, price: Int): MockExtractedLine {
            val option = MockMenuOption("option-$id", label = label, pourMl = null,
                priceKrw = price)
            return MockExtractedLine(
                extractedItemId = id, sourceText = "Lagavulin Bottle",
                kind = MockLineKind.PRODUCT, options = listOf(option),
                decision = MockReviewDecision(MockDecisionKind.SELECT_PRODUCT,
                    productId = "lagavulin", correctedOptions = listOf(option)))
        }
        val job = MockMenuImport("job", "bar", MockImportStatus.READY_FOR_REVIEW, 1,
            listOf(
                MockPhotoExtraction("first", "content://first", 1,
                    listOf(line("bottle-ko", "병", 150000))),
                MockPhotoExtraction("second", "content://second", 2,
                    listOf(line("bottle-en", "Bottle", 150000)))))
        val priced = reviewedServingsByProduct(job, setOf("lagavulin"))
        // Android normalizes Korean/English bottle to the one Bottle identity.
        assertEquals(1, priced.getValue("lagavulin").size)
        assertEquals("bottle", reviewServingKey(null, priced.getValue("lagavulin")[0].label))
        assertEquals("bottle", reviewServingKey(null, "  BOTTLE  "))
        assertEquals("ml:30", reviewServingKey(30, "잔"))
        assertEquals("ml:30", reviewServingKey(30, "Double"))
        assertEquals("ml:60", reviewServingKey(60, "잔"))
    }

    @Test fun failedReplacementNeverDeletesExistingPhoto() {
        val existing = MockPhoto("old", "https://server/old", MockPhotoKind.BAR_GALLERY)
        val replacement = MockPhoto("new", "content://new", MockPhotoKind.BAR_GALLERY)
        val calls = mutableListOf<String>()
        try {
            kotlinx.coroutines.runBlocking {
                replaceOwnerGallerySafely(
                    old = listOf(existing), now = listOf(replacement),
                    prepare = { photo -> calls += "prepare:${photo.photoId}"; photo.uri },
                    upload = { calls += "upload"; error("upload offline") },
                    delete = { calls += "delete:$it" },
                    reorder = { calls += "reorder" },
                )
            }
            fail("Upload must fail")
        } catch (_: IllegalStateException) {
            assertEquals(listOf("prepare:new", "upload"), calls)
        }
    }

    @Test fun replacementUploadPrecedesDestructiveDeleteAndReorder() {
        val existing = MockPhoto("old", "https://server/old", MockPhotoKind.BAR_GALLERY)
        val replacement = MockPhoto("new", "content://new", MockPhotoKind.BAR_GALLERY)
        val calls = mutableListOf<String>()
        kotlinx.coroutines.runBlocking {
            replaceOwnerGallerySafely(
                old = listOf(existing), now = listOf(replacement),
                prepare = { calls += "prepare"; it.uri },
                upload = { calls += "upload"; "server-new" },
                delete = { calls += "delete:$it" },
                reorder = { calls += "reorder:${it.joinToString(",")}" },
            )
        }
        assertEquals(listOf("prepare", "upload", "delete:old",
            "reorder:server-new"), calls)
    }

    @Test fun largeCompressedGalleryUsesSampledDecode() {
        assertEquals(4, sampledBitmapSize(8000, 6000))
        assertEquals(1, sampledBitmapSize(2048, 1536))
        assertEquals(2, sampledBitmapSize(4032, 3024))
    }
}
