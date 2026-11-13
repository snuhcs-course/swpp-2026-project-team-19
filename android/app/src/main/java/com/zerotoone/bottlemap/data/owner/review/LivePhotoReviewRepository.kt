package com.zerotoone.bottlemap.data.owner.review

import com.zerotoone.bottlemap.data.OwnerRepository
import com.zerotoone.bottlemap.data.owner.MockImportStatus
import com.zerotoone.bottlemap.data.owner.MockOwnerLoadState
import com.zerotoone.bottlemap.data.owner.MockOwnerSnapshot
import com.zerotoone.bottlemap.network.MenuImportStatusDto
import com.zerotoone.bottlemap.ui.owner.OwnerMockViewModel
import com.zerotoone.bottlemap.ui.owner.review.CatalogProduct
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewRules
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import com.zerotoone.bottlemap.ui.owner.review.ReviewItem
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.first
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
class LivePhotoReviewRepository(
    private val owner: OwnerMockViewModel,
    private val importId: String?,
    private val remote: OwnerRepository = OwnerRepository(),
) : PhotoReviewRepository {
    private var loaded: MenuImportStatusDto? = null
    private var activeImportId: String? = null
    private var inMemoryDraft: PhotoReviewState? = null

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
        require(status == MockImportStatus.READY_FOR_REVIEW) {
            "메뉴판 분석이 아직 완료되지 않았어요."
        }
        val response = remote.getMenuImport(id)
        require(response.menuImportId == id &&
            response.status == "ready_for_review" && response.reviewVersion != null) {
            "검수할 수 없는 메뉴판 작업이에요."
        }
        val current = snapshot()
        require(current.imports.any {
            it.menuImportId == id && it.reviewVersion == response.reviewVersion
        }) { "검수 버전이 변경됐어요. 다시 불러와 주세요." }
        val state = mapServerPhotoReview(response, current)
        val restored = inMemoryDraft.takeIf {
            loaded?.reviewVersion == response.reviewVersion &&
                it?.items?.map { item -> item.id } == state.items.map { item -> item.id }
        } ?: state
        loaded = response
        return restored
    }

    override suspend fun searchCatalog(query: String): List<CatalogProduct> {
        // The existing publish adapter validates selected IDs against its
        // current catalog snapshot, so keep it in sync with the server search.
        owner.searchCatalogLive(query)
        return remote.searchCatalogProducts(query).filter { it.isActive }
            .map { CatalogProduct(it.productId, it.displayName) }
    }

    override suspend fun exactMatches(name: String): List<CatalogProduct> {
        owner.searchCatalogLive(name)
        val key = normalized(name)
        return remote.searchCatalogProducts(name)
            .filter { it.isActive && (
                normalized(it.displayName) == key ||
                    normalized(it.matchedAlias.orEmpty()) == key) }
            .map { CatalogProduct(it.productId, it.displayName) }
            .distinctBy { it.productId }
    }

    /** The server validates age and edition when review-and-apply commits. */
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

    /** This is an in-memory draft only, not a fake server-side save. */
    override suspend fun saveDraft(state: PhotoReviewState) {
        inMemoryDraft = state
    }

    override suspend fun publish(state: PhotoReviewState) {
        require(PhotoReviewRules.stats(state).canPublish) {
            "확인이 필요한 메뉴를 먼저 검수해 주세요."
        }
        val original = loaded ?: error("검수 데이터를 먼저 불러와 주세요.")
        val id = activeImportId ?: error("검수 작업을 먼저 불러와 주세요.")
        val latest = remote.getMenuImport(id)
        require(latest.status == "ready_for_review" &&
            latest.reviewVersion == original.reviewVersion) {
            "검수 버전이 달라졌어요. 다시 불러와 확인해 주세요."
        }
        val rawItems = latest.images.flatMap { it.items }
        val cards = state.items.associateBy { it.id }
        require(cards.size == rawItems.size &&
            rawItems.all { cards.containsKey(it.extractedItemId) }) {
            "검수 항목이 서버 내용과 달라졌어요. 다시 불러와 주세요."
        }
        val brands = snapshot().brands.associate {
            normalized(it.name) to it.brandId
        }.toMutableMap()
        // Resolve an existing catalog brand by exact canonical name before a
        // create_product request. Do not invent brand IDs or new API fields.
        for (item in rawItems) {
            val card = cards.getValue(item.extractedItemId)
            if (card.excluded || card.linkedProductId != null) continue
            val brand = (item.extractedBrandName ?: item.newProductDraft?.brandText)
                ?.trim().orEmpty()
            if (brand.isNotBlank() && normalized(brand) !in brands) {
                owner.searchCatalogBrandsLive(brand)
                val match = snapshot().brands.firstOrNull {
                    normalized(it.name) == normalized(brand)
                }
                if (match != null) brands[normalized(brand)] = match.brandId
            }
        }
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
            // Existing tested production path preserves add-only semantics,
            // discounts, and correct post-commit success/error boundaries.
            owner.publishPhotoImportLive(id, version)
        } catch (cancelled: CancellationException) {
            throw cancelled
        }
        inMemoryDraft = null
    }

    private fun normalized(value: String): String =
        Normalizer.normalize(value.trim(), Normalizer.Form.NFKC).lowercase()
}
