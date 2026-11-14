package com.zerotoone.bottlemap.data.owner.review

import android.content.Context

import com.zerotoone.bottlemap.data.OwnerRepository
import com.zerotoone.bottlemap.data.owner.MockImportStatus
import com.zerotoone.bottlemap.data.owner.MockOwnerLoadState
import com.zerotoone.bottlemap.data.owner.MockOwnerSnapshot
import com.zerotoone.bottlemap.data.owner.ownerExistingUnlinkedOptions
import com.zerotoone.bottlemap.data.owner.isBottleServingLabel
import com.zerotoone.bottlemap.data.owner.servingIdentityKey
import com.zerotoone.bottlemap.network.MenuImportStatusDto
import com.zerotoone.bottlemap.ui.owner.OwnerMockViewModel
import com.zerotoone.bottlemap.ui.owner.review.CatalogProduct
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewRules
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import com.zerotoone.bottlemap.ui.owner.review.ReviewItem
import com.zerotoone.bottlemap.ui.owner.review.ReviewPriceCandidate
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.text.Normalizer

/**
 * Production data adapter for the existing one-page v20 photo-review UI.
 *
 * The backend contract uses one atomic review-and-apply request (section 8);
 * it has NO intermediate draft endpoint. Until that is agreed, edits remain
 * in this navigation ViewModel's memory and the existing Owner repository
 * stages validated decisions locally just before the one final submit.
 *
 * Real OCR, reviewed product IDs and version are always loaded from the
 * owner-authenticated server; never substitute the BASIC demo scenario.
 */
/** Only GET for this exact import may establish that publishing already completed. */
class ReviewAlreadyAppliedException : IllegalStateException("이미 게시된 메뉴판 작업이에요.")

/** Typed error for preflight reviewVersion mismatches (distinct from field validation). */
class ReviewVersionConflictException : IllegalStateException("검수 버전이 달라졌어요. 다시 불러와 확인해 주세요.")

internal fun reviewerCandidateConflicts(
    extractedAge: Int?, extractedEdition: String?,
    candidateAge: Int?, candidateEdition: String?,
): Boolean {
    if (extractedAge != null && candidateAge != null &&
        extractedAge != candidateAge) return true
    val original = extractedEdition?.trim()?.takeIf { it.isNotBlank() }
    val selected = candidateEdition?.trim()?.takeIf { it.isNotBlank() }
    return original != null && selected != null &&
        Normalizer.normalize(original, Normalizer.Form.NFKC).lowercase() !=
        Normalizer.normalize(selected, Normalizer.Form.NFKC).lowercase()
}

