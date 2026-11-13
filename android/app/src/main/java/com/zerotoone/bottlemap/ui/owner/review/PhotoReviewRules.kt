package com.zerotoone.bottlemap.ui.owner.review

/**
 * Pure review rules ported from BottleMap_Minimal_UX_v18.html (problems(), itemGroup(),
 * stats(), optionSummary() and the card actions). No Android or repository code here,
 * so every rule is unit tested on the JVM.
 */
object PhotoReviewRules {
    const val MAX_OPTIONS = 3

    fun optionSummary(x: ReviewItem): List<ReviewOption> =
        (if (x.primaryHasOption) listOf(ReviewOption(x.volume, x.price, x.bottle, x.primarySourceOptionId)) else emptyList()) + x.options

    fun countOptions(x: ReviewItem): Int = (if (x.primaryHasOption) 1 else 0) + x.options.size

    fun problems(x: ReviewItem): List<ReviewIssue> {
        if (x.excluded) return emptyList()
        val p = mutableListOf<ReviewIssue>()
        if (x.detailNameEditing) p += ReviewIssue.DETAIL_NAME
        if (x.type == ReviewItemType.WHISKY) {
            when {
                x.searchMode -> p += ReviewIssue.CATALOG_SEARCH
                x.match == ReviewMatch.AMBIGUOUS && !x.nameSaved -> p += ReviewIssue.MATCH
                x.match == ReviewMatch.CANDIDATE && !x.matchConfirmed -> p += ReviewIssue.CANDIDATE
                x.match == ReviewMatch.NEW && !x.nameSaved -> p += ReviewIssue.NEW
            }
            if (x.oldPrice != null && x.photoPrice != null && x.oldPrice != x.photoPrice &&
                x.priceChoice == PriceChoice.NONE
            ) p += ReviewIssue.PRICE_CHOICE
            if (x.conflictPrices.isNotEmpty() && x.conflictChoice == null) p += ReviewIssue.PHOTO_CONFLICT
            val entries = optionSummary(x)
            if (entries.isEmpty()) {
                p += ReviewIssue.PRICE
            } else {
                if (entries.any { !it.bottle && !validVolume(it.volume) }) p += ReviewIssue.VOLUME
                if (entries.any { !validPrice(it.price) }) p += ReviewIssue.PRICE
                if (entries.size > MAX_OPTIONS) p += ReviewIssue.OPTION
                val keys = entries.map { if (it.bottle) "Bottle" else numberText(it.volume) + "ml" }
                if (keys.size != keys.toSet().size) p += ReviewIssue.OPTION
            }
        } else if (!validPrice(x.price)) {
            p += ReviewIssue.PRICE
        }
        if (x.typo && !x.nameSaved) p += ReviewIssue.NAME
        if (x.name.isBlank() && ReviewIssue.NAME !in p) p += ReviewIssue.NAME
        return p.distinct()
    }

    fun itemGroup(x: ReviewItem): ReviewGroup = when {
        x.excluded -> ReviewGroup.EXCLUDED
        problems(x).isNotEmpty() -> ReviewGroup.PENDING
        x.type == ReviewItemType.OTHER -> ReviewGroup.OTHER
        else -> ReviewGroup.READY
    }

    /** The group a card is drawn in: frozen while one of its fields is being typed in. */
    fun displayGroup(state: PhotoReviewState, x: ReviewItem): ReviewGroup =
        itemGroup(state.typingSnapshots[x.id] ?: x)

    fun stats(state: PhotoReviewState): ReviewStats {
        val all = state.items
        val byGroup = all.groupBy { displayGroup(state, it) }
        val required = all.filter { it.required || problems(it).isNotEmpty() }
        val done = required.count { it.excluded || problems(it).isEmpty() }
        val total = required.size
        val noDefault = !validVolume(state.defaultPour)
        val pending = byGroup[ReviewGroup.PENDING].orEmpty()
        val ready = byGroup[ReviewGroup.READY].orEmpty()
        val other = byGroup[ReviewGroup.OTHER].orEmpty()
        return ReviewStats(
            pending = pending,
            ready = ready,
            other = other,
            excluded = byGroup[ReviewGroup.EXCLUDED].orEmpty(),
            total = total,
            done = done,
            percent = if (total > 0) Math.round(done.toDouble() / total * 100).toInt() else 100,
            canPublish = pending.isEmpty() && (ready.size + other.size) > 0 && !noDefault,
            noDefault = noDefault,
        )
    }

