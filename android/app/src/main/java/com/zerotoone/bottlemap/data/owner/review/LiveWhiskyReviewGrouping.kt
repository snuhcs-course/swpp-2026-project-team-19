package com.zerotoone.bottlemap.data.owner.review

import com.zerotoone.bottlemap.data.owner.MockOwnerSnapshot
import com.zerotoone.bottlemap.data.owner.servingIdentityKey
import com.zerotoone.bottlemap.network.ReviewItemDto
import com.zerotoone.bottlemap.ui.owner.review.MergedLine
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewRules
import com.zerotoone.bottlemap.ui.owner.review.RecognizedOffer
import com.zerotoone.bottlemap.ui.owner.review.ReviewItem
import com.zerotoone.bottlemap.ui.owner.review.ReviewItemType
import com.zerotoone.bottlemap.ui.owner.review.ReviewOption
import com.zerotoone.bottlemap.ui.owner.review.ReviewPriceCandidate
import com.zerotoone.bottlemap.ui.owner.review.PriceChoice
import com.zerotoone.bottlemap.ui.owner.review.validVolume
import java.text.Normalizer
import java.util.Locale

/** One whisky product -> one visible Owner review card, even when OCR returns
 * one extractedItemId per price line. Server item IDs still receive separate
 * final decisions: the master publishes all reviewed options; merged children
 * are rejected only after their nonduplicate servings have been carried into
 * the master. No Backend/AI grouping is assumed.
 */
internal fun groupLiveWhiskyReview(
    inputs: List<Pair<ReviewItemDto, ReviewItem>>,
    snapshot: MockOwnerSnapshot,
    barId: String,
): List<ReviewItem> {
    fun identity(input: Pair<ReviewItemDto, ReviewItem>): String {
        val (dto, item) = input
        if (item.type != ReviewItemType.WHISKY ||
            dto.effectiveLineType !in setOf("product", "unknown")) {
            return "line:${item.id}"
        }
        val productId = item.linkedProductId ?: dto.proposedProductId ?:
            dto.candidates.singleOrNull()?.productId
        if (!productId.isNullOrBlank()) return "product:$productId"
        val name = Normalizer.normalize(item.name, Normalizer.Form.NFKC)
            .lowercase(Locale.ROOT).replace(Regex("""\s+"""), "")
        return if (name.isNotBlank()) "name:$name" else "line:${item.id}"
    }
    val grouped = inputs.groupBy(::identity)
    return grouped.values.flatMap { batch ->
        val head = batch.first().second
        if (head.type != ReviewItemType.WHISKY) return@flatMap batch.map { it.second }
        val allOptions = batch.flatMap { (_, item) ->
            PhotoReviewRules.optionSummary(item).map { option -> item.id to option }
        }
        if (allOptions.isEmpty()) return@flatMap batch.map { it.second }

        fun key(option: ReviewOption): String =
            servingIdentityKey(if (option.bottle) null
                else option.volume.takeIf(::validVolume)?.toInt(),
                if (option.bottle) "Bottle" else option.label)
        val firstByServing = allOptions.groupBy { key(it.second) }
        val unique = firstByServing.map { (_, offers) ->
            val (lineId, option) = offers.first()
            // OCR source IDs are scoped to ONE extractedItemId. A serving
            // moved from another OCR line becomes a manually corrected final
            // option of the master; never send the child's foreign ID.
            option.copy(sourceOptionId = option.sourceOptionId.takeIf {
                lineId == head.id
            })
        }

        val productId = batch.firstNotNullOfOrNull { (dto, item) ->
            item.linkedProductId ?: dto.proposedProductId
        }
        val existing = snapshot.menuItems.filter { row ->
            row.barId == barId && row.productId == productId
        }.flatMap { row -> row.options }
        val candidates = allOptions.mapNotNull { (lineId, option) ->
            val price = option.price.takeIf {
                it.isFinite() && it > 0 && it == kotlin.math.floor(it)
            }?.toInt() ?: return@mapNotNull null
            ReviewPriceCandidate(
                servingKey = key(option),
                volumeMl = option.volume.takeIf(::validVolume)?.toInt(),
                bottle = option.bottle,
                label = option.label,
                priceKrw = price,
                sourceItemId = lineId,
            )
        } + existing.map { option ->
            ReviewPriceCandidate(
                servingKey = servingIdentityKey(option.pourMl, option.label),
                volumeMl = option.pourMl,
                bottle = com.zerotoone.bottlemap.data.owner.isBottleServingLabel(option.label),
                label = option.label,
                priceKrw = option.priceKrw,
                existing = true,
            )
        } + batch.flatMap { (_, card) ->
            // Grouping recomputes OCR candidates; preserve the saved local
            // prices that the mapper matched by bar + normalized name.
            card.priceCandidates.filter { it.existing }
        }.distinctBy { listOf(it.servingKey, it.priceKrw, it.existing, it.sourceItemId) }
        // Keep every OCR candidate (including nonconflicting sizes) so a
        // product linked later can compare its EXISTING bar price without
        // losing the original 잔/샷 source labels. Only differing prices
        // become a visible issue via pendingPriceServings().
        val tooMany = unique.size > 3
        val first = unique.first()
        val master = head.copy(
            primaryHasOption = !tooMany,
            volume = first.volume,
            price = first.price,
            bottle = first.bottle,
            primarySourceOptionId = if (tooMany) null else first.sourceOptionId,
            primaryOptionLabel = first.label,
            options = if (tooMany) emptyList() else unique.drop(1),
            // Price conflicts are expressed once in a single card instead of
            // the prior PRICE_CHOICE/PHOTO_CONFLICT/DUPLICATE_PRODUCT rows.
            oldPrice = null, priceChoice = PriceChoice.PHOTO,
            photoPrice = null, conflictPrices = emptyList(), conflictChoice = null,
            priceCandidates = candidates,
            chosenServingPrices = emptyMap(),
            volumeChoices = if (tooMany) unique else emptyList(),
            chosenVolumeKeys = emptySet(),
            volumeChoicesConfirmed = !tooMany,
            preMergeOptions = if (batch.size > 1) PhotoReviewRules.optionSummary(head)
                else emptyList(),
            mergeSources = batch.drop(1).map { (_, other) ->
                MergedLine(
                    photoIndex = other.photoIndex,
                    recognizedName = other.recognizedName,
                    raw = other.raw,
                    offers = other.recognizedOffers,
                    sourceItemId = other.id,
                    sourcePhotoUrl = other.sourcePhotoUrl,
                    sourceBox = other.sourceBox,
                    hasSourceBox = other.hasSourceBox,
                    sourceLine = other.sourceLine.takeIf { it > 0 } ?: 1,
                )
            },
        )
        val children = batch.drop(1).map { (_, item) ->
            item.copy(excluded = true, required = false, mergedInto = head.id)
        }
        listOf(master) + children
    }
}
