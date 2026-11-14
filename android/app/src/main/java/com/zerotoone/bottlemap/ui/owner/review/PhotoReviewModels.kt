package com.zerotoone.bottlemap.ui.owner.review

import java.text.NumberFormat
import java.util.Locale

/**
 * UI model of the one-page photo-menu review (BottleMap_Minimal_UX_v18.html, flow 02).
 *
 * This is a screen model, not an API DTO. A repository maps whatever the server sends
 * into it, so the composables never change when the data source changes.
 *
 * Numbers follow the HTML prototype: a volume or price the owner typed but that is not a
 * valid number is `NaN`, and "no value" is `0` or `NaN`. Validation is always done with
 * [validVolume] and [validPrice], never by comparing with null.
 */
enum class ReviewItemType { WHISKY, OTHER }

/** How the line was matched to the catalog when the review started. */
enum class ReviewMatch { EXACT, AMBIGUOUS, CANDIDATE, NEW, NONE }

enum class VolumeSource { PHOTO, DEFAULT, MANUAL }

enum class PriceChoice { NONE, OLD, PHOTO, MANUAL }

/** Why a line goes to the operator queue after publication (decisions 1, 2 and 7). */
enum class OperatorReason { NEW, CHANGED, UNLINKED, SELECTED_PRODUCT_CONFLICT }

enum class ReviewGroup { PENDING, READY, OTHER, EXCLUDED }

/** One problem shown as an inline row on a card that still needs the owner. */
enum class ReviewIssue {
    DETAIL_NAME, CATALOG_SEARCH, MATCH, CANDIDATE, NEW, PRICE_CHOICE, PHOTO_CONFLICT,
    PRICE, VOLUME, OPTION, NAME, DUPLICATE_PRICE,
}

data class CatalogProduct(val productId: String, val name: String, val isActive: Boolean = true)

/** A value read from the photo. Read-only: owner corrections never overwrite it. */
data class RecognizedOffer(val volumeMl: Int? = null, val bottle: Boolean = false, val priceKrw: Int? = null)

/** Another menu line that was merged into this card because it is the same product. */
data class MergedLine(
    val photoIndex: Int,
    val recognizedName: String,
    val raw: String,
    val offers: List<RecognizedOffer>,
    val sourceItemId: String? = null,
    val sourcePhotoUrl: String? = null,
    val sourceBox: List<Int>? = null,
    val hasSourceBox: Boolean = true,
    val sourceLine: Int = 1,
)

/** Competing OCR and existing-bar prices for one canonical serving size. */
data class ReviewPriceCandidate(
    val servingKey: String,
    val volumeMl: Int? = null,
    val bottle: Boolean = false,
    val label: String? = null,
    val priceKrw: Int,
    val existing: Boolean = false,
    val sourceItemId: String? = null,
)

/** One serving option the owner will publish. */
data class ReviewOption(
    val volume: Double = 0.0, val price: Double = 0.0, val bottle: Boolean = false,
    // Real extracted option identity and label survive edits/reclassification.
    val sourceOptionId: String? = null,
    val label: String? = null,
    /** OCR omitted a glass pour; update this if the bar default changes. */
    val volumeFromDefault: Boolean = false,
)

/** The fields that "분류 변경" stores so that changing back restores the original options. */
data class ClassificationSnapshot(
    val type: ReviewItemType,
    val volume: Double,
    val volumeSource: VolumeSource,
    val bottle: Boolean,
    val primaryHasOption: Boolean,
    val options: List<ReviewOption>,
    val match: ReviewMatch,
    val matchConfirmed: Boolean,
    val nameSaved: Boolean,
    val newConfirmed: Boolean,
    val linkedProductId: String?,
    val linkedProductName: String?,
    val newProductName: String?,
    val candidates: List<CatalogProduct>,
    val rawOptionEdits: Map<String, String>,
    val primarySourceOptionId: String? = null,
    val primaryOptionLabel: String? = null,
)

