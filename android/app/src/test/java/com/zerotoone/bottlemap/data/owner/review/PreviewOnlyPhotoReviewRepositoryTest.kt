package com.zerotoone.bottlemap.data.owner.review

import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/**
 * I4-P14 contract guard: the v20 debug navigation uses the existing
 * interactive Mock review; it must not pretend to publish actual OCR data.
 */
class PreviewOnlyPhotoReviewRepositoryTest {
    @Test fun previewReadsExistingMockScenarioWithoutReplacingItsData() = runTest {
        val delegate = MockPhotoReviewRepository(MockPhotoReviewScenario.BASIC)
        val preview = PreviewOnlyPhotoReviewRepository(MockPhotoReviewScenario.BASIC, delegate)
        val state = preview.loadReview()
        assertEquals(MockPhotoReviewScenario.BASIC.initialState().items.map { it.id },
            state.items.map { it.id })
    }

    @Test fun previewCannotPublishEvenWhenAllReviewItemsAreReady() = runTest {
        val delegate = MockPhotoReviewRepository(MockPhotoReviewScenario.READY)
        val preview = PreviewOnlyPhotoReviewRepository(MockPhotoReviewScenario.READY, delegate)
        try {
            preview.publish(preview.loadReview())
            fail("Preview-only navigation must not publish fixture menu rows")
        } catch (expected: IllegalStateException) {
            assertTrue(expected.message.orEmpty().contains("Mock"))
        }
        assertNull(delegate.published)
    }
}