class LivePhotoReviewRepository(
    private val owner: OwnerMockViewModel,
    private val importId: String?,
    context: Context,
    private val remote: OwnerRepository = OwnerRepository(),
) : PhotoReviewRepository {
    private var loaded: MenuImportStatusDto? = null
    private var activeImportId: String? = null
    private var inMemoryDraft: PhotoReviewState? = null
    private val draftStore = OwnerPhotoReviewDraftStore(context)
    private val draftMutex = Mutex()
    private var published = false

    private fun snapshot(): MockOwnerSnapshot = when (val current = owner.state.value) {
        is MockOwnerLoadState.Ready -> current.snapshot
        is MockOwnerLoadState.Empty -> current.snapshot
        else -> error("매장 정보를 불러오는 중이에요. 다시 시도해 주세요.")
    }

    private suspend fun resolveImportId(): String {
        importId?.let { return it }
        val current = owner.state.first { it !is MockOwnerLoadState.Loading }
        val snap = when (current) {
            is MockOwnerLoadState.Ready -> current.snapshot
            is MockOwnerLoadState.Empty -> current.snapshot
            is MockOwnerLoadState.Error -> error(current.message)
            MockOwnerLoadState.Loading -> error("매장 정보를 불러오는 중이에요.")
        }
        val barId = snap.selectedBarId ?: snap.bars.firstOrNull()?.barId
        return snap.imports.lastOrNull {
            it.barId == barId && it.status == MockImportStatus.READY_FOR_REVIEW
        }?.menuImportId ?: error("검수할 메뉴판 작업이 없어요. 메뉴 관리에서 다시 선택해 주세요.")
    }

    override suspend fun loadReview(): PhotoReviewState {
        val id = resolveImportId()
        activeImportId = id
        val status = owner.pollPhotoImportLive(id)
        val response = remote.getMenuImport(id)
        if (isAppliedReviewImport(response, id)) {
            finishPublishedDraft(id)
            throw ReviewAlreadyAppliedException()
        }
        require(status == MockImportStatus.READY_FOR_REVIEW) {
            "메뉴판 분석이 아직 완료되지 않았어요."
        }
        require(response.menuImportId == id &&
            response.status == "ready_for_review" && response.reviewVersion != null) {
            "검수할 수 없는 메뉴판 작업이에요."
        }
        val current = snapshot()
        require(current.imports.any {
            it.menuImportId == id && it.reviewVersion == response.reviewVersion
        }) { "검수 버전이 변경됐어요. 다시 불러와 주세요." }
        val state = mapServerPhotoReview(response, current)
        val local = draftStore.load(id, requireNotNull(response.reviewVersion),
            state.items.map { it.id })
        // A draft created before the per-product grouping migration has the
        // same raw OCR IDs but incompatible card semantics. Never restore that
        // obsolete ungrouped state over a newly grouped, price-conflicted card.
        // Compatible drafts retain all owner edits after process recreation.
        fun compatible(candidate: PhotoReviewState?): Boolean =
            candidate != null &&
                candidate.items.map { it.id } == state.items.map { it.id } &&
                candidate.items.zip(state.items).all { (saved, fresh) ->
                    if (saved.manuallySplitGroup)
                        (fresh.mergedInto != null || fresh.mergeSources.isNotEmpty())
                    else saved.mergedInto == fresh.mergedInto &&
                        saved.volumeChoices == fresh.volumeChoices
                }
        val chosen = inMemoryDraft.takeIf {
            loaded?.reviewVersion == response.reviewVersion && compatible(it)
        } ?: local.takeIf(::compatible) ?: state
        // Signed URLs expire, and source observations belong to the server.
        // Restore only owner edits; rebind fresh data to the current response.
        val currentItems = state.items.associateBy { it.id }
        // Restoring a corrected name must use *that* name's saved row.
        // The fresh OCR name could refer to a different menu item and would
        // otherwise erase the owner's unresolved saved-versus-photo conflict.
        loaded = response
        val restored = chosen.copy(items = chosen.items.map { old ->
            val fresh = currentItems.getValue(old.id)
            val savedPrices = if (old.linkedProductId == null && old.name.isNotBlank())
                existingUnlinkedServingPrices(old.name)
            else fresh.priceCandidates.filter { it.existing }
            val previousSaved = old.priceCandidates.filter { it.existing }
            old.copy(sourcePhotoUrl = fresh.sourcePhotoUrl, sourceBox = fresh.sourceBox,
                raw = fresh.raw, recognizedOffers = fresh.recognizedOffers,
                // Candidate prices and OCR identities always come from the current
                // server snapshot; a saved draft must not mask a price conflict.
                existingPriceByProductId = fresh.existingPriceByProductId,
                existingServingPricesByProductId = fresh.existingServingPricesByProductId,
                mergeSources = if (old.manuallySplitGroup) old.mergeSources
                    else fresh.mergeSources,
                // Existing prices are refreshed from the server; the OCR
                // candidates are retained even after a late product relink.
                priceCandidates = old.priceCandidates.filterNot { it.existing } + savedPrices,
                chosenServingPrices = if (previousSaved == savedPrices &&
                    old.existingServingPricesByProductId ==
                    fresh.existingServingPricesByProductId) old.chosenServingPrices
                    else emptyMap(),
                // A removed OCR primary must not regain its extractedOptionId
                // when an owner later adds a manual replacement with null ID.
                primarySourceOptionId = old.primarySourceOptionId)
        }, modal = null, typingSnapshots = emptyMap())
        loaded = response
        return restored
    }

    override suspend fun searchCatalog(query: String): List<CatalogProduct> {
        // The existing publish adapter validates selected IDs against its
        // current catalog snapshot, so keep it in sync with the server search.
        return owner.searchCatalogLive(query).filter { it.isActive }
            .map { CatalogProduct(it.productId, it.displayName) }
    }

    override suspend fun exactMatches(name: String): List<CatalogProduct> {
        val candidates = owner.searchCatalogLive(name)
        val key = normalized(name)
        return candidates
            .filter { it.isActive && (
                normalized(it.displayName) == key ||
                    normalized(it.matchedAlias.orEmpty()) == key) }
            .map { CatalogProduct(it.productId, it.displayName) }
            .distinctBy { it.productId }
    }

    override fun existingUnlinkedServingPrices(name: String): List<ReviewPriceCandidate> {
        val barId = loaded?.barId ?: error("검수 정보를 먼저 불러와 주세요.")
        return ownerExistingUnlinkedOptions(snapshot(), barId, name).map { saved ->
            ReviewPriceCandidate(
                servingKey = servingIdentityKey(saved.pourMl, saved.label),
                volumeMl = saved.pourMl,
                bottle = isBottleServingLabel(saved.label),
                label = saved.label,
                priceKrw = saved.priceKrw,
                existing = true,
            )
        }
    }

    /** Contract §8.7 assigns attribute_conflict to the server. */
    override suspend fun needsOperatorCheck(
        item: ReviewItem, product: CatalogProduct,
    ): Boolean = false

    override suspend fun saveDefaultPour(ml: Int) {
        require(ml in 1..999)
        val response = loaded ?: error("검수 정보를 먼저 불러와 주세요.")
        val bar = snapshot().bars.firstOrNull { it.barId == response.barId }
            ?: error("매장 정보를 불러오지 못했어요.")
        owner.saveBarLive(bar.copy(defaultPourMl = ml))
    }

    override suspend fun refreshSourcePhotoUrl(itemId: String): String? {
        val importId = activeImportId ?: return null
        val version = loaded?.reviewVersion ?: return null
        val current = remote.getMenuImport(importId)
        require(current.reviewVersion == version) {
            "검수 버전이 변경됐어요. 다시 검수 정보를 불러와 주세요."
        }
        return current.images.firstOrNull { image ->
            image.items.any { it.extractedItemId == itemId }
        }?.imageUrl
    }

    override suspend fun checkPublishedStatus(): Boolean? {
        val id = activeImportId ?: return null
        val current = remote.getMenuImport(id)
        if (current.menuImportId != id) return null
        if (isAppliedReviewImport(current, id)) {
            runCatching { owner.pollPhotoImportLive(id) }
            finishPublishedDraft(id)
            return true
        }
        return if (current.status == "ready_for_review" &&
            current.reviewVersion == loaded?.reviewVersion) false else null
    }

    /** Durable device-local draft; never claims a server-side write. */
    override suspend fun saveDraft(state: PhotoReviewState) {
        val id = activeImportId ?: return
        val version = loaded?.reviewVersion ?: return
        draftMutex.withLock {
            if (!published) {
                draftStore.save(id, version, state)
                inMemoryDraft = state
            }
        }
    }

    /** A committed server review must never be reported as a failed publish
     * just because the HTTP response or local draft deletion was interrupted.
     */
    private suspend fun finishPublishedDraft(id: String) {
        draftMutex.withLock {
            published = true
            // Local persistence is best effort once the server has committed.
            runCatching { draftStore.clear(id) }
            inMemoryDraft = null
        }
    }

    override suspend fun publish(state: PhotoReviewState) {
        require(PhotoReviewRules.stats(state).canPublish) {
            "확인이 필요한 메뉴를 먼저 검수해 주세요."
        }
        val original = loaded ?: error("검수 데이터를 먼저 불러와 주세요.")
        val id = activeImportId ?: error("검수 작업을 먼저 불러와 주세요.")
        val latest = remote.getMenuImport(id)
        if (isAppliedReviewImport(latest, id)) {
            // If the prior request committed but its response was lost, the
            // same import is already customer-visible. Do not keep a false
            // failed Draft or attempt an unrelated second publication.
            runCatching { owner.pollPhotoImportLive(id) }
            finishPublishedDraft(id)
            return
        }
        if (latest.reviewVersion != original.reviewVersion)
            throw ReviewVersionConflictException()
        require(latest.menuImportId == id && latest.status == "ready_for_review") {
            "검수할 수 없는 메뉴판 작업이에요."
        }
        val rawItems = latest.images.flatMap { it.items }
        val cards = state.items.associateBy { it.id }
        require(cards.size == rawItems.size &&
            rawItems.all { cards.containsKey(it.extractedItemId) }) {
            "검수 항목이 서버 내용과 달라졌어요. 다시 불러와 주세요."
        }
        // Unlinked whisky and non-whisky lines are bar-only. PR #164 does not
        // require a catalog brand, so publishing must not depend on brand search
        // or accidentally create a global brand before review-and-apply.
        val brands = emptyMap<String, String>()
        // Preflight the COMPLETE batch before mutating local decisions. This
        // prevents unsupported option operations from being silently dropped.
        val decisions = rawItems.map { item ->
            val card = cards.getValue(item.extractedItemId)
            item.extractedItemId to mapConfirmedReviewDecision(
                card, item, state.defaultPour, brands,
            )
        }
        val version = requireNotNull(original.reviewVersion)
        decisions.forEach { (itemId, decision) ->
            owner.review(id, itemId, version, decision)
        }
        try {
            // The server's #164 endpoint is atomic and idempotent per import.
            owner.publishPhotoImportLive(id, version)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Exception) {
            // The server may have committed before the client lost its
            // response. Confirm THIS import's applied status before deciding
            // that a retry failed; do not invent a successful publication.
            val observed = runCatching { remote.getMenuImport(id) }.getOrNull()
            if (observed == null || !isAppliedReviewImport(observed, id)) throw error
            runCatching { owner.pollPhotoImportLive(id) }
        }
        finishPublishedDraft(id)
    }

    private fun normalized(value: String): String =
        Normalizer.normalize(value.trim(), Normalizer.Form.NFKC).lowercase()
}
