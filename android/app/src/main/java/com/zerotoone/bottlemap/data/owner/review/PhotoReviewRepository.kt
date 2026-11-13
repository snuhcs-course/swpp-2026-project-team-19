package com.zerotoone.bottlemap.data.owner.review

import com.zerotoone.bottlemap.ui.owner.review.CatalogProduct
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import com.zerotoone.bottlemap.ui.owner.review.ReviewItem

/**
 * Data contract of the one-page photo-menu review screen.
 *
 * The screen and its ViewModel only talk to this interface. This step ships the mock
 * ([MockPhotoReviewRepository]); the server-backed implementation replaces it later
 * without touching the composables. Several behaviours here are NOT in the current API
 * spec yet (marked "Mock only" below); the real implementation must wait for the spec
 * change instead of inventing fields.
 */
interface PhotoReviewRepository {
    /** The review to show, mapped into the screen model. A saved draft is restored here. */
    suspend fun loadReview(): PhotoReviewState

    /** Catalog search for "아니에요" and "다른 위스키 검색" (spec 4.x catalog search). */
    suspend fun searchCatalog(query: String): List<CatalogProduct>

    /**
     * Exact-name rematch after the owner renames a line (decision 2).
     * Mock only: the agreed design runs this on the server at submit time.
     */
    suspend fun exactMatches(name: String): List<CatalogProduct>

    /**
     * Whether a product the owner picked conflicts with the age or edition read from the
     * photo (decision 7). Mock only: the server compares at submit time.
     */
    suspend fun needsOperatorCheck(item: ReviewItem, product: CatalogProduct): Boolean

    /** Saves the bar's default glass size (spec 3.7 `defaultPourMl`, 1..999). */
    suspend fun saveDefaultPour(ml: Int)

    /** Saves the in-progress review (decision 9). Mock only: no draft API exists yet. */
    suspend fun saveDraft(state: PhotoReviewState)

    /** Refresh a short-lived signed photo URL after expiry/403 (contract §5.4).
     * Mock scenarios do not have remote image URLs.
     */
    suspend fun refreshSourcePhotoUrl(itemId: String): String? = null

    /** Publishes reviewed decisions through the backend's single 8.1 submit. */
    suspend fun publish(state: PhotoReviewState)
}