    /** Collapsed cards show the first valid price; nothing while a price conflict is open. */
    fun itemDisplayPrice(x: ReviewItem): Double? =
        if (x.conflictPrices.isNotEmpty() && x.conflictChoice == null) null
        else optionSummary(x).firstOrNull { validPrice(it.price) }?.price ?: x.price

    /** Position of the line among the lines of the same photo, from 1. */
    fun photoLine(state: PhotoReviewState, x: ReviewItem): Int =
        state.items.filter { it.photoIndex == x.photoIndex }.indexOfFirst { it.id == x.id } + 1

    fun sourceLocation(state: PhotoReviewState, x: ReviewItem): String =
        if (x.hasSourceBox) "${x.photoIndex}번째 장 ${photoLine(state, x)}번째 줄"
        else "${x.photoIndex}번째 장 · 위치 정보 없음"

    private val koreanCounts = mapOf(2 to "두", 3 to "세", 4 to "네", 5 to "다섯", 6 to "여섯",
        7 to "일곱", 8 to "여덟", 9 to "아홉", 10 to "열")

    /** "같은 위스키가 두 줄 있어 하나로 합쳤어요." with the real number of merged lines. */
    fun mergedNotice(x: ReviewItem): String? {
        val count = 1 + x.mergeSources.size
        if (count < 2) return null
        val label = koreanCounts[count]?.let { "$it 줄" } ?: "${count}줄"
        return "같은 위스키가 $label 있어 하나로 합쳤어요."
    }

    /** The OCR snapshot shown under the photo: recognised volumes and prices. */
    fun recognizedOffers(x: ReviewItem): List<RecognizedOffer> {
        val source = x.recognizedOffers + x.mergeSources.flatMap { it.offers }
        val sameVolumeConflict = x.mergeSources.isNotEmpty() && x.conflictPrices.isNotEmpty() &&
            x.conflictChoice == null
        val entries = if (sameVolumeConflict) {
            source.associateBy { o ->
                when {
                    o.bottle -> "Bottle"
                    (o.volumeMl ?: 0) > 0 -> "${o.volumeMl}ml"
                    else -> "none"
                }
            }.values.toList()
        } else source
        return entries.ifEmpty { listOf(RecognizedOffer()) }
    }

    /** Show the configured bar pour beside the OCR price when the photo omits size. */
    fun offerVolumeLabel(o: RecognizedOffer, defaultPourMl: Double? = null): String = when {
        o.bottle -> "Bottle"
        (o.volumeMl ?: 0) > 0 -> "${o.volumeMl}ml"
        defaultPourMl != null && validVolume(defaultPourMl) ->
            "${defaultPourMl.toInt()}ml"
        else -> ""
    }

    /** Price text of a recognised offer, or null when the conflict hides it. */
    fun offerPriceLabel(x: ReviewItem, o: RecognizedOffer): String? {
        val sameVolumeConflict = x.mergeSources.isNotEmpty() && x.conflictPrices.isNotEmpty() &&
            x.conflictChoice == null
        if (sameVolumeConflict) return null
        return when {
            x.conflictPrices.isNotEmpty() && x.conflictChoice == null -> "-"
            (o.priceKrw ?: 0) > 0 -> won(o.priceKrw!!.toDouble())
            else -> "가격 미인식"
        }
    }

    // ---- Product link transitions (decisions 1, 2, 7) ----

    fun markLinked(x: ReviewItem, product: CatalogProduct): ReviewItem {
        val old = x.existingPriceByProductId[product.productId]
        val photo = x.photoPrice
        val changed = old != null && photo != null && old != photo
        return x.copy(
        oldPrice = old,
        priceChoice = if (x.priceChoice == PriceChoice.MANUAL) PriceChoice.MANUAL
            else if (changed) PriceChoice.NONE else PriceChoice.PHOTO,
        price = if (x.priceChoice == PriceChoice.MANUAL) x.price else photo ?: x.price,
        linkedProductId = product.productId,
        linkedProductName = product.name,
        match = ReviewMatch.EXACT,
        matchConfirmed = true,
        nameSaved = true,
        newConfirmed = false,
        searchMode = false,
        searchResults = null,
        searchDraft = "",
        selectedCandidateId = null,
        selectedSearchId = null,
        nameEditMode = false,
        operatorPending = false,
        operatorReason = null,
        // The photo text and the menu-board name are never overwritten.
    )
    }

