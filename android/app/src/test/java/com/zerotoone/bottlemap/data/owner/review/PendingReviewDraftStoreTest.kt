package com.zerotoone.bottlemap.data.owner.review

import android.content.Context
import android.util.Base64
import com.zerotoone.bottlemap.network.ReviewDraftDto
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import com.zerotoone.bottlemap.ui.owner.review.ReviewItem
import java.io.File
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class PendingReviewDraftStoreTest {
    private val context: Context = RuntimeEnvironment.getApplication()
    private val folder = File(context.noBackupFilesDir, "pending-owner-review-drafts")

    private fun jwt(subject: String) = "header." + Base64.encodeToString(
        """{"sub":"$subject"}""".toByteArray(),
        Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP,
    ) + ".signature"

    @After fun clean() { folder.deleteRecursively() }

    @Test fun failedNetworkDraftSurvivesRecreationButCannotLeakToOtherAccountOrImport() = runBlocking {
        val original = PhotoReviewState(items = listOf(ReviewItem(
            id = "ocr-1", name = "업주 수정 이름", draftPriceText = "15000",
            volume = Double.NaN,
        )))
        val pending = PendingReviewDraftStore.Envelope(
            reviewVersion = 7, expectedDraftVersion = 3,
            itemIds = listOf("ocr-1"), content = ServerReviewDraftCodec.encode(original),
        )
        val ownerA = PendingReviewDraftStore(context) { jwt("owner-a") }
        ownerA.write("import-1", pending)
        val recreated = PendingReviewDraftStore(context) { jwt("owner-a") }
        val ownerB = PendingReviewDraftStore(context) { jwt("owner-b") }
        assertNull(ownerB.read("import-1"))
        assertNull(recreated.read("import-2"))
        val restored = requireNotNull(recreated.read("import-1"))
        assertTrue(restored.canReplay(ReviewDraftDto(
            3, 7, "2026-11-15T00:00:00Z", emptyMap()), 7))
        assertFalse(restored.canReplay(ReviewDraftDto(
            4, 7, "2026-11-15T00:00:00Z", emptyMap()), 7))
        assertFalse(restored.canReplay(ReviewDraftDto(
            3, 8, "2026-11-15T00:00:00Z", emptyMap()), 8))
        val decoded = requireNotNull(ServerReviewDraftCodec.decode(ReviewDraftDto(
            3, 7, "2026-11-15T00:00:00Z", restored.content,
        )))
        assertEquals("업주 수정 이름", decoded.items.single().name)
        assertEquals("15000", decoded.items.single().draftPriceText)
        ownerB.clear("import-1")
        assertNotNull(recreated.read("import-1"))
        recreated.clear("import-1")
        assertNull(recreated.read("import-1"))
    }

    @Test fun cannotWriteUnscopedDraftWithoutCurrentAuthSubject() = runBlocking {
        val unauthenticated = PendingReviewDraftStore(context) { null }
        try {
            unauthenticated.write("import-1", PendingReviewDraftStore.Envelope(
                1, 0, emptyList(), emptyMap(),
            ))
            fail("Draft must not be written without an authenticated account scope")
        } catch (_: IllegalStateException) {
            assertTrue(folder.listFiles()?.isEmpty() != false)
        }
    }
}