data class ReviewItem(
    val id: String,
    val name: String,
    val type: ReviewItemType = ReviewItemType.WHISKY,
    val match: ReviewMatch = ReviewMatch.EXACT,
    val matchConfirmed: Boolean = true,
    val newConfirmed: Boolean = true,
    val linkedProductId: String? = null,
    val linkedProductName: String? = null,
    val newProductName: String? = null,
    // The first option is stored inline, as in the prototype ("primary option").
    val price: Double = 0.0,
    val volume: Double = 30.0,
    val bottle: Boolean = false,
    val volumeSource: VolumeSource = VolumeSource.PHOTO,
    val primaryHasOption: Boolean = true,
    val options: List<ReviewOption> = emptyList(),
    // Existing menu price versus the price read from the new photo.
    val oldPrice: Double? = null,
    val photoPrice: Double? = null,
    val priceChoice: PriceChoice = PriceChoice.NONE,
    // Same volume, different prices on merged lines (decision 4).
    val conflictPrices: List<Double> = emptyList(),
    val conflictChoice: Double? = null,
    val typo: Boolean = false,
    val nameConfirmed: Boolean = true,
    val nameSaved: Boolean = match != ReviewMatch.NEW && match != ReviewMatch.AMBIGUOUS,
    val reviewNameDraft: String? = null,
    val nameEditMode: Boolean = false,
    val searchMode: Boolean = false,
    val searchDraft: String = "",
    val searchResults: List<CatalogProduct>? = null,
    val selectedCandidateId: String? = null,
    val selectedSearchId: String? = null,
    val detailNameEditing: Boolean = false,
    val detailNameDraft: String? = null,
    val candidates: List<CatalogProduct> = emptyList(),
    val excluded: Boolean = false,
    val expanded: Boolean = false,
    val draftPriceText: String = "",
    val draftVolumeText: String = "",
    val raw: String = "",
    val photoIndex: Int = 1,
    val sourceLine: Int = 0,
    val hasSourceBox: Boolean = true,
    val mergeSources: List<MergedLine> = emptyList(),
    val operatorPending: Boolean = false,
    val operatorReason: OperatorReason? = null,
    val classificationSnapshot: ClassificationSnapshot? = null,
    val rawOptionEdits: Map<String, String> = emptyMap(),
    /** Counts toward "검수 n/m 완료" even after it is resolved. */
    val required: Boolean = false,
    val recognizedName: String = name,
    val recognizedOffers: List<RecognizedOffer> = listOf(RecognizedOffer(priceKrw = price.takeIf { it > 0 }?.toInt())),
    // Production-only signed image URL and normalized extraction box.
    // Mock scenarios leave them null, retaining their exact visual fixtures.
    val sourcePhotoUrl: String? = null,
    val sourceBox: List<Int>? = null,
    /** First OCR option identity, kept separate from displayed price/volume. */
    val primarySourceOptionId: String? = null,
    val primaryOptionLabel: String? = null,
    /** Current bar prices for matching the first photographed serving. */
    val existingPriceByProductId: Map<String, Double> = emptyMap(),
    /** Every saved serving of each catalog product, not just the first OCR ml. */
    val existingServingPricesByProductId: Map<String, List<ReviewPriceCandidate>> = emptyMap(),
    /** When multiple OCR rows refer to one product, only the master card
     * is shown; child rows are submitted as reject, never silently published.
     */
    val mergedInto: String? = null,
    /** Exact master OCR options before automatic multi-line grouping. */
    val preMergeOptions: List<ReviewOption> = emptyList(),
    /** Persist an explicit owner split across process death. */
    val manuallySplitGroup: Boolean = false,
    val priceCandidates: List<ReviewPriceCandidate> = emptyList(),
    val chosenServingPrices: Map<String, Int> = emptyMap(),
    /** More than three detected servings: explicitly select up to three. */
    val volumeChoices: List<ReviewOption> = emptyList(),
    val chosenVolumeKeys: Set<String> = emptySet(),
    val volumeChoicesConfirmed: Boolean = true,
)

enum class ReviewModalType { SOURCE_PHOTO, PUBLISH, EXCLUDE }

data class ReviewModal(val type: ReviewModalType, val itemId: String? = null, val mergeIndex: Int? = null)

data class GroupVisibility(
    val pending: Boolean = true,
    val ready: Boolean = true,
    val other: Boolean = true,
    val excluded: Boolean = false,
) {
    operator fun get(group: ReviewGroup) = when (group) {
        ReviewGroup.PENDING -> pending
        ReviewGroup.READY -> ready
        ReviewGroup.OTHER -> other
        ReviewGroup.EXCLUDED -> excluded
    }

    fun with(group: ReviewGroup, open: Boolean) = when (group) {
        ReviewGroup.PENDING -> copy(pending = open)
        ReviewGroup.READY -> copy(ready = open)
        ReviewGroup.OTHER -> copy(other = open)
        ReviewGroup.EXCLUDED -> copy(excluded = open)
    }
}

data class PhotoReviewState(
    val items: List<ReviewItem> = emptyList(),
    /** The bar's default glass size. 0 means not set (decision 6 makes it required). */
    val defaultPour: Double = 30.0,
    val draftDefaultPourText: String = "",
    val show: GroupVisibility = GroupVisibility(),
    val modal: ReviewModal? = null,
    /**
     * Cards whose detail fields are being typed in keep their header, issues and group as
     * they were when typing started, until the field is left (the prototype re-renders only
     * on the change event).
     */
    val typingSnapshots: Map<String, ReviewItem> = emptyMap(),
)

data class ReviewStats(
    val pending: List<ReviewItem>,
    val ready: List<ReviewItem>,
    val other: List<ReviewItem>,
    val excluded: List<ReviewItem>,
    val total: Int,
    val done: Int,
    val percent: Int,
    val canPublish: Boolean,
    val noDefault: Boolean,
)

// ---- Number rules (same as the prototype) ----

/** Removes commas and spaces; accepts digits with an optional decimal part. */
fun readNumeric(raw: String?): Double {
    val cleaned = raw.orEmpty().replace(",", "").trim()
    return if (Regex("^\\d+(?:\\.\\d+)?$").matches(cleaned)) cleaned.toDouble() else Double.NaN
}

/** Removes commas, spaces and a trailing "원"; accepts whole numbers only. */
fun priceValue(raw: String?): Double {
    val text = raw.orEmpty().trim().replace(Regex("[,\\s]"), "").removeSuffix("원")
    return if (Regex("^\\d+$").matches(text) && text.length <= 15) text.toDouble() else Double.NaN
}

fun validPrice(n: Double): Boolean = !n.isNaN() && n == Math.floor(n) && n >= 1 && n <= 99_999_999

fun validVolume(n: Double): Boolean = !n.isNaN() && n == Math.floor(n) && n >= 1 && n <= 999

/** "15,000원", or "—" when there is no price. */
fun won(n: Double?): String =
    if (n != null && n > 0) NumberFormat.getNumberInstance(Locale.KOREA).format(n.toLong()) + "원" else "—"

/** Shows a number the way the prototype prints it in a field: 30, 22.5, or empty. */
fun numberText(n: Double): String = when {
    n.isNaN() -> ""
    n == Math.floor(n) -> n.toLong().toString()
    else -> n.toString()
}
