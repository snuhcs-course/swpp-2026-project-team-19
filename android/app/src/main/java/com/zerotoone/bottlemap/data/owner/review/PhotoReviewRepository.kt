package com.zerotoone.bottlemap.data.owner.review

import com.zerotoone.bottlemap.ui.owner.review.CatalogProduct
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import com.zerotoone.bottlemap.ui.owner.review.ReviewItem

/**
 * Data contract of the one-page photo-menu review screen.
 *
 * The screen and ViewModel use this interface. LivePhotoReviewRepository
 * implements the approved #164 server review-and-apply contract; development
 * fixtures are isolated in src/debug and never replace real Owner review.
 * Local draft persistence is device-only; no server draft API is assumed.
 */
interface PhotoReviewRepository {
    /** The review to show, mapped into the screen model. A saved draft is restored here. */
    suspend fun loadReview(): PhotoReviewState

    /** Catalog search for "아니에요" and "다른 위스키 검색" (spec 4.x catalog search). */
    suspend fun searchCatalog(query: String): List<CatalogProduct>

    /**
     * Exact-name rematch after the owner renames a line (decision 2).
     * Client-side search/reconfirmation is advisory; the server remains authoritative.
     */
    suspend fun exactMatches(name: String): List<CatalogProduct>

    /**
     * Whether structured OCR age/edition contradicts the selected candidate.
     * A conflict is published bar-locally, not linked under the wrong product.
     */
    suspend fun needsOperatorCheck(item: ReviewItem, product: CatalogProduct): Boolean

    /** Saves the bar's default glass size (spec 3.7 `defaultPourMl`, 1..999). */
    suspend fun saveDefaultPour(ml: Int)

    /** Saves the on-device in-progress review; no Backend A5 draft API exists yet. */
    suspend fun saveDraft(state: PhotoReviewState)

    /** Refresh a short-lived signed photo URL after expiry/403 (contract §5.4).
     * Mock scenarios do not have remote image URLs.
     */
    suspend fun refreshSourcePhotoUrl(itemId: String): String? = null

    /** True only for this import's applied state; false only if review can safely resume. */
    suspend fun checkPublishedStatus(): Boolean? = null

    /** Publishes reviewed decisions through the backend's single 8.1 submit. */
    suspend fun publish(state: PhotoReviewState)
}
