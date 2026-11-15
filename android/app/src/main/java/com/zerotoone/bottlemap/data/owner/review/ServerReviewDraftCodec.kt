package com.zerotoone.bottlemap.data.owner.review

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.zerotoone.bottlemap.network.ReviewDraftDto
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewRules
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import com.zerotoone.bottlemap.ui.owner.review.ReviewItem
import com.zerotoone.bottlemap.ui.owner.review.ReviewItemType
import com.zerotoone.bottlemap.ui.owner.review.ReviewOption
import com.zerotoone.bottlemap.ui.owner.review.ReviewMatch
import com.zerotoone.bottlemap.ui.owner.review.PriceChoice
import com.zerotoone.bottlemap.ui.owner.review.VolumeSource
import com.zerotoone.bottlemap.ui.owner.review.validPrice
import com.zerotoone.bottlemap.ui.owner.review.validVolume

/**
 * PR #171 §5.9: the server owns persistence, draftVersion and per-bar authorization.
 *
 * itemDecisions are partial §8.1 values for other clients. clientState is an
 * Android-specific, non-authoritative copy of unfinished field and card state.
 * Never put signed media URLs, a token, or a cached catalog snapshot in it.
 * Server validates the JSON object and its 256 KiB limit, NOT submit semantics.
 */
internal object ServerReviewDraftCodec {
    private val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
    private val stateAdapter = moshi.adapter(PhotoReviewState::class.java)
    private val mapAdapter = moshi.adapter(Map::class.java)
    private const val MAX_BYTES = 262_144

    private fun safeOption(option: ReviewOption) = option.copy(
        price = option.price.takeIf(Double::isFinite) ?: 0.0,
        volume = option.volume.takeIf(Double::isFinite) ?: 0.0,
    )

    private fun safeItem(item: ReviewItem): ReviewItem = item.copy(
        price = item.price.takeIf(Double::isFinite) ?: 0.0,
        volume = item.volume.takeIf(Double::isFinite) ?: 0.0,
        sourcePhotoUrl = null,
        sourceBox = null,
        raw = "",
        recognizedOffers = emptyList(),
        mergeSources = item.mergeSources.map {
            it.copy(sourcePhotoUrl = null, sourceBox = null, raw = "", offers = emptyList())
        },
        existingPriceByProductId = emptyMap(),
        existingServingPricesByProductId = emptyMap(),
        options = item.options.map(::safeOption),
        preMergeOptions = item.preMergeOptions.map(::safeOption),
        volumeChoices = item.volumeChoices.map(::safeOption),
        classificationSnapshot = item.classificationSnapshot?.let { snapshot ->
            snapshot.copy(
                volume = snapshot.volume.takeIf(Double::isFinite) ?: 0.0,
                primaryPrice = snapshot.primaryPrice?.takeIf(Double::isFinite),
                options = snapshot.options.map(::safeOption),
            )
        },
        searchResults = null,
    )

    private fun partialDecision(item: ReviewItem): Map<String, Any?> {
        val decision = linkedMapOf<String, Any?>("extractedItemId" to item.id)
        if (item.excluded) {
            decision["action"] = "reject"
            return decision
        }
        item.name.takeIf { it.isNotBlank() }?.let { decision["correctedProductName"] = it }
        decision["finalLineType"] = "product"
        val validOptions = PhotoReviewRules.optionSummary(item).mapNotNull { option ->
            if (!validPrice(option.price)) return@mapNotNull null
            mapOf(
                "extractedOptionId" to option.sourceOptionId,
                "optionLabel" to (if (option.bottle) "Bottle" else option.label),
                "pourMl" to (if (option.bottle) null
                    else option.volume.takeIf(::validVolume)?.toInt()),
                "priceKrw" to option.price.toInt(),
            )
        }
        if (validOptions.isNotEmpty() || !item.primaryHasOption && item.options.isEmpty())
            decision["options"] = validOptions
        if (validOptions.isNotEmpty() && item.name.isNotBlank()) {
            if (item.linkedProductId != null && item.matchConfirmed) {
                decision["action"] = "select_existing_product"
                decision["productId"] = item.linkedProductId
            } else if (item.type == ReviewItemType.OTHER ||
                (item.nameSaved && item.newConfirmed)) {
                decision["action"] = "publish_without_product"
                decision["kind"] = if (item.type == ReviewItemType.OTHER) "other" else "whisky"
            }
        }
        return decision
    }