    /** "찾는 위스키가 없어요": publish without a product; an operator links it later. */
    fun markAsNewForOperator(x: ReviewItem, typed: String): ReviewItem {
        val name = typed.trim().ifBlank { x.newProductName ?: x.name }
        return x.copy(
            linkedProductId = null,
            linkedProductName = null,
            match = ReviewMatch.NEW,
            newConfirmed = false,
            nameSaved = false,
            matchConfirmed = false,
            operatorPending = true,
            operatorReason = OperatorReason.NEW,
            newProductName = name,
            searchMode = false,
            searchResults = null,
            searchDraft = "",
            selectedCandidateId = null,
            selectedSearchId = null,
            nameEditMode = true,
            reviewNameDraft = name,
        )
    }

    enum class RematchOutcome { SAME, CHANGED, OPERATOR, OTHER }

    /**
     * Decision 2: after the owner renames a whisky line, match the new name again.
     * One exact product keeps or changes the link (a change goes to the operator);
     * none or several leave the line unlinked for the operator.
     */
    fun applyRematch(x: ReviewItem, exactMatches: List<CatalogProduct>): Pair<ReviewItem, RematchOutcome> {
        if (x.type != ReviewItemType.WHISKY) return x to RematchOutcome.OTHER
        val oldProductId = x.linkedProductId
        if (exactMatches.size == 1) {
            val linked = markLinked(x, exactMatches[0])
            return if (oldProductId != null && oldProductId != exactMatches[0].productId) {
                linked.copy(operatorPending = true, operatorReason = OperatorReason.CHANGED) to RematchOutcome.CHANGED
            } else linked to RematchOutcome.SAME
        }
        return x.copy(
            linkedProductId = null,
            linkedProductName = null,
            match = ReviewMatch.NEW,
            newProductName = x.name,
            newConfirmed = true,
            matchConfirmed = true,
            nameSaved = true,
            operatorPending = true,
            operatorReason = if (oldProductId != null) OperatorReason.UNLINKED else OperatorReason.NEW,
            searchMode = false,
            searchResults = null,
            searchDraft = "",
        ) to RematchOutcome.OPERATOR
    }

    /** Decision 7: a chosen product whose age or edition differs goes to the operator. */
    fun linkChosenProduct(x: ReviewItem, product: CatalogProduct, operatorCheck: Boolean): ReviewItem {
        val linked = markLinked(x, product)
        return if (operatorCheck) {
            linked.copy(operatorPending = true, operatorReason = OperatorReason.SELECTED_PRODUCT_CONFLICT)
        } else linked
    }

    // ---- Classification ----

    fun reclassify(x: ReviewItem, defaultPour: Double): ReviewItem {
        val target = if (x.type == ReviewItemType.WHISKY) ReviewItemType.OTHER else ReviewItemType.WHISKY
        val prev = x.classificationSnapshot
        val changed = if (prev != null && prev.type == target) {
            x.copy(
                volume = prev.volume, volumeSource = prev.volumeSource, bottle = prev.bottle,
                primaryHasOption = prev.primaryHasOption, options = prev.options,
                primarySourceOptionId = prev.primarySourceOptionId, match = prev.match,
                matchConfirmed = prev.matchConfirmed, nameSaved = prev.nameSaved,
                newConfirmed = prev.newConfirmed, linkedProductId = prev.linkedProductId,
                linkedProductName = prev.linkedProductName, newProductName = prev.newProductName,
                candidates = prev.candidates, rawOptionEdits = prev.rawOptionEdits,
                classificationSnapshot = null,
            )
        } else {
            val snapshot = ClassificationSnapshot(
                type = x.type, volume = x.volume, volumeSource = x.volumeSource, bottle = x.bottle,
                primaryHasOption = x.primaryHasOption, options = x.options, match = x.match,
                matchConfirmed = x.matchConfirmed, nameSaved = x.nameSaved, newConfirmed = x.newConfirmed,
                linkedProductId = x.linkedProductId, linkedProductName = x.linkedProductName,
                newProductName = x.newProductName, candidates = x.candidates,
                rawOptionEdits = x.rawOptionEdits,
                primarySourceOptionId = x.primarySourceOptionId,
            )
            if (target == ReviewItemType.OTHER) {
                x.copy(
                    classificationSnapshot = snapshot, volume = Double.NaN, options = emptyList(),
                    primarySourceOptionId = null, primaryHasOption = false, bottle = false,
                    // A non-whisky is never linked to the canonical whisky catalog.
                    // The classification snapshot restores the prior link on undo.
                    linkedProductId = null, linkedProductName = null,
                    match = ReviewMatch.NEW, matchConfirmed = true, newConfirmed = true,
                    nameSaved = true, operatorPending = false, operatorReason = null,
                )
            } else {
                x.copy(classificationSnapshot = snapshot, volume = defaultPour, volumeSource = VolumeSource.DEFAULT,
                    options = emptyList(), primaryHasOption = true, primarySourceOptionId = null,
                    bottle = false, match = ReviewMatch.NEW,
                    newConfirmed = false, nameSaved = false, matchConfirmed = false, newProductName = x.name)
            }
        }
        return changed.copy(type = target, expanded = false)
    }

