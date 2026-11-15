package com.zerotoone.bottlemap.data.owner.review

import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState

/**
 * I4-P14 Mock-approval bridge for the actual photo review navigation route in debug APKs.
 *
 * This does NOT interpret uploaded photos, update a backend reviewVersion, write
 * review decisions, or publish real menu items. The approved API integration is
 * a separate task; silently publishing Mock fixture data would be unsafe.
 *
 * All UI interactions before publication are delegated to the existing Mock
 * repository, preserving the current v20 layout and its scenarios unmodified.
 */
class PreviewOnlyPhotoReviewRepository(
    scenario: MockPhotoReviewScenario = MockPhotoReviewScenario.BASIC,
    private val mock: MockPhotoReviewRepository = MockPhotoReviewRepository(scenario),
) : PhotoReviewRepository by mock {
    override suspend fun publish(state: PhotoReviewState) {
        throw IllegalStateException(
            "현재 메뉴 검수는 Mock 시안입니다. 실제 메뉴는 게시되지 않았어요."
        )
    }
}