    fun encode(state: PhotoReviewState): Map<String, Any?> {
        val safe = state.copy(
            items = state.items.map(::safeItem),
            defaultPour = state.defaultPour.takeIf(Double::isFinite) ?: 0.0,
            modal = null,
            typingSnapshots = emptyMap(),
        )
        val content: Map<String, Any?> = mapOf(
            "itemDecisions" to state.items.map(::partialDecision),
            "changeDecisions" to emptyList<Any>(),
            "clientState" to mapOf(
                "androidSchemaVersion" to 1,
                "androidStateJson" to stateAdapter.toJson(safe),
                "expandedItemIds" to state.items.filter { it.expanded }.map { it.id },
            ),
        )
        check(mapAdapter.toJson(content).toByteArray(Charsets.UTF_8).size <= MAX_BYTES) {
            "검수 초안이 256KB를 넘었어요. 입력 내용을 줄여 주세요."
        }
        return content
    }

    /** Compare the COMPLETE draft, not just Android UI state: an operator may
     * change standard decisions while leaving clientState untouched.
     * Moshi may parse JSON integers as Doubles; normalize only numeric type.
     */
    fun sameAndroidSnapshot(
        attempted: Map<String, Any?>?,
        observed: Map<String, Any?>?,
    ): Boolean {
        fun normalize(value: Any?): Any? = when (value) {
            is Number -> value.toDouble()
            is List<*> -> value.map(::normalize)
            is Map<*, *> -> value.entries.associate { (k, v) -> k to normalize(v) }
            else -> value
        }
        val left = attempted ?: return false
        val right = observed ?: return false
        if (((left["clientState"] as? Map<*, *>)?.get("androidStateJson")) !is String)
            return false
        return normalize(left) == normalize(right)
    }