    // ---- Option editing ----

    fun rawKey(field: OptionField, index: Int?): String =
        if (index == null) "${field.key}:main" else "option-${field.key}:$index"

    enum class OptionField(val key: String) { VOLUME("volume"), PRICE("price") }

    /** Applies one keystroke in an option field; invalid text stays visible in [ReviewItem.rawOptionEdits]. */
    fun editOption(x: ReviewItem, field: OptionField, index: Int?, text: String): ReviewItem {
        val n = if (field == OptionField.PRICE) priceValue(text) else readNumeric(text)
        val valid = if (field == OptionField.PRICE) validPrice(n) else validVolume(n)
        val key = rawKey(field, index)
        val raw = if (valid) x.rawOptionEdits - key else x.rawOptionEdits + (key to text)
        val edited = x.copy(rawOptionEdits = raw)
        if (x.type != ReviewItemType.WHISKY) {
            return if (field == OptionField.PRICE && index == null) edited.copy(price = n) else edited
        }
        return when {
            index == null && field == OptionField.PRICE -> edited.copy(
                price = n,
                priceChoice = if (x.oldPrice != null) (if (validPrice(n)) PriceChoice.MANUAL else PriceChoice.NONE)
                else x.priceChoice,
            )
            index == null -> edited.copy(volume = n, volumeSource = VolumeSource.MANUAL)
            else -> {
                val option = x.options.getOrNull(index) ?: return edited
                val updated = if (field == OptionField.PRICE) option.copy(price = n) else option.copy(volume = n)
                edited.copy(options = x.options.toMutableList().also { it[index] = updated })
            }
        }
    }

    /** Text shown in an option field: the invalid text if any, otherwise the stored number. */
    fun optionFieldText(x: ReviewItem, field: OptionField, index: Int?): String {
        x.rawOptionEdits[rawKey(field, index)]?.let { return it }
        val value = when {
            index == null && field == OptionField.PRICE -> x.price
            index == null -> x.volume
            field == OptionField.PRICE -> x.options.getOrNull(index)?.price ?: Double.NaN
            else -> x.options.getOrNull(index)?.volume ?: Double.NaN
        }
        return numberText(value)
    }

    fun toggleBottle(x: ReviewItem, index: Int?, defaultPour: Double): ReviewItem {
        if (index == null) {
            val bottle = !x.bottle
            return if (bottle) x.copy(bottle = true, volume = 0.0, rawOptionEdits = x.rawOptionEdits - "volume:main")
            else x.copy(bottle = false, volume = if (x.volume > 0) x.volume else defaultPour)
        }
        val op = x.options.getOrNull(index) ?: return x
        val bottle = !op.bottle
        val updated = if (bottle) op.copy(bottle = true, volume = 0.0) else op.copy(bottle = false,
            volume = if (op.volume > 0) op.volume else 0.0)
        val raw = if (bottle) x.rawOptionEdits - "option-volume:$index" else x.rawOptionEdits
        return x.copy(options = x.options.toMutableList().also { it[index] = updated }, rawOptionEdits = raw)
    }

    fun addOption(x: ReviewItem, defaultPour: Double): ReviewItem =
        if (!x.primaryHasOption) {
            x.copy(primaryHasOption = true, bottle = false, volume = defaultPour,
                volumeSource = VolumeSource.DEFAULT, price = 0.0, expanded = true)
        } else x.copy(options = x.options + ReviewOption(), expanded = true)

    fun removeOption(x: ReviewItem, index: Int?): ReviewItem =
        if (index == null) x.copy(primaryHasOption = false, primarySourceOptionId = null, expanded = true)
        else x.copy(options = x.options.filterIndexed { i, _ -> i != index }, expanded = true)

    // ---- Publish summary ----

    data class PublishSummary(val changedPrices: Int, val unlinkedNew: Int, val merged: Int, val operatorChecks: Int)

    fun publishSummary(state: PhotoReviewState) = PublishSummary(
        changedPrices = state.items.count { it.priceChoice == PriceChoice.PHOTO },
        unlinkedNew = state.items.count { it.match == ReviewMatch.NEW && !it.excluded && it.linkedProductId == null },
        merged = state.items.count { it.mergeSources.isNotEmpty() && !it.excluded },
        operatorChecks = state.items.count { it.operatorPending && !it.excluded },
    )
}
