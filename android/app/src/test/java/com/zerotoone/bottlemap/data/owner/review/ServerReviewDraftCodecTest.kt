package com.zerotoone.bottlemap.data.owner.review

import com.zerotoone.bottlemap.network.ReviewDraftDto
import com.zerotoone.bottlemap.ui.owner.review.ClassificationSnapshot
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import com.zerotoone.bottlemap.ui.owner.review.PriceChoice
import com.zerotoone.bottlemap.ui.owner.review.ReviewItem
import com.zerotoone.bottlemap.ui.owner.review.ReviewItemType
import com.zerotoone.bottlemap.ui.owner.review.ReviewMatch
import com.zerotoone.bottlemap.ui.owner.review.ReviewOption
import com.zerotoone.bottlemap.ui.owner.review.VolumeSource
import org.junit.Assert.*
import org.junit.Test

class ServerReviewDraftCodecTest {
    @Test fun roundTripPreservesUnfinishedEditsWithoutSignedMediaOrNaN() {
        val item = ReviewItem(
            id = "ocr-1", name = "수정한 위스키", price = 15000.0,
            volume = Double.NaN, draftPriceText = "145",
            priceChoice = PriceChoice.MANUAL,
            reviewNameDraft = "수정 중", nameEditMode = true,
            sourcePhotoUrl = "https://signed.example/secret?token=abc",
            sourceBox = listOf(1,2,3,4),
            raw = "OCR raw line",
            options = listOf(ReviewOption(volume = Double.NaN, price = 20000.0)),
            classificationSnapshot = ClassificationSnapshot(
                type = ReviewItemType.OTHER,
                volume = Double.NaN, volumeSource = VolumeSource.PHOTO,
                bottle = false, primaryHasOption = true,
                options = listOf(ReviewOption(volume = Double.NaN)),
                match = ReviewMatch.NEW, matchConfirmed = false,
                nameSaved = false, newConfirmed = false,
                linkedProductId = null, linkedProductName = null,
                newProductName = null, candidates = emptyList(),
                rawOptionEdits = emptyMap(), primaryPrice = Double.NaN,
            ),
        )
        val data = ServerReviewDraftCodec.encode(PhotoReviewState(items = listOf(item)))
        val saved = ReviewDraftDto(4, 3, "2026-11-15T00:00:00Z", data)
        val restored = requireNotNull(ServerReviewDraftCodec.decode(saved))
        assertEquals("수정 중", restored.items.single().reviewNameDraft)
        assertEquals("145", restored.items.single().draftPriceText)
        assertEquals(PriceChoice.MANUAL, restored.items.single().priceChoice)
        assertEquals(0.0, restored.items.single().volume, 0.0)
        assertEquals(0.0, restored.items.single().options.single().volume, 0.0)
        assertEquals(0.0, restored.items.single().classificationSnapshot!!.volume, 0.0)
        assertNull(restored.items.single().classificationSnapshot!!.primaryPrice)
        val encoded = data.toString()
        assertFalse(encoded.contains("token=abc"))
        assertFalse(encoded.contains("OCR raw line"))
        assertFalse(encoded.contains("NaN"))
        assertEquals("ocr-1",
            (data["itemDecisions"] as List<*>).first().let {
                (it as Map<*, *>)["extractedItemId"]
            })
    }

    @Test fun anotherDevicesAndroidDraftRestoresReviewItemEdits() {
        val line = ReviewItem(
            id = "line-1", name = "글렌피딕 12",
            linkedProductId = "catalog-1",
            chosenServingPrices = mapOf("ml:30" to 12000),
            manuallySplitGroup = true, draftVolumeText = "6",
            expanded = true,
        )
        val content = ServerReviewDraftCodec.encode(PhotoReviewState(items = listOf(line)))
        val fromServer = ReviewDraftDto(7, 3, "2026-11-15T00:00:00Z", content)
        val copy = requireNotNull(ServerReviewDraftCodec.decode(fromServer)).items.single()
        assertEquals(mapOf("ml:30" to 12000), copy.chosenServingPrices)
        assertTrue(copy.manuallySplitGroup)
        assertTrue(copy.expanded)
        assertEquals("6", copy.draftVolumeText)
    }

    @Test fun foreignClientDraftCannotBeMistakenForEmptyAndroidDraft() {
        val foreign = ReviewDraftDto(5, 3, "2026-11-15T00:00:00Z",
            mapOf("itemDecisions" to listOf(mapOf("extractedItemId" to "ocr-1"))))
        assertNull(ServerReviewDraftCodec.decode(foreign))
    }

    @Test fun oversizedDraftRejectedBeforeNetworkWrite() {
        val huge = PhotoReviewState(items = listOf(ReviewItem(
            id = "line-1", name = "A",
            draftPriceText = "9".repeat(270_000),
        )))
        val ex = runCatching { ServerReviewDraftCodec.encode(huge) }.exceptionOrNull()
        assertNotNull(ex)
        assertTrue(ex!!.message.orEmpty().contains("256KB"))
    }
}
