package com.zerotoone.bottlemap.data.owner.review

import android.content.Context
import android.util.Base64
import androidx.test.core.app.ApplicationProvider
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import com.zerotoone.bottlemap.ui.owner.review.ReviewItem
import java.io.File
import java.security.MessageDigest
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class LegacyReviewDraftReaderTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()
    private val folder = File(context.noBackupFilesDir, "owner-review-drafts")

    private fun jwt(subject: String) = "header." + Base64.encodeToString(
        """{"sub":"$subject"}""".toByteArray(),
        Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP,
    ) + ".signature"

    private fun file(subject: String, importId: String): File {
        val hash = MessageDigest.getInstance("SHA-256")
            .digest("$subject:$importId".toByteArray())
            .joinToString("") { "%02x".format(it) }
        return File(folder, "$hash.json")
    }

    @After fun clear() { folder.deleteRecursively() }

    @Test fun readsOnlyMatchingAccountImportAndReviewVersionAndDeletesAfterMigration() = runBlocking {
        folder.mkdirs()
        val old = LegacyReviewDraftReader.Envelope(
            reviewVersion = 3, itemIds = listOf("ocr-1"),
            state = PhotoReviewState(items = listOf(
                ReviewItem(id="ocr-1",name="수정한 이름",draftPriceText="15000"),
            )),
        )
        val json = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
            .adapter(LegacyReviewDraftReader.Envelope::class.java).toJson(old)
        file("owner-a", "import-a").writeText(json)

        val a = LegacyReviewDraftReader(context) { jwt("owner-a") }
        val b = LegacyReviewDraftReader(context) { jwt("owner-b") }
        assertNull(b.read("import-a", 3, listOf("ocr-1")))
        assertNull(a.read("import-b", 3, listOf("ocr-1")))
        assertNull(a.read("import-a", 4, listOf("ocr-1")))
        assertEquals("15000", a.read("import-a", 3, listOf("ocr-1"))
            ?.items?.single()?.draftPriceText)
        assertTrue(file("owner-a","import-a").isFile)
        a.clear("import-a")
        assertFalse(file("owner-a","import-a").exists())
    }
}
