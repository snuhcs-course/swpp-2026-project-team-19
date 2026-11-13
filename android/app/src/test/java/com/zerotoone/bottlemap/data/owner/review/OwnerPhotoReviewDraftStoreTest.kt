package com.zerotoone.bottlemap.data.owner.review

import android.util.Base64
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import com.zerotoone.bottlemap.ui.owner.review.ReviewItem
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment

/** Exact version / identity restore contracts for a process-kill proof draft. */
@RunWith(RobolectricTestRunner::class)
class OwnerPhotoReviewDraftStoreTest {
    private fun jwt(subject: String) = "header." + Base64.encodeToString(
        """{"sub":"$subject"}""".toByteArray(Charsets.UTF_8),
        Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING,
    ) + ".signature"

    private fun store(subject: String) = OwnerPhotoReviewDraftStore(
        RuntimeEnvironment.getApplication(), accessToken = { jwt(subject) },
    )

    @Test fun draftSurvivesNewRepositoryInstanceButNotOtherOwner() = runTest {
        val id = "review-draft-test-1111"
        val first = store("owner-a")
        val state = PhotoReviewState(items = listOf(
            ReviewItem(id = "item-1", name = "위스키 수정",
                price = 15000.0, sourcePhotoUrl = "https://signed.example/short-lived",
                draftPriceText = "1500", expanded = true),
        ))
        first.save(id,3,state)
        val afterProcessDeath = store("owner-a").load(id,3,listOf("item-1"))
        assertNotNull(afterProcessDeath)
        assertEquals("위스키 수정",afterProcessDeath!!.items.single().name)
        assertEquals("1500",afterProcessDeath.items.single().draftPriceText)
        assertNull(afterProcessDeath.items.single().sourcePhotoUrl)
        assertNull(store("owner-b").load(id,3,listOf("item-1")))
        first.clear(id)
        assertNull(store("owner-a").load(id,3,listOf("item-1")))
    }

    @Test fun staleReviewVersionOrExtractedIdsNeverReusesOwnerEdits() = runTest {
        val id = "review-draft-test-2222"
        val store = store("owner-c")
        store.save(id,1,PhotoReviewState(items=listOf(ReviewItem(id="old-item",name="old"))))
        assertNull(store.load(id,2,listOf("old-item")))
        assertNull(store.load(id,1,listOf("old-item")))
        store.save(id,2,PhotoReviewState(items=listOf(ReviewItem(id="old-item",name="old"))))
        assertNull(store.load(id,2,listOf("different-item")))
        assertNull(store.load(id,2,listOf("old-item")))
    }
}
