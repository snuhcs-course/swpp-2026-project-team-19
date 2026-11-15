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
import com.zerotoone.bottlemap.network.ReviewDraftSaveRequestDto
import com.zerotoone.bottlemap.network.ReviewDraftDto
import com.zerotoone.bottlemap.network.BottleMapApiException
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
 * Draft edits use server §5.9 (PR #171) with compare-and-swap draftVersion.
 * Only final publishing uses the separate atomic review-and-apply (§8).
 * Pre-#171 local drafts are imported only once. New device-local writes
 * are exclusively a failure-safe pending copy under §5.9, never the source
 * of truth and never replayed over a newer server draftVersion.
 *
 * Real OCR, reviewed product IDs and version are always loaded from the
 * owner-authenticated server; never substitute the BASIC demo scenario.
 */
/** Only GET for this exact import may establish that publishing already completed. */
class ReviewAlreadyAppliedException : IllegalStateException("이미 게시된 메뉴판 작업이에요.")

/** Typed error for preflight reviewVersion mismatches (distinct from field validation). */
class ReviewVersionConflictException : IllegalStateException("검수 버전이 달라졌어요. 다시 불러와 확인해 주세요.")

/** A different device/operator saved this same import; no automatic overwrite. */
class ReviewDraftConflictException : IllegalStateException(
    "다른 기기에서 검수 초안을 변경했어요. 최신 내용을 다시 불러와 확인해 주세요."
)

/** The full edit is safely on-device but §5.9 will reject its JSON size. */
class ReviewDraftTooLargeLocalException : IllegalStateException(
    "검수 초안이 서버 256KB 제한을 넘었어요. 이 기기에만 저장했어요. 입력 내용을 줄여 주세요."
)

/** Edits were saved only to the explicit conflict working copy, never PUT. */
class ReviewDraftLocalEditingException : IllegalStateException(
    "이 기기 초안 편집 중이에요. 서버에 반영하려면 명시적으로 덮어쓰기를 선택해 주세요."
)

/**
 * Shared save gate for server CAS and the unique device pending copy.
 * Test this gate independently: a conflict must never reach AtomicFile.write;
 * an unacknowledged forced PUT must never be optimized away.
 */
internal object DraftSaveSafety {
    fun assertWritable(conflicted: Boolean) {
        if (conflicted) throw ReviewDraftConflictException()
    }

    /** Only the most recent working copy may be considered acknowledged. */
    fun latestCopyAcknowledged(
        remote: ReviewDraftDto?,
        original: PendingReviewDraftStore.Envelope,
        working: PendingReviewDraftStore.Envelope?,
    ): Boolean = remote != null &&
        remote.reviewVersion == original.reviewVersion &&
        remote.draftVersion > original.expectedDraftVersion &&
        (working == null || working.reviewVersion == original.reviewVersion) &&
        ServerReviewDraftCodec.sameAndroidSnapshot(
            (working ?: original).content, remote.content)

    fun canSkip(
        forced: Boolean,
        pendingLocally: Boolean,
        attempted: Map<String, Any?>,
        acknowledged: Map<String, Any?>?,
    ): Boolean = !forced && !pendingLocally &&
        ServerReviewDraftCodec.sameAndroidSnapshot(attempted, acknowledged)
}

/**
 * The device checkpoint is never sufficient authorization to overwrite a
 * newer server draft. A prior in-flight PUT may, however, explain one exact
 * server version advance when its content matches byte-for-byte semantically.
 */
internal object DraftRecoveryPolicy {
    enum class Outcome { NONE, ACKNOWLEDGED, RESTORE, REBASE, CONFLICT }

    fun decide(
        server: ReviewDraftDto?,
        device: PendingReviewDraftStore.Envelope?,
        priorAttempt: PendingReviewDraftStore.Envelope?,
        reviewVersion: Int,
    ): Outcome {
        val local = device ?: return Outcome.NONE
        if (local.reviewVersion != reviewVersion ||
            (server != null && server.reviewVersion != reviewVersion)) return Outcome.CONFLICT
        if (ServerReviewDraftCodec.sameAndroidSnapshot(local.content, server?.content))
            return Outcome.ACKNOWLEDGED
        val serverVersion = server?.draftVersion ?: 0
        if (local.expectedDraftVersion == serverVersion) return Outcome.RESTORE
        if (priorAttempt != null && priorAttempt.reviewVersion == reviewVersion &&
            priorAttempt.expectedDraftVersion + 1 == serverVersion &&
            ServerReviewDraftCodec.sameAndroidSnapshot(priorAttempt.content, server?.content))
            return Outcome.REBASE
        return Outcome.CONFLICT
    }
}

/**
 * Treat a deliberate split of a previously merged OCR child as compatible.
 * Fresh OCR source identities must still be present. Used for both normal
 * draft restore and explicit conflict overwrite; keep their gates identical.
 */
internal fun compatibleOwnerReviewDraft(
    candidate: PhotoReviewState?, freshState: PhotoReviewState,
): Boolean = candidate != null &&
    candidate.items.map { it.id } == freshState.items.map { it.id } &&
    candidate.items.zip(freshState.items).all { (old, fresh) ->
        val freshIds = (
            PhotoReviewRules.optionSummary(fresh) + fresh.volumeChoices +
                fresh.preMergeOptions
        ).mapNotNull { it.sourceOptionId }.toSet()
        val savedIds = (
            PhotoReviewRules.optionSummary(old) + old.volumeChoices +
                old.preMergeOptions + old.classificationSnapshot?.options.orEmpty()
        ).mapNotNull { it.sourceOptionId } +
            listOfNotNull(old.classificationSnapshot?.primarySourceOptionId)
        savedIds.all { it in freshIds } && (if (old.manuallySplitGroup)
            fresh.mergedInto != null || fresh.mergeSources.isNotEmpty()
        else old.mergedInto == fresh.mergedInto &&
            old.volumeChoices.map { it.sourceOptionId } ==
                fresh.volumeChoices.map { it.sourceOptionId })
    }

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
    private val appContext = context.applicationContext
    private val pendingStore = PendingReviewDraftStore(appContext)
    // An explicitly chosen local conflict edit never mutates the original
    // pending file. It lives in its own auth/import-scoped AtomicFile.
    private val workingStore = PendingReviewDraftStore(appContext, slot = "working")
    // Separate AtomicFile and mutex: slow server PUT must never delay a newer
    // keystroke's durable on-device checkpoint.
    private val checkpointStore = PendingReviewDraftStore(appContext, slot = "checkpoint")
    private val checkpointMutex = Mutex()
    private var editingLocalConflict = false
    private var freshReview: PhotoReviewState? = null
    private var pendingLocally = false
    private var pendingOversized = false
    private var loaded: MenuImportStatusDto? = null
    private var activeImportId: String? = null
    private val draftMutex = Mutex()
    @Volatile private var draftVersion = 0
    private var published = false
    private var draftConflict = false
    private var pendingDraftConflict = false
    private var lastSavedContent: Map<String, Any?>? = null
    private var draftNotice: String? = null

    override fun consumeDraftNotice(): String? = draftNotice.also { draftNotice = null }
    override fun hasPendingLocalDraft(): Boolean = pendingLocally
    override fun hasOversizedPendingDraft(): Boolean = pendingOversized
    override fun hasPendingDraftConflict(): Boolean = pendingDraftConflict

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
        freshReview = state
        editingLocalConflict = false
        // Server content remains authoritative for other devices. Device
        // checkpoints are candidates only after draftVersion, reviewVersion,
        // OCR identity and the full serialized decisions are checked.
        fun compatible(candidate: PhotoReviewState?): Boolean =
            compatibleOwnerReviewDraft(candidate, state)
        runCatching { LegacyReviewDraftReader(appContext).clear(id) }
        val reviewVersion = requireNotNull(response.reviewVersion)
        val saved = response.reviewDraft
        val parsedAndroid = saved?.let(ServerReviewDraftCodec::decode)
        val regenerated = saved != null && saved.reviewVersion != reviewVersion
        val parsed = if (parsedAndroid != null) {
            if (regenerated) ServerReviewDraftCodec.reconcileRegenerated(parsedAndroid, state)
            else parsedAndroid
        } else saved?.let {
            ServerReviewDraftCodec.restoreStandard(it, state, allowStaleIds = regenerated)
        }
        draftVersion = saved?.draftVersion ?: 0
        draftConflict = false
        pendingDraftConflict = false
        published = false
        pendingLocally = false
        pendingOversized = false
        lastSavedContent = saved?.content
        draftNotice = when {
            saved == null -> null
            parsed == null -> "다른 클라이언트에서 저장한 초안을 확인해 주세요."
            saved.reviewVersion != reviewVersion ->
                "검수 버전이 변경됐어요. 남아 있는 항목만 다시 확인해 주세요."
            else -> null
        }
        val canRestore = saved == null ||
            (if (regenerated) parsed != null else compatible(parsed))
        var chosen = parsed.takeIf { canRestore } ?: state
        if (saved != null && !canRestore) {
            draftConflict = true
            draftNotice = "서버 초안의 일부 내용을 복원할 수 없어요. 담당자에게 확인해 주세요."
        }

        val pending = pendingStore.read(id)
        val checkpoint = checkpointStore.read(id)
        val working = workingStore.read(id)
        val device = working ?: checkpoint ?: pending
        val recovery = DraftRecoveryPolicy.decide(saved, device, pending, reviewVersion)
        if (device != null) {
            val local = ServerReviewDraftCodec.decode(ReviewDraftDto(
                device.expectedDraftVersion, device.reviewVersion,
                "1970-01-01T00:00:00Z", device.content,
            ))
            val safeLocal = device.itemIds == state.items.map { it.id } &&
                compatible(local)
            when {
                recovery == DraftRecoveryPolicy.Outcome.ACKNOWLEDGED && working == null -> {
                    // This exact edit reached the server (including a lost
                    // 200 response). Only now can its device copies be removed.
                    checkpointStore.clear(id)
                    pendingStore.clear(id)
                }
                working == null && canRestore && safeLocal &&
                    recovery in setOf(DraftRecoveryPolicy.Outcome.RESTORE,
                        DraftRecoveryPolicy.Outcome.REBASE) -> {
                    // Compatible unsent changes are editable immediately;
                    // normal CAS will synchronize them after the screen loads.
                    chosen = requireNotNull(local)
                    pendingLocally = true
                    pendingOversized =
                        ServerReviewDraftCodec.exceedsServerLimit(device.content)
                    if (recovery == DraftRecoveryPolicy.Outcome.REBASE) {
                        // An older in-flight request is the exact server
                        // version advance. Rebase the *newer* checkpoint
                        // durably before discarding evidence of that request.
                        checkpointStore.write(id,
                            device.copy(expectedDraftVersion = draftVersion))
                        pendingStore.clear(id)
                    }
                }
                else -> {
                    // Never silently overwrite another device or an unknown
                    // operator schema. Preserve the freshest local copy and
                    // expose only the already-existing explicit conflict flow.
                    if (working == null && checkpoint != null && safeLocal)
                        pendingStore.write(id, checkpoint)
                    draftConflict = true
                    pendingDraftConflict = safeLocal
                    pendingLocally = safeLocal
                    pendingOversized = safeLocal &&
                        ServerReviewDraftCodec.exceedsServerLimit(device.content)
                    draftNotice = if (safeLocal)
                        "서버와 기기에 서로 다른 검수 초안이 있어요. 먼저 확인해 주세요."
                    else "기기 초안의 OCR 항목이 변경되어 자동 복원을 중단했어요."
                }
            }
        }
        // OCR evidence and signed image URLs always come from this GET, not
        // from old local files. Draft-only fields are rebound to fresh data.
        loaded = response
        return rebindDraftData(chosen, state)
    }

    /** Rebind live OCR provenance and catalog observations to an edited draft. */
    private fun rebindDraftData(
        chosen: PhotoReviewState, state: PhotoReviewState,
    ): PhotoReviewState {
        val currentItems = state.items.associateBy { it.id }
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
        return restored
    }

    override suspend fun searchCatalog(query: String): List<CatalogProduct> {
        // The existing publish adapter validates selected IDs against its
        // current catalog snapshot, so keep it in sync with the server search.
        // Keep inactive results visible; never offer them for selection.
        return owner.searchCatalogLive(query)
            .map { CatalogProduct(it.productId, it.displayName, it.isActive) }
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

    /** §5.9 explicit conflict choices. Keep the pending file until the
     * owner deliberately selects one of these two paths.
     */
    override suspend fun startEditingLocalDraft(): PhotoReviewState {
        val id = activeImportId ?: error("검수 작업을 먼저 불러와 주세요.")
        return draftMutex.withLock {
            check(pendingDraftConflict) { "편집할 충돌 초안이 없어요." }
            val current = remote.getMenuImport(id)
            val displayed = loaded ?: error("최신 서버 초안을 먼저 불러와 주세요.")
            if (current.menuImportId != id || current.status != "ready_for_review" ||
                current.reviewVersion != displayed.reviewVersion ||
                (current.reviewDraft?.draftVersion ?: 0) != draftVersion) {
                throw ReviewDraftConflictException()
            }
            val original = pendingStore.read(id)
                ?: error("이 기기의 보호된 초안을 찾지 못했어요.")
            val selected = workingStore.read(id) ?: original
            val local = ServerReviewDraftCodec.decode(ReviewDraftDto(
                selected.expectedDraftVersion, selected.reviewVersion,
                "1970-01-01T00:00:00Z", selected.content,
            )) ?: error("기기 초안을 안전하게 읽을 수 없어요.")
            val fresh = freshReview ?: error("최신 OCR 항목을 불러와 주세요.")
            require(original.reviewVersion == displayed.reviewVersion &&
                selected.reviewVersion == displayed.reviewVersion &&
                selected.itemIds == fresh.items.map { it.id } &&
                compatibleOwnerReviewDraft(local, fresh)) {
                "기기 초안의 OCR 항목이 최신 서버 검수와 달라요. 원본을 유지했어요."
            }
            // This explicit action only changes the displayed editor. Until
            // the owner confirms CAS overwrite, server data is unchanged.
            editingLocalConflict = true
            pendingLocally = true
            pendingOversized = ServerReviewDraftCodec.exceedsServerLimit(selected.content)
            rebindDraftData(local, fresh)
        }
    }

    override suspend fun chooseServerDraft() {
        val id = activeImportId ?: error("검수 작업을 먼저 불러와 주세요.")
        draftMutex.withLock {
            check(pendingDraftConflict) { "선택할 기기 초안 충돌이 없어요." }
            check(pendingStore.read(id) != null) { "이 기기의 보관 초안을 찾지 못했어요." }
            // The owner must have seen THIS version. Never discard the only
            // device copy after another operator saved again.
            val current = remote.getMenuImport(id)
            if (current.menuImportId != id ||
                current.status != "ready_for_review" ||
                current.reviewVersion != loaded?.reviewVersion ||
                (current.reviewDraft?.draftVersion ?: 0) != draftVersion) {
                throw ReviewDraftConflictException()
            }
            checkpointMutex.withLock {
                checkpointStore.clear(id)
                pendingStore.clear(id)
                workingStore.clear(id)
            }
            pendingDraftConflict = false
            pendingLocally = false
            pendingOversized = false
            draftConflict = false
        }
    }

    override suspend fun chooseLocalDraft() {
        val id = activeImportId ?: error("검수 작업을 먼저 불러와 주세요.")
        val version = loaded?.reviewVersion ?: error("검수 데이터를 먼저 불러와 주세요.")
        draftMutex.withLock {
            check(pendingDraftConflict) { "선택할 기기 초안 충돌이 없어요." }
            val pending = workingStore.read(id) ?: pendingStore.read(id)
                ?: error("이 기기의 보관 초안을 찾지 못했어요.")
            val current = remote.getMenuImport(id)
            require(current.menuImportId == id && current.status == "ready_for_review" &&
                current.reviewVersion == version &&
                pending.reviewVersion == version) {
                "검수 데이터가 변경됐어요. 서버 검수를 다시 확인해 주세요."
            }
            val currentDraftVersion = current.reviewDraft?.draftVersion ?: 0
            // The user made a choice about the exact version displayed.
            // If someone saved again, require another explicit review.
            if (currentDraftVersion != draftVersion) throw ReviewDraftConflictException()
            val fresh = mapServerPhotoReview(current, snapshot())
            val local = ServerReviewDraftCodec.decode(ReviewDraftDto(
                pending.expectedDraftVersion, version, "1970-01-01T00:00:00Z",
                pending.content,
            )) ?: error("기기 보관 초안을 안전하게 읽을 수 없어요.")
            require(pending.itemIds == fresh.items.map { it.id } &&
                compatibleOwnerReviewDraft(local, fresh)) {
                "OCR 항목이나 옵션이 변경됐어요. 자동 덮어쓰기를 중단했어요."
            }
            if (ServerReviewDraftCodec.exceedsServerLimit(pending.content))
                throw ReviewDraftTooLargeLocalException()
            val result = try {
                remote.saveMenuReviewDraft(id, ReviewDraftSaveRequestDto(
                    draftVersion = currentDraftVersion,
                    reviewVersion = version, content = pending.content,
                ))
            } catch (error: BottleMapApiException) {
                if (error.code == "REVIEW_DRAFT_OUTDATED") throw ReviewDraftConflictException()
                throw error
            }
            check(result.menuImportId == id &&
                result.draftVersion == currentDraftVersion + 1) {
                "검수 초안 저장 버전이 올바르지 않아요."
            }
            draftVersion = result.draftVersion
            lastSavedContent = pending.content
            // Clear only after an acknowledged CAS save. On connection loss,
            // the local backup survives and can be reconciled on reload.
            checkpointMutex.withLock {
                checkpointStore.clear(id)
                pendingStore.clear(id)
                workingStore.clear(id)
            }
            editingLocalConflict = false
            pendingLocally = false
            pendingOversized = false
            pendingDraftConflict = false
            draftConflict = false
        }
    }

    /** Atomic, account/import-scoped local write independent of network IO. */
    override suspend fun checkpointDraft(state: PhotoReviewState) {
        val id = activeImportId ?: error("검수 작업을 먼저 불러와 주세요.")
        val version = loaded?.reviewVersion ?: error("검수 데이터를 먼저 불러와 주세요.")
        val content = ServerReviewDraftCodec.encode(state)
        checkpointMutex.withLock {
            if (published) return@withLock
            if (editingLocalConflict && draftConflict) {
                val original = pendingStore.read(id)
                    ?: error("보호된 기기 원본 초안을 찾지 못했어요.")
                workingStore.write(id, original.copy(
                    content = content, itemIds = state.items.map { it.id },
                ))
                pendingLocally = true
                pendingOversized = ServerReviewDraftCodec.exceedsServerLimit(content)
            } else if (!draftConflict) {
                checkpointStore.write(id, PendingReviewDraftStore.Envelope(
                    reviewVersion = version,
                    expectedDraftVersion = draftVersion,
                    itemIds = state.items.map { it.id },
                    content = content,
                ))
                pendingLocally = !ServerReviewDraftCodec.sameAndroidSnapshot(
                    content, lastSavedContent)
                pendingOversized = ServerReviewDraftCodec.exceedsServerLimit(content)
            }
        }
    }

    /** The ACK applies only to the submitted snapshot, not later edits. */
    private suspend fun acknowledgeDeviceDraft(
        id: String, content: Map<String, Any?>,
    ) {
        checkpointMutex.withLock {
            val latest = checkpointStore.read(id)
            if (latest != null &&
                !ServerReviewDraftCodec.sameAndroidSnapshot(latest.content, content)) {
                // A newer edit was made while PUT was in flight. The server
                // version is now the base for that edit; keep it recoverable.
                checkpointStore.write(id, latest.copy(expectedDraftVersion = draftVersion))
                pendingLocally = true
                pendingOversized =
                    ServerReviewDraftCodec.exceedsServerLimit(latest.content)
            } else {
                checkpointStore.clear(id)
                pendingLocally = false
                pendingOversized = false
            }
            // Clearing last is important for crashes during version rebase:
            // this attempted snapshot proves a lost server ACK was ours.
            pendingStore.clear(id)
        }
    }

    /** §5.9 optimistic concurrency: never silently replace another editor. */
    override suspend fun saveDraft(state: PhotoReviewState) = saveDraftInternal(state, forceCas = false)

    override suspend fun flushBeforePublish(state: PhotoReviewState) =
        saveDraftInternal(state, forceCas = true)

    private suspend fun saveDraftInternal(state: PhotoReviewState, forceCas: Boolean) {
        val id = activeImportId ?: error("검수 작업을 먼저 불러와 주세요.")
        val version = loaded?.reviewVersion ?: error("검수 정보를 먼저 불러와 주세요.")
        val content = ServerReviewDraftCodec.encode(state)
        draftMutex.withLock {
            if (published) return@withLock
            // The pending file is the ONLY copy of the offline edits when
            // an operator/device has advanced the server CAS. Do not touch it
            // until the owner explicitly resolves the conflict.
            if (editingLocalConflict && draftConflict) {
                // No server PUT is allowed during conflict editing, even
                // after the working copy is reduced under the server limit.
                // Explicit confirmation in chooseLocalDraft is required.
                val original = pendingStore.read(id)
                    ?: error("보호된 기기 원본 초안을 찾지 못했어요.")
                workingStore.write(id, original.copy(content = content,
                    itemIds = state.items.map { it.id }))
                pendingLocally = true
                pendingOversized = ServerReviewDraftCodec.exceedsServerLimit(content)
                throw ReviewDraftLocalEditingException()
            }
            DraftSaveSafety.assertWritable(draftConflict)
            // An unacknowledged forced prepublish PUT may have identical
            // content to the last ACK, but still needs server CAS + cleanup.
            if (DraftSaveSafety.canSkip(forceCas, pendingLocally,
                    content, lastSavedContent)) {
                checkpointMutex.withLock {
                    val cache = checkpointStore.read(id)
                    if (ServerReviewDraftCodec.sameAndroidSnapshot(cache?.content, content))
                        checkpointStore.clear(id)
                }
                return@withLock
            }
            // Atomic no-backup storage is completed BEFORE network IO so a
            // process kill after a failed PUT cannot silently lose edits.
            pendingStore.write(id, PendingReviewDraftStore.Envelope(
                reviewVersion = version, expectedDraftVersion = draftVersion,
                itemIds = state.items.map { it.id }, content = content,
            ))
            pendingLocally = true
            // A server-rejected large snapshot still survives on device.
            // Never make a PUT that §5.9 must reject above 256 KiB.
            pendingOversized = ServerReviewDraftCodec.exceedsServerLimit(content)
            if (pendingOversized) throw ReviewDraftTooLargeLocalException()
            val request = ReviewDraftSaveRequestDto(
                draftVersion = draftVersion, reviewVersion = version, content = content,
            )
            val saved = try {
                remote.saveMenuReviewDraft(id, request)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: BottleMapApiException) {
                if (error.code == "REVIEW_DRAFT_TOO_LARGE" || error.httpStatus == 413) {
                    pendingOversized = true
                    throw ReviewDraftTooLargeLocalException()
                }
                if (error.code == "REVIEW_DRAFT_OUTDATED") {
                    draftConflict = true
                    pendingDraftConflict = true
                    throw ReviewDraftConflictException()
                }
                // A lost 200 response can mean the server committed. Check the
                // exact content before retrying with an obsolete draftVersion.
                val observed = runCatching { remote.getMenuImport(id) }.getOrNull()
                val currentDraft = observed?.reviewDraft
                if (currentDraft != null &&
                    ServerReviewDraftCodec.sameAndroidSnapshot(content, currentDraft.content) &&
                    currentDraft.reviewVersion == version &&
                    currentDraft.draftVersion > draftVersion) {
                    draftVersion = currentDraft.draftVersion
                    lastSavedContent = content
                    acknowledgeDeviceDraft(id, content)
                    return@withLock
                }
                if (currentDraft != null && currentDraft.draftVersion > draftVersion) {
                    draftConflict = true
                    pendingDraftConflict = true
                    throw ReviewDraftConflictException()
                }
                throw error
            }
            check(saved.menuImportId == id && saved.draftVersion == draftVersion + 1) {
                "검수 초안 저장 버전이 올바르지 않아요."
            }
            draftVersion = saved.draftVersion
            lastSavedContent = content
            pendingDraftConflict = false
            acknowledgeDeviceDraft(id, content)
        }
    }

    /** A committed server review atomically clears its draft (PR #171). */
    private suspend fun finishPublishedDraft(id: String) {
        draftMutex.withLock {
            published = true
            lastSavedContent = null
            pendingLocally = false
            pendingOversized = false
            checkpointMutex.withLock {
                runCatching { checkpointStore.clear(id) }
                runCatching { pendingStore.clear(id) }
                runCatching { workingStore.clear(id) }
            }
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
