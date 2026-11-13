package com.zerotoone.bottlemap.ui.owner.review

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.zerotoone.bottlemap.network.menuWriteErrorText
import com.zerotoone.bottlemap.data.owner.review.PhotoReviewRepository
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewRules.OptionField
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewRules.RematchOutcome
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch

sealed interface PhotoReviewLoad {
    data object Loading : PhotoReviewLoad
    data class Error(val message: String) : PhotoReviewLoad
    data class Ready(val review: PhotoReviewState) : PhotoReviewLoad
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

    private val _events = Channel<PhotoReviewEvent>(Channel.BUFFERED)
    val events = _events.receiveAsFlow()

    init {
        reload()
    }

    fun reload() {
        if (_publishing.value) return
        _load.value = PhotoReviewLoad.Loading
        viewModelScope.launch {
            _load.value = try {
                PhotoReviewLoad.Ready(repository.loadReview())
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                PhotoReviewLoad.Error(error.message ?: "검수 정보를 불러오지 못했어요.")
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

    private fun saveDraft(state: PhotoReviewState) {
        viewModelScope.launch { runCatching { repository.saveDraft(state) } }
    }

    // ---- Screen-level actions ----

    fun leave() {
        if (_publishing.value) return
        review?.let { set(it.copy(modal = null)) }
        _events.trySend(PhotoReviewEvent.Leave)
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

    fun confirmPublish() {
        if (_publishing.value) return
        val s = review ?: return
        if (s.modal?.type != ReviewModalType.PUBLISH) return
        if (!PhotoReviewRules.stats(s).canPublish) return
        // Guard before launching: rapid taps must never submit two atomic
        // review-and-apply calls for the same server reviewVersion.
        _publishing.value = true
        viewModelScope.launch {
            try {
                repository.publish(s)
                _publishing.value = false
                leave()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                set(s.copy(modal = null))
                toast(menuWriteErrorText(error))
            } finally {
                _publishing.value = false
            }
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
        if (x.searchResults?.any { it.productId == productId } == true) {
            mutateItem(id) { it.copy(selectedSearchId = productId) }
        }
    }

    fun confirmSelectedSearch(id: String) {
        val x = item(id) ?: return
        val product = x.searchResults?.firstOrNull { it.productId == x.selectedSearchId }
        if (product == null) toast("위스키를 먼저 선택해 주세요.") else linkChosen(x, product)
    }

    /** Decision 7: link at once; a conflicting age or edition goes to the operator. */
    private fun linkChosen(x: ReviewItem, product: CatalogProduct) {
        viewModelScope.launch {
            val operatorCheck = runCatching { repository.needsOperatorCheck(x, product) }.getOrDefault(false)
            mutateItem(x.id) { PhotoReviewRules.linkChosenProduct(it, product, operatorCheck) }
            if (operatorCheck) toast("위스키를 연결했어요. 운영자 확인 대상으로 전달돼요.")
        }
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
        if (proposed.isEmpty()) {
            toast("이름을 입력해 주세요.")
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
        if (x.name.isBlank()) {
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
        if (proposed.isEmpty()) {
            toast("메뉴 이름을 입력해 주세요.")
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
            mutateItem(id, rename)
            return
        }
        viewModelScope.launch {
            val matches = runCatching { repository.exactMatches(name) }.getOrDefault(emptyList())
            var outcome = RematchOutcome.OTHER
            mutateItem(id) {
                val (rematched, result) = PhotoReviewRules.applyRematch(rename(it), matches)
                outcome = result
                rematched
            }
            if (outcome == RematchOutcome.OPERATOR) toast(operatorToast)
        }
    }

    fun startCatalogSearch(id: String) = mutateItem(id) {
        it.copy(searchMode = true, searchDraft = it.searchDraft.ifEmpty { it.name }, searchResults = null,
            selectedCandidateId = null, selectedSearchId = null, nameEditMode = false)
    }

    fun typeCatalogQuery(id: String, text: String) =
        setItem(id) { it.copy(searchDraft = text, searchResults = null, selectedSearchId = null) }

    fun searchCatalog(id: String) {
        val x = item(id) ?: return
        val query = x.searchDraft.trim()
        if (query.isEmpty()) {
            toast("검색할 위스키 이름을 입력해 주세요.")
            return
        }
        viewModelScope.launch {
            val results = runCatching { repository.searchCatalog(query) }.getOrElse {
                toast("검색하지 못했어요. 다시 시도해 주세요.")
                return@launch
            }
            mutateItem(id) { it.copy(searchDraft = query, searchResults = results, selectedSearchId = null) }
        }
    }

    fun registerAsNew(id: String) {
        mutateItem(id) { PhotoReviewRules.markAsNewForOperator(it, it.searchDraft.ifEmpty { it.name }) }
        _events.trySend(PhotoReviewEvent.FocusReviewName(id))
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
        mutate { s ->
            val target = item(id)?.type ?: return@mutate s
            val group = if (target == ReviewItemType.WHISKY) ReviewGroup.OTHER else ReviewGroup.PENDING
            s.copy(items = s.items.map { if (it.id == id) PhotoReviewRules.reclassify(it, pour) else it },
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
            PhotoReviewRules.countOptions(x) >= PhotoReviewRules.MAX_OPTIONS ->
                toast("검수 옵션은 최대 10개까지 등록할 수 있어요.")
            else -> mutateItem(id) { PhotoReviewRules.addOption(it, pour) }
        }
    }

    fun removeOption(id: String, index: Int?) = mutateItem(id) { PhotoReviewRules.removeOption(it, index) }

    class Factory(private val repository: PhotoReviewRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = PhotoReviewViewModel(repository) as T
    }
}