    /** A regenerated §5.4 review may reorder, add or remove extracted lines.
     * Keep edits on surviving item IDs, never keep an OCR option ID that no
     * longer occurs in the new review. Changed option inventories require
     * explicit Owner selection again rather than silently dropping/adding a
     * serving. Re-grouped source lines are not safely representable here.
     */
    fun reconcileRegenerated(saved: PhotoReviewState, fresh: PhotoReviewState): PhotoReviewState? {
        val oldById = saved.items.associateBy { it.id }
        if (oldById.size != saved.items.size) return null
        val result = mutableListOf<ReviewItem>()
        for (current in fresh.items) {
            val old = oldById[current.id]
            if (old == null) {
                result += current // newly extracted: never invent an old decision
                continue
            }
            if (old.mergedInto != current.mergedInto &&
                !(old.manuallySplitGroup && current.mergeSources.isNotEmpty())) return null
            if (old.manuallySplitGroup && current.mergeSources.isEmpty() &&
                current.mergedInto == null) return null
            val liveOptions = PhotoReviewRules.optionSummary(current) +
                current.volumeChoices + current.preMergeOptions
            val liveIds = liveOptions.mapNotNull { it.sourceOptionId }.toSet()
            val oldSeen = (PhotoReviewRules.optionSummary(old) + old.volumeChoices +
                old.preMergeOptions).mapNotNull { it.sourceOptionId }.toSet()
            val selected = PhotoReviewRules.optionSummary(old)
            val kept = selected.filter { it.sourceOptionId == null || it.sourceOptionId in liveIds }
            val validChoices = old.volumeChoices.filter {
                it.sourceOptionId == null || it.sourceOptionId in liveIds
            }
            val newOptions = liveOptions.filter {
                it.sourceOptionId != null && it.sourceOptionId !in oldSeen
            }.distinctBy { it.sourceOptionId }
            val inventoryChanged = kept.size != selected.size ||
                validChoices.size != old.volumeChoices.size || newOptions.isNotEmpty()
            var retained = PhotoReviewRules.applyDefaultPour(old, fresh.defaultPour)
            if (inventoryChanged) {
                val safeRetained = kept.map { option ->
                    if (option.volumeFromDefault && !option.bottle)
                        option.copy(volume = fresh.defaultPour) else option
                }
                val candidates = (if (old.volumeChoicesConfirmed) safeRetained
                    else validChoices) + newOptions
                val first = safeRetained.firstOrNull()
                retained = retained.copy(
                    primaryHasOption = first != null,
                    price = first?.price ?: current.price,
                    volume = first?.volume ?: current.volume,
                    bottle = first?.bottle ?: current.bottle,
                    primarySourceOptionId = first?.sourceOptionId,
                    primaryOptionLabel = first?.label,
                    volumeSource = if (first?.volumeFromDefault == true)
                        VolumeSource.DEFAULT else VolumeSource.MANUAL,
                    options = safeRetained.drop(1),
                    volumeChoices = candidates.distinctBy {
                        it.sourceOptionId ?: "manual:${PhotoReviewRules.servingKey(it)}"
                    },
                    chosenVolumeKeys = if (old.volumeChoicesConfirmed)
                        safeRetained.map(PhotoReviewRules::servingKey).toSet()
                    else old.chosenVolumeKeys.intersect(
                        candidates.map(PhotoReviewRules::servingKey).toSet()),
                    volumeChoicesConfirmed = false,
                    expanded = true,
                )
            }
            result += retained.copy(
                photoIndex = current.photoIndex,
                sourceLine = current.sourceLine,
                mergedInto = current.mergedInto,
                preMergeOptions = current.preMergeOptions,
            )
        }
        return saved.copy(items = result, defaultPour = fresh.defaultPour,
            modal = null, typingSnapshots = emptyMap())
    }

