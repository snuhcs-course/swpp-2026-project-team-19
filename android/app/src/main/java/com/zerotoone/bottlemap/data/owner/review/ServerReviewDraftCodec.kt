package com.zerotoone.bottlemap.data.owner.review

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.zerotoone.bottlemap.network.ReviewDraftDto
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewRules
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import com.zerotoone.bottlemap.ui.owner.review.ReviewItem
import com.zerotoone.bottlemap.ui.owner.review.ReviewItemType
import com.zerotoone.bottlemap.ui.owner.review.ReviewOption
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
        if (validOptions.isNotEmpty()) decision["options"] = validOptions
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

    /** Null means the server draft came from another client / unknown schema. */
    fun decode(saved: ReviewDraftDto): PhotoReviewState? {
        val client = saved.content["clientState"] as? Map<*, *> ?: return null
        if ((client["androidSchemaVersion"] as? Number)?.toInt() != 1) return null
        val json = client["androidStateJson"] as? String ?: return null
        return runCatching { stateAdapter.fromJson(json) }.getOrNull()
    }
}
