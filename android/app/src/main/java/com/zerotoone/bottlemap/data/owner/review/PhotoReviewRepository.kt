package com.zerotoone.bottlemap.data.owner.review

import com.zerotoone.bottlemap.ui.owner.review.CatalogProduct
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import com.zerotoone.bottlemap.ui.owner.review.ReviewItem
import com.zerotoone.bottlemap.ui.owner.review.ReviewPriceCandidate

/**
 * Data contract of the one-page photo-menu review screen.
 *
 * The screen and ViewModel use this interface. LivePhotoReviewRepository
 * implements the approved #164 server review-and-apply contract; development
 * fixtures are isolated in src/debug and never replace real Owner review.
 * Live uses PR #171's server draft/version API; Mock only uses in-memory data.
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

    /** Bar-local saved price options keyed by the CURRENT corrected menu name.
     * Default has no saved menu data; the Live adapter queries its owner state.
     */
    fun existingUnlinkedServingPrices(name: String): List<ReviewPriceCandidate> = emptyList()

    /**
     * Whether structured OCR age/edition contradicts the selected candidate.
     * A conflict is published bar-locally, not linked under the wrong product.
     */
    suspend fun needsOperatorCheck(item: ReviewItem, product: CatalogProduct): Boolean

    /** Saves the bar's default glass size (spec 3.7 `defaultPourMl`, 1..999). */
    suspend fun saveDefaultPour(ml: Int)

    /** Version-checked remote draft; errors must be visible before leaving. */
    suspend fun saveDraft(state: PhotoReviewState)

    /** Always check the server's latest draftVersion before the atomic publication. */
    suspend fun flushBeforePublish(state: PhotoReviewState) = saveDraft(state)

    /** True when an unsynced device draft conflicts with a newer remote draft. */
    fun hasPendingDraftConflict(): Boolean = false

    /** Explicit choice: discard the protected local copy and reload the remote draft. */
    suspend fun chooseServerDraft() {
        error("이 검수 저장소에서는 서버 초안 선택을 지원하지 않아요.")
    }

    /** Enter protected device-only conflict editing; no remote PUT is allowed. */
    suspend fun startEditingLocalDraft(): PhotoReviewState {
        error("이 검수 저장소에서는 충돌 초안 편집을 지원하지 않아요.")
    }

    /** Explicit choice: overwrite the just-reviewed remote CAS with a compatible local copy. */
    suspend fun chooseLocalDraft() {
        error("이 검수 저장소에서는 이 기기 초안 선택을 지원하지 않아요.")
    }

    /** True if the device-only copy exceeds §5.9's server 256 KiB limit. */
    fun hasOversizedPendingDraft(): Boolean = false

    /** True if an account-scoped device copy is loaded but not yet server-acknowledged. */
    fun hasPendingLocalDraft(): Boolean = false

    /** Optional message when a server draft needs operator review/reconciliation. */
    fun consumeDraftNotice(): String? = null

    /** Refresh a short-lived signed photo URL after expiry/403 (contract §5.4).
     * Mock scenarios do not have remote image URLs.
     */
    suspend fun refreshSourcePhotoUrl(itemId: String): String? = null

    /** True only for this import's applied state; false only if review can safely resume. */
    suspend fun checkPublishedStatus(): Boolean? = null

    /** Publishes reviewed decisions through the backend's single 8.1 submit. */
    suspend fun publish(state: PhotoReviewState)
}