    /** Null means the server draft came from another client / unknown schema. */
    fun decode(saved: ReviewDraftDto): PhotoReviewState? {
        val client = saved.content["clientState"] as? Map<*, *> ?: return null
        if ((client["androidSchemaVersion"] as? Number)?.toInt() != 1) return null
        val json = client["androidStateJson"] as? String ?: return null
        val restored = runCatching { stateAdapter.fromJson(json) }.getOrNull() ?: return null
        // clientState is advisory. Operator web may have changed standard
        // decisions without removing an older Android UI snapshot.
        val serverDecisions = saved.content["itemDecisions"] ?: return null
        val locallyDerived = runCatching { encode(restored)["itemDecisions"] }.getOrNull()
            ?: return null
        fun normalize(value: Any?): Any? = when (value) {
            is Number -> value.toDouble()
            is List<*> -> value.map(::normalize)
            is Map<*, *> -> value.entries.associate { (k, v) -> k to normalize(v) }
            else -> value
        }
        return restored.takeIf { normalize(serverDecisions) == normalize(locallyDerived) }
    }
    /**
     * Drafts written by the operator web may not contain Android's UI
     * snapshot. Reconcile their standard, partial §8.1 decisions when the
     * operation is representable without dropping an explicit changeDecision.
     * Unknown actions/options block restoration instead of being overwritten.
     */
    fun restoreStandard(saved: ReviewDraftDto, fresh: PhotoReviewState): PhotoReviewState? {
        val changes = when (val raw = saved.content["changeDecisions"]) {
            null -> emptyList<Any>()
            is List<*> -> raw
            else -> return null
        }
        if (changes.isNotEmpty()) return null // Android cannot edit ignored diffs.
        // The spec permits a draft with no itemDecisions at all; it is empty,
        // not malformed. A present non-array value still must be rejected.
        val input = when (val raw = saved.content["itemDecisions"]) {
            null -> emptyList<Any>()
            is List<*> -> raw
            else -> return null
        }
        val rows = mutableMapOf<String, Map<*, *>>()
        for (candidate in input) {
            val decision = candidate as? Map<*, *> ?: return null
            val id = decision["extractedItemId"] as? String ?: return null
            if (id in rows || fresh.items.none { it.id == id }) return null
            rows[id] = decision
        }
        val restored = fresh.items.map { original ->
            val decision = rows[original.id] ?: return@map original
            val action = decision["action"] as? String
            if (action != null && action !in setOf(
                    "reject", "confirm_non_product",
                    "select_existing_product", "publish_without_product"
                )) return null
            // Android has only an excluded/reject state. Converting an
            // operator's confirmed header/description to reject destroys intent.
            if (action == "confirm_non_product") return null
            if (decision["finalLineType"] != null &&
                decision["finalLineType"] != "product") return null
            val name = (decision["correctedProductName"] as? String)
                ?.takeIf { it.isNotBlank() } ?: original.name
            val linked = if (action == "select_existing_product")
                decision["productId"] as? String ?: return null
                else if (action == "publish_without_product") null
                else original.linkedProductId
            val category = if (action == "publish_without_product") {
                when (decision["kind"]) {
                    "other" -> ReviewItemType.OTHER
                    "whisky" -> ReviewItemType.WHISKY
                    // An incomplete operator choice must remain incomplete.
                    else -> return null
                }
            } else original.type
            val rawOptions = when (val raw = decision["options"]) {
                null -> if ("options" in decision) return null else null
                is List<*> -> raw
                else -> return null
            }
            val options = rawOptions?.map { raw ->
                val obj = raw as? Map<*, *> ?: return null
                val price = (obj["priceKrw"] as? Number)?.toDouble() ?: return null
                if (!validPrice(price)) return null
                val originalId = obj["extractedOptionId"] as? String
                val validIds = (
                    PhotoReviewRules.optionSummary(original) + original.volumeChoices +
                    original.preMergeOptions
                ).mapNotNull { it.sourceOptionId }.toSet()
                if (originalId != null && originalId !in validIds) return null
                val label = obj["optionLabel"] as? String
                val bottle = label.equals("Bottle", ignoreCase = true) || label == "병"
                val ml = (obj["pourMl"] as? Number)?.toDouble()
                if (ml != null && !validVolume(ml)) return null
                ReviewOption(
                    volume = if (bottle) 0.0 else ml ?: 0.0,
                    price = price, bottle = bottle,
                    sourceOptionId = originalId, label = label,
                )
            }
            var changed = original.copy(
                name = name,
                nameSaved = action != null || name != original.name || original.nameSaved,
                excluded = action == "reject" || action == "confirm_non_product",
                linkedProductId = linked,
                linkedProductName = if (linked == original.linkedProductId)
                    original.linkedProductName else null,
                match = if (linked != null) ReviewMatch.EXACT else ReviewMatch.NEW,
                matchConfirmed = action != null || original.matchConfirmed,
                newConfirmed = action != null || original.newConfirmed,
                type = category,
            )
            if (rawOptions != null) {
                // Explicit [] means the operator removed every OCR serving.
                // It is different from an omitted options field.
                if (options!!.isEmpty()) {
                    changed = changed.copy(
                        primaryHasOption = false, options = emptyList(),
                        primaryOptionLabel = null, primarySourceOptionId = null,
                    )
                } else {
                    val first = options.first()
                    changed = changed.copy(
                        primaryHasOption = true,
                        price = first.price, volume = first.volume,
                        bottle = first.bottle, volumeSource = VolumeSource.MANUAL,
                        primaryOptionLabel = first.label,
                        primarySourceOptionId = first.sourceOptionId,
                        options = options.drop(1), priceChoice = PriceChoice.MANUAL,
                    )
                }
            }
            changed
        }
        return fresh.copy(items = restored)
    }

}
