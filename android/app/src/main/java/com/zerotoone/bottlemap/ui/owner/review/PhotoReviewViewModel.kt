package com.zerotoone.bottlemap.ui.owner.review

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.network.menuWriteErrorText
import com.zerotoone.bottlemap.data.owner.review.PhotoReviewRepository
import com.zerotoone.bottlemap.data.owner.review.ReviewAlreadyAppliedException
import com.zerotoone.bottlemap.data.owner.review.ReviewVersionConflictException
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewRules.OptionField
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewRules.RematchOutcome
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

sealed interface PhotoReviewLoad {
    data object Loading : PhotoReviewLoad
    data object Applied : PhotoReviewLoad
    data class Error(val message: String) : PhotoReviewLoad
    data class Ready(val review: PhotoReviewState) : PhotoReviewLoad
}

enum class PublishFailure { NETWORK, SERVER, FORBIDDEN, VALIDATION, CONFLICT, AUTH, UNKNOWN }

sealed interface PublishOutcome {
    data class Submitting(val summary: ReviewStats, val newWhisky: Boolean) : PublishOutcome
    data class Checking(val summary: ReviewStats, val newWhisky: Boolean) : PublishOutcome
    data class Success(val summary: ReviewStats, val newWhisky: Boolean) : PublishOutcome
    data class Failed(
        val summary: ReviewStats,
        val newWhisky: Boolean,
        val reason: PublishFailure,
        val detail: String? = null,
    ) : PublishOutcome
}

internal fun classifyPublishFailure(error: Throwable): PublishFailure {
    val api = error as? BottleMapApiException
    return when {
        api?.httpStatus == 401 || api?.code == "UNAUTHORIZED" -> PublishFailure.AUTH
        api?.httpStatus == 403 -> PublishFailure.FORBIDDEN
        api?.httpStatus == 409 || error is ReviewVersionConflictException ||
            error.message == "REVIEW_OUTDATED" -> PublishFailure.CONFLICT
        api?.httpStatus == 422 || error is IllegalArgumentException ->
            PublishFailure.VALIDATION
        api?.code == "NETWORK_ERROR" -> PublishFailure.NETWORK
        api?.httpStatus != null && api.httpStatus >= 500 -> PublishFailure.SERVER
        else -> PublishFailure.UNKNOWN
    }
}

sealed interface PhotoReviewEvent {
    data class Toast(val message: String) : PhotoReviewEvent
    /** Leave the photo flow for the existing menu-management screen. */
    data object Leave : PhotoReviewEvent
    data class FocusReviewName(val itemId: String) : PhotoReviewEvent
    data class FocusDetailName(val itemId: String) : PhotoReviewEvent
    data object ScrollToPublish : PhotoReviewEvent
}

/**
 * State and transitions of the one-page review (v18 flow 02). Every user action of the
 * prototype has one method here; the composables only call them.
 */
class PhotoReviewViewModel(private val repository: PhotoReviewRepository) : ViewModel() {
    private val _load = MutableStateFlow<PhotoReviewLoad>(PhotoReviewLoad.Loading)
    val load: StateFlow<PhotoReviewLoad> = _load.asStateFlow()
    private val _publishing = MutableStateFlow(false)
    val publishing: StateFlow<Boolean> = _publishing.asStateFlow()
    private val _publishOutcome = MutableStateFlow<PublishOutcome?>(null)
    val publishOutcome: StateFlow<PublishOutcome?> = _publishOutcome.asStateFlow()

    private val draftSaveMutex = Mutex()
    private var latestDraftRevision = 0L
    private var leaving = false
    private val latestRematchRequest = mutableMapOf<String, Int>()
    private val latestCatalogSearchRequest = mutableMapOf<String, Int>()

    private val _events = Channel<PhotoReviewEvent>(Channel.BUFFERED)
    val events = _events.receiveAsFlow()

    init {
        reload()
    }

    fun reload() {
        if (_publishing.value) return
        // Invalidate all queued writes before the repository changes its loaded
        // reviewVersion. Also wait for any already-running save to finish at the
        // old version; otherwise it could persist stale decisions as the new one.
        ++latestDraftRevision
        _load.value = PhotoReviewLoad.Loading
        viewModelScope.launch {
            draftSaveMutex.withLock {
                _load.value = try {
                    PhotoReviewLoad.Ready(repository.loadReview())
                } catch (applied: ReviewAlreadyAppliedException) {
                    PhotoReviewLoad.Applied
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (error: Exception) {
                    PhotoReviewLoad.Error(error.message ?: "검수 정보를 불러오지 못했어요.")
                }
            }
        }
    }

    private val review: PhotoReviewState?
        get() = (_load.value as? PhotoReviewLoad.Ready)?.review

    private fun item(id: String) = review?.items?.firstOrNull { it.id == id }

    private fun toast(message: String) {
        _events.trySend(PhotoReviewEvent.Toast(message))
    }

    /** Replaces the state without regrouping (typing, opening a modal). */
    private fun set(state: PhotoReviewState) {
        _load.value = PhotoReviewLoad.Ready(state)
        // Persist every field change, including unfinished typing, so a
        // process kill never discards the current owner review draft.
        saveDraft(state)
    }

    /**
     * The prototype's mutate(): apply a change, fold every card that moved to another
     * group, open that group, save the draft and say "확인 완료" when a card left the
     * "확인이 필요해요" group.
     */
    private fun mutate(change: (PhotoReviewState) -> PhotoReviewState) {
        val before = review ?: return
        val pendingBefore = PhotoReviewRules.stats(before).pending.size
        val oldGroups = before.items.associate { it.id to PhotoReviewRules.displayGroup(before, it) }
        val changed = change(before)
        var show = changed.show
        val items = changed.items.map { x ->
            val group = PhotoReviewRules.itemGroup(x, changed)
            if (oldGroups[x.id] != null && oldGroups[x.id] != group) {
                if (group != ReviewGroup.EXCLUDED) show = show.with(group, true)
                x.copy(expanded = false)
            } else x
        }
        val next = changed.copy(items = items, show = show, typingSnapshots = emptyMap())
        set(next)
        if (PhotoReviewRules.stats(next).pending.size < pendingBefore) toast("확인 완료")
    }

    private fun mutateItem(id: String, change: (ReviewItem) -> ReviewItem) = mutate { s ->
        s.copy(items = s.items.map { if (it.id == id) change(it) else it })
    }

    private fun setItem(id: String, change: (ReviewItem) -> ReviewItem) {
        val s = review ?: return
        set(s.copy(items = s.items.map { if (it.id == id) change(it) else it }))
    }

    /** Serialized, latest-state-only writes. An older suspended snapshot
     * cannot overwrite an owner's more recent edit when its IO completes.
     */
    private fun saveDraft(state: PhotoReviewState) {
        val revision = ++latestDraftRevision
        viewModelScope.launch {
            draftSaveMutex.withLock {
                if (revision == latestDraftRevision) {
                    try {
                        repository.saveDraft(state)
                    } catch (cancelled: CancellationException) {
                        throw cancelled
                    } catch (_: Exception) {
                        // The final save on Leave will retry and surface errors.
                    }
                }
            }
        }
    }

    // ---- Screen-level actions ----

    fun leave() {
        if (_publishing.value || leaving) return
        leaving = true
        val final = review?.takeIf { _publishOutcome.value == null }?.copy(modal = null)
        if (final == null) {
            _events.trySend(PhotoReviewEvent.Leave)
            return
        }
        // Do not pop the ViewModel until its final draft is durably saved.
        _load.value = PhotoReviewLoad.Ready(final)
        ++latestDraftRevision // invalidate any queued older save
        viewModelScope.launch {
            val saved = draftSaveMutex.withLock {
                try {
                    repository.saveDraft(final)
                    true
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (_: Exception) {
                    false
                }
            }
            if (saved) _events.send(PhotoReviewEvent.Leave)
            else {
                leaving = false
                toast("임시 검수 기록을 저장하지 못했어요. 다시 시도해 주세요.")
            }
        }
    }

    fun toggleGroup(group: ReviewGroup) {
        val s = review ?: return
        set(s.copy(show = s.show.with(group, !s.show[group])))
    }

    fun jumpToPublish() {
        _events.trySend(PhotoReviewEvent.ScrollToPublish)
    }

    fun typeDefaultPour(text: String) {
        val s = review ?: return
        set(s.copy(draftDefaultPourText = text))
    }

    fun saveDefaultPour(text: String) {
        val n = readNumeric(text)
        if (!validVolume(n)) {
            toast("1 ~ 999 사이의 숫자를 입력해주세요.")
            return
        }
        viewModelScope.launch {
            // Claim a saved default only after the real bar API succeeds. A
            // failed request must not silently unlock the Publish button.
            try {
                repository.saveDefaultPour(n.toInt())
                mutate { s ->
                    s.copy(defaultPour = n, draftDefaultPourText = "",
                        items = s.items.map { PhotoReviewRules.applyDefaultPour(it, n) })
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                toast(error.message ?: "기본 잔 용량을 저장하지 못했어요. 다시 시도해 주세요.")
            }
        }
    }

    fun requestPublish() {
        if (_publishing.value) return
        val s = review ?: return
        if (PhotoReviewRules.stats(s).canPublish) set(s.copy(modal = ReviewModal(ReviewModalType.PUBLISH)))
    }

    private fun summaryFor(state: PhotoReviewState) =
        PhotoReviewRules.stats(state) to state.items.any {
            !it.excluded && it.mergedInto == null && it.type == ReviewItemType.WHISKY &&
                it.linkedProductId == null && it.match == ReviewMatch.NEW
        }

    private fun submit(state: PhotoReviewState, summary: ReviewStats, newWhisky: Boolean) {
        if (_publishing.value) return
        _publishing.value = true
        _publishOutcome.value = PublishOutcome.Submitting(summary, newWhisky)
        viewModelScope.launch {
            try {
                repository.publish(state)
                _publishOutcome.value = PublishOutcome.Success(summary, newWhisky)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                val reason = classifyPublishFailure(error)
                _publishOutcome.value = PublishOutcome.Failed(
                    summary, newWhisky, reason,
                    detail = if (reason == PublishFailure.VALIDATION)
                        menuWriteErrorText(error) else null,
                )
            } finally {
                _publishing.value = false
            }
        }
    }

    fun confirmPublish() {
        if (_publishing.value || _publishOutcome.value != null) return
        val state = review ?: return
        if (state.modal?.type != ReviewModalType.PUBLISH ||
            !PhotoReviewRules.stats(state).canPublish) return
        val (summary, newWhisky) = summaryFor(state)
        set(state.copy(modal = null))
        submit(state, summary, newWhisky)
    }

    /** Unknown responses can already be committed. Never resubmit before GET. */
    fun checkPublishStatus(retryWhenReady: Boolean = false) {
        if (_publishing.value) return
        val result = _publishOutcome.value as? PublishOutcome.Failed ?: return
        _publishing.value = true
        _publishOutcome.value = PublishOutcome.Checking(result.summary, result.newWhisky)
        viewModelScope.launch {
            try {
                when (repository.checkPublishedStatus()) {
                    true -> _publishOutcome.value =
                        PublishOutcome.Success(result.summary, result.newWhisky)
                    false -> if (retryWhenReady && result.reason == PublishFailure.NETWORK &&
                        review?.let { PhotoReviewRules.stats(it).canPublish } == true) {
                        _publishing.value = false
                        submit(requireNotNull(review), result.summary, result.newWhisky)
                        return@launch
                    } else {
                        _publishOutcome.value = null
                        toast("게시되지 않았어요. 검수 내용을 확인한 뒤 다시 게시해 주세요.")
                    }
                    null -> _publishOutcome.value = PublishOutcome.Failed(
                        result.summary, result.newWhisky, PublishFailure.UNKNOWN)
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                _publishOutcome.value = PublishOutcome.Failed(
                    result.summary, result.newWhisky, PublishFailure.UNKNOWN)
            } finally {
                if (_publishOutcome.value !is PublishOutcome.Submitting)
                    _publishing.value = false
            }
        }
    }

    fun returnToReview() {
        if (_publishing.value) return
        when ((_publishOutcome.value as? PublishOutcome.Failed)?.reason) {
            PublishFailure.CONFLICT -> {
                _publishOutcome.value = null
                // Current reviewVersion is stale. The repository will restore a
                // compatible draft only when server IDs and version still match.
                reload()
                toast("메뉴 정보가 변경돼 최신 검수 내용을 불러와요. 이전 버전의 입력은 자동 적용되지 않아요.")
            }
            PublishFailure.NETWORK, PublishFailure.VALIDATION, PublishFailure.AUTH -> {
                _publishOutcome.value = null
                review?.let { set(it.copy(modal = null)) }
            }
            else -> Unit
        }
    }

    fun dismissModal() {
        if (_publishing.value) return
        val s = review ?: return
        set(s.copy(modal = null))
    }

    suspend fun refreshSourcePhotoUrl(itemId: String): String? =
        repository.refreshSourcePhotoUrl(itemId)

    fun openSourcePhoto(id: String, mergeIndex: Int? = null) {
        val s = review ?: return
        set(s.copy(modal = ReviewModal(ReviewModalType.SOURCE_PHOTO, id, mergeIndex)))
    }

    // ---- Card actions ----

    fun toggleExpanded(id: String) = mutateItem(id) { it.copy(expanded = !it.expanded) }

    /** OCR grouping is advisory: if two lines are NOT the same whisky the owner
     * can undo the inferred grouping without losing either source line.
     * Already-confirmed prices are intentionally restored to their OCR values.
     */
    fun splitMerged(id: String) {
        val loaded = review ?: return
        val master = loaded.items.firstOrNull { it.id == id } ?: return
        if (master.mergeSources.isEmpty()) return
        val allChildren = loaded.items.filter { it.mergedInto == id }.map { it.id }.toSet()
        if (allChildren.isEmpty()) return
        val localPrices = try {
            loaded.items.filter { (it.id == id || it.id in allChildren) &&
                it.linkedProductId == null
            }.associate { it.id to repository.existingUnlinkedServingPrices(it.name) }
        } catch (_: Exception) {
            toast("기존 메뉴 가격을 확인하지 못했어요. 다시 시도해 주세요.")
            return
        }
        mutate { state ->
        val original = master.preMergeOptions
        val first = original.firstOrNull()
        state.copy(
            show = state.show.copy(pending = true, ready = true),
            items = state.items.map { item ->
                when {
                    item.id == id -> {
                        val split = item.copy(
                        mergeSources = emptyList(),
                        manuallySplitGroup = true,
                        preMergeOptions = emptyList(),
                        primaryHasOption = first != null,
                        price = first?.price ?: 0.0,
                        volume = first?.volume ?: item.volume,
                        bottle = first?.bottle ?: false,
                        primarySourceOptionId = first?.sourceOptionId,
                        primaryOptionLabel = first?.label,
                        options = original.drop(1),
                        priceCandidates = item.priceCandidates.filter { candidate ->
                            !candidate.existing && candidate.sourceItemId == id
                        },
                        chosenServingPrices = emptyMap(),
                        volumeChoices = emptyList(),
                        chosenVolumeKeys = emptySet(),
                        volumeChoicesConfirmed = true,
                        expanded = false,
                        )
                        if (split.linkedProductId == null)
                            PhotoReviewRules.rebindUnlinkedPrices(
                                split, localPrices[split.id].orEmpty())
                        else split
                    }
                    item.id in allChildren -> {
                        val split = item.copy(
                            mergedInto = null, excluded = false, required = true,
                            manuallySplitGroup = true, expanded = false,
                        )
                        if (split.linkedProductId == null)
                            PhotoReviewRules.rebindUnlinkedPrices(
                                split, localPrices[split.id].orEmpty())
                        else split
                    }
                    else -> item
                }
            },
        )
        }
    }

    fun toggleBottle(id: String, index: Int?) {
        val pour = review?.defaultPour ?: return
        mutateItem(id) { PhotoReviewRules.toggleBottle(it, index, pour) }
    }

    fun confirmMatch(id: String) {
        val x = item(id) ?: return
        val product = x.candidates.singleOrNull()
        if (product == null) {
            toast("후보를 다시 선택해 주세요.")
            return
        }
        linkChosen(x, product)
    }

    fun chooseCandidate(id: String, productId: String) {
        val x = item(id) ?: return
        if (x.candidates.any { it.productId == productId }) mutateItem(id) { it.copy(selectedCandidateId = productId) }
        else toast("상품 후보를 다시 확인해 주세요.")
    }

    fun confirmSelectedCandidate(id: String) {
        val x = item(id) ?: return
        val product = x.candidates.firstOrNull { it.productId == x.selectedCandidateId }
        if (product == null) toast("위스키를 먼저 선택해 주세요.") else linkChosen(x, product)
    }

    fun selectSearchResult(id: String, productId: String) {
        val x = item(id) ?: return
        if (x.searchResults?.any { it.productId == productId && it.isActive } == true) {
            mutateItem(id) { it.copy(selectedSearchId = productId) }
        }
    }

    fun confirmSelectedSearch(id: String) {
        val x = item(id) ?: return
        val product = x.searchResults?.firstOrNull {
            it.productId == x.selectedSearchId && it.isActive
        }
        if (product == null) toast("위스키를 먼저 선택해 주세요.") else linkChosen(x, product)
    }

    /** Contract §8.7: server handles age/edition conflicts after linking. */
    private fun linkChosen(x: ReviewItem, product: CatalogProduct) {
        mutateItem(x.id) { PhotoReviewRules.linkChosenProduct(it, product, false) }
    }

    fun confirmNew(id: String) = mutateItem(id) {
        it.copy(name = it.newProductName ?: it.name, nameSaved = true, newConfirmed = true, matchConfirmed = true,
            nameEditMode = false, reviewNameDraft = null, linkedProductId = null, linkedProductName = null,
            match = ReviewMatch.NEW, operatorPending = true, operatorReason = OperatorReason.NEW)
    }

    fun editReviewName(id: String) {
        setItem(id) {
            // The latest owner-visible name wins over a stale OCR draft.
            it.copy(nameEditMode = true,
                reviewNameDraft = it.reviewNameDraft ?: it.name)
        }
        review?.let(::saveDraft)
        _events.trySend(PhotoReviewEvent.FocusReviewName(id))
    }

    fun typeReviewName(id: String, text: String) = setItem(id) { it.copy(reviewNameDraft = text) }

    fun clearReviewName(id: String) {
        setItem(id) { it.copy(reviewNameDraft = "") }
        _events.trySend(PhotoReviewEvent.FocusReviewName(id))
    }

    fun saveReviewName(id: String) {
        val x = item(id) ?: return
        val proposed = (x.reviewNameDraft ?: x.name).trim()
        if (proposed.isEmpty() || proposed.length > 200 ||
            PhotoReviewRules.normalizedUnlinkedMenuName(proposed).isBlank()) {
            toast("메뉴 이름을 다시 확인해 주세요.")
            _events.trySend(PhotoReviewEvent.FocusReviewName(id))
            return
        }
        renameAndRematch(id, proposed, "메뉴 이름 저장 · 상품 연결은 관리자 검토 대상이에요.") {
            it.copy(name = proposed, newProductName = proposed, nameSaved = true, nameConfirmed = true,
                reviewNameDraft = null, nameEditMode = false)
        }
    }

    fun confirmName(id: String) {
        val x = item(id) ?: return
        if (x.name.isBlank() ||
            PhotoReviewRules.normalizedUnlinkedMenuName(x.name).isBlank()) {
            toast("메뉴 이름을 확인해 주세요.")
            return
        }
        mutateItem(id) { it.copy(nameConfirmed = true, nameSaved = true, nameEditMode = false) }
    }

    fun editDetailName(id: String) {
        mutateItem(id) { it.copy(detailNameEditing = true, detailNameDraft = it.name, expanded = true) }
        _events.trySend(PhotoReviewEvent.FocusDetailName(id))
    }

    fun typeDetailName(id: String, text: String) = setItem(id) { it.copy(detailNameDraft = text) }

    fun saveDetailName(id: String) {
        val x = item(id) ?: return
        val proposed = (x.detailNameDraft ?: x.name).trim()
        if (proposed.isEmpty() || proposed.length > 200 ||
            PhotoReviewRules.normalizedUnlinkedMenuName(proposed).isBlank()) {
            toast("메뉴 이름을 다시 확인해 주세요.")
            _events.trySend(PhotoReviewEvent.FocusDetailName(id))
            return
        }
        renameAndRematch(id, proposed, "메뉴 이름 저장 · 미매칭 상품은 관리자 검토 대상이에요.") {
            it.copy(name = proposed, detailNameDraft = null, detailNameEditing = false, nameSaved = true,
                nameConfirmed = true)
        }
    }

    /** Decision 2: renaming a whisky line rematches it by the new name. */
    private fun renameAndRematch(id: String, name: String, operatorToast: String, rename: (ReviewItem) -> ReviewItem) {
        val x = item(id) ?: return
        if (x.type != ReviewItemType.WHISKY) {
            val saved = try {
                repository.existingUnlinkedServingPrices(name)
            } catch (_: Exception) {
                toast("기존 메뉴 가격을 확인하지 못했어요. 다시 시도해 주세요.")
                return
            }
            mutateItem(id) { PhotoReviewRules.rebindUnlinkedPrices(rename(it), saved) }
            return
        }
        val sequence = (latestRematchRequest[id] ?: 0) + 1
        latestRematchRequest[id] = sequence
        viewModelScope.launch {
            val matches = try {
                repository.exactMatches(name)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                // A failed search is not a zero-match result. Keep the saved link.
                if (latestRematchRequest[id] == sequence)
                    toast("위스키 검색에 실패했어요. 연결을 유지하고 다시 시도해 주세요.")
                return@launch
            }
            // Responses may arrive out of order (A then B, but A finishes last).
            // An edit still being typed is newer than the submitted request.
            if (latestRematchRequest[id] != sequence) return@launch
            val current = item(id) ?: return@launch
            if (current.reviewNameDraft?.trim()?.let { it != name } == true ||
                current.detailNameDraft?.trim()?.let { it != name } == true) return@launch
            // Only unlinked results are compared against the bar-local
            // normalized name key. Linked results use their product ID.
            val saved = if (matches.size == 1) emptyList() else try {
                repository.existingUnlinkedServingPrices(name)
            } catch (_: Exception) {
                toast("기존 메뉴 가격을 확인하지 못했어요. 다시 시도해 주세요.")
                return@launch
            }
            var outcome = RematchOutcome.OTHER
            mutateItem(id) {
                val (rematched, result) = PhotoReviewRules.applyRematch(rename(it), matches)
                outcome = result
                if (rematched.linkedProductId == null)
                    PhotoReviewRules.rebindUnlinkedPrices(rematched, saved)
                else rematched
            }
            if (outcome == RematchOutcome.OPERATOR) toast(operatorToast)
        }
    }

    fun startCatalogSearch(id: String) = mutateItem(id) {
        it.copy(searchMode = true, searchDraft = it.searchDraft.ifEmpty { it.name }, searchResults = null,
            selectedCandidateId = null, selectedSearchId = null, nameEditMode = false)
    }

    fun typeCatalogQuery(id: String, text: String) {
        latestCatalogSearchRequest[id] = (latestCatalogSearchRequest[id] ?: 0) + 1
        setItem(id) { it.copy(searchDraft = text, searchResults = null, selectedSearchId = null) }
    }

    fun searchCatalog(id: String) {
        val x = item(id) ?: return
        val query = x.searchDraft.trim()
        if (query.isEmpty()) {
            toast("검색할 위스키 이름을 입력해 주세요.")
            return
        }
        val generation = (latestCatalogSearchRequest[id] ?: 0) + 1
        latestCatalogSearchRequest[id] = generation
        viewModelScope.launch {
            val results = try {
                repository.searchCatalog(query)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                if (latestCatalogSearchRequest[id] == generation)
                    toast("검색하지 못했어요. 다시 시도해 주세요.")
                return@launch
            }
            val current = item(id) ?: return@launch
            if (latestCatalogSearchRequest[id] != generation ||
                !current.searchMode || current.searchDraft.trim() != query) return@launch
            mutateItem(id) { it.copy(searchResults = results, selectedSearchId = null) }
        }
    }

    fun registerAsNew(id: String) {
        mutateItem(id) { PhotoReviewRules.markAsNewForOperator(it, it.searchDraft.ifEmpty { it.name }) }
        _events.trySend(PhotoReviewEvent.FocusReviewName(id))
    }

    fun chooseServingPrice(id: String, servingKey: String, price: Int) {
        val x = item(id) ?: return
        if (PhotoReviewRules.priceCandidatesForServing(x, servingKey).none {
            it.priceKrw == price
        }) return
        mutateItem(id) { PhotoReviewRules.chooseServingPrice(it, servingKey, price) }
    }

    fun toggleVolumeChoice(id: String, servingKey: String) {
        val x = item(id) ?: return
        val exists = x.volumeChoices.any { PhotoReviewRules.servingKey(it) == servingKey }
        if (!exists || x.volumeChoicesConfirmed) return
        val selected = x.chosenVolumeKeys
        if (servingKey !in selected &&
            selected.size >= PhotoReviewRules.MAX_PICKED_VOLUMES) {
            toast("용량은 최대 3가지까지 설정 가능해요.")
            return
        }
        mutateItem(id) { it.copy(chosenVolumeKeys =
            if (servingKey in selected) selected - servingKey else selected + servingKey
        ) }
    }

    fun confirmVolumeChoices(id: String) {
        val x = item(id) ?: return
        if (x.chosenVolumeKeys.isEmpty()) {
            toast("등록할 용량을 선택해 주세요.")
            return
        }
        mutateItem(id, PhotoReviewRules::confirmVolumeChoices)
    }

    fun choosePrice(id: String, choice: PriceChoice) = mutateItem(id) {
        it.copy(priceChoice = choice, price = (if (choice == PriceChoice.OLD) it.oldPrice else it.photoPrice) ?: it.price)
    }

    fun chooseConflictPrice(id: String, price: Double) = mutateItem(id) { it.copy(conflictChoice = price, price = price) }

    fun typeInlinePrice(id: String, text: String) = setItem(id) { it.copy(draftPriceText = text) }

    fun typeInlineVolume(id: String, text: String) = setItem(id) { it.copy(draftVolumeText = text) }

    fun commitInlinePrice(id: String) {
        val x = item(id) ?: return
        val pour = review?.defaultPour ?: return
        val n = priceValue(x.draftPriceText)
        if (!validPrice(n)) {
            toast("가격을 확인해 주세요.")
            return
        }
        mutateItem(id) {
            val base = if (!it.primaryHasOption && it.options.isEmpty()) {
                // Zero-option OCR lines need a real first final option. For
                // non-whisky, pourMl remains optional (not the bar default).
                if (it.type == ReviewItemType.WHISKY) it.copy(primaryHasOption = true,
                    bottle = false, volume = pour, volumeSource = VolumeSource.DEFAULT)
                else it.copy(primaryHasOption = true, bottle = false, volume = Double.NaN)
            } else it
            base.copy(price = n, priceChoice = PriceChoice.MANUAL, draftPriceText = "")
        }
    }

    fun commitInlineVolume(id: String) {
        val x = item(id) ?: return
        val n = readNumeric(x.draftVolumeText)
        if (!validVolume(n)) {
            toast("1 ~ 999 사이의 숫자를 입력해주세요.")
            return
        }
        mutateItem(id) {
            val base = if (it.type == ReviewItemType.WHISKY && !it.primaryHasOption) {
                it.copy(primaryHasOption = true, price = 0.0)
            } else it
            base.copy(volume = n, volumeSource = VolumeSource.MANUAL, draftVolumeText = "")
        }
    }

    /** One keystroke in a detail option field. The card stays in its group until [commitOptionField]. */
    fun typeOptionField(id: String, field: OptionField, index: Int?, text: String) {
        val s = review ?: return
        val x = item(id) ?: return
        val frozen = s.typingSnapshots[id] ?: x
        set(s.copy(
            items = s.items.map { if (it.id == id) PhotoReviewRules.editOption(it, field, index, text) else it },
            typingSnapshots = s.typingSnapshots + (id to frozen),
        ))
    }

    /** The field lost focus: regroup the card, as the prototype's change event does. */
    fun commitOptionField() {
        val s = review ?: return
        if (s.typingSnapshots.isEmpty()) return
        mutate { it }
    }

    fun reclassify(id: String) {
        val pour = review?.defaultPour ?: return
        val original = item(id) ?: return
        val revised = PhotoReviewRules.reclassify(original, pour)
        val update = if (revised.linkedProductId == null) {
            // Without a catalog link, publishing resolves the target by name,
            // whether the owner switched to OTHER or back to unlinked WHISKY.
            val existing = try {
                repository.existingUnlinkedServingPrices(revised.name)
            } catch (_: Exception) {
                toast("기존 메뉴 가격을 확인하지 못했어요. 다시 시도해 주세요.")
                return
            }
            PhotoReviewRules.rebindUnlinkedPrices(revised, existing)
        } else {
            // Undoing reclassification restores the old catalog link. Do not
            // carry price candidates from an unrelated bar-local menu name.
            revised.copy(
                priceCandidates = revised.priceCandidates.filterNot { it.existing },
                chosenServingPrices = emptyMap(),
            )
        }
        mutate { s ->
            val group = if (original.type == ReviewItemType.WHISKY)
                ReviewGroup.OTHER else ReviewGroup.PENDING
            s.copy(items = s.items.map { if (it.id == id) update else it },
                show = s.show.with(group, true))
        }
    }

    fun requestExclude(id: String) {
        val s = review ?: return
        set(s.copy(modal = ReviewModal(ReviewModalType.EXCLUDE, id)))
    }

    fun confirmExclude(id: String) = mutate { s ->
        s.copy(modal = null, items = s.items.map { if (it.id == id) it.copy(excluded = true) else it })
    }

    fun unexclude(id: String) = mutate { s ->
        s.copy(show = s.show.copy(pending = true), items = s.items.map { if (it.id == id) it.copy(excluded = false) else it })
    }

    fun addOption(id: String) {
        val x = item(id) ?: return
        val pour = review?.defaultPour ?: return
        when {
            PhotoReviewRules.countOptions(x) >=
                (if (x.type == ReviewItemType.WHISKY)
                    PhotoReviewRules.MAX_PICKED_VOLUMES else PhotoReviewRules.MAX_OPTIONS) ->
                toast(if (x.type == ReviewItemType.WHISKY)
                    "용량은 최대 3가지까지 설정 가능해요."
                else "검수 옵션은 최대 10개까지 등록할 수 있어요.")
            else -> mutateItem(id) { PhotoReviewRules.addOption(it, pour) }
        }
    }

    fun removeOption(id: String, index: Int?) = mutateItem(id) { PhotoReviewRules.removeOption(it, index) }

    class Factory(private val repository: PhotoReviewRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = PhotoReviewViewModel(repository) as T
    }
}
