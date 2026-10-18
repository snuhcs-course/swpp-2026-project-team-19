// AI-generated with ChatGPT (Hojin Nam, 2026-10-06, PR #15). Reviewed by Hojin Nam.
package com.zerotoone.bottlemap.ui.owner

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zerotoone.bottlemap.data.Repositories
import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.network.ChangeDecisionDto
import com.zerotoone.bottlemap.network.MenuImportStatusDto
import com.zerotoone.bottlemap.network.ReviewAndApplyRequestDto
import com.zerotoone.bottlemap.network.ReviewItemDto
import java.text.NumberFormat
import java.util.Locale
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class ExtractionReviewViewModel : ViewModel() {
    private val repository = Repositories.owner

    private val _state = MutableStateFlow<ExtractionReviewUiState>(ExtractionReviewUiState.Loading)
    val state: StateFlow<ExtractionReviewUiState> = _state.asStateFlow()

    private var currentImportId: String? = null
    private var currentReview: MenuImportStatusDto? = null

    fun load(menuImportId: String, force: Boolean = false) {
        if (!force && currentImportId == menuImportId && _state.value !is ExtractionReviewUiState.Error) {
            return
        }
        currentImportId = menuImportId
        _state.value = ExtractionReviewUiState.Loading
        viewModelScope.launch {
            fetchReview(menuImportId)
        }
    }

    fun applyDefaultReview() {
        val import = currentReview ?: return
        val ui = import.toReviewUiModelOrNull() ?: return
        val request = runCatching { import.buildDefaultReviewRequest() }
            .getOrElse { error ->
                _state.value = ExtractionReviewUiState.Ready(
                    review = ui,
                    message = error.message ?: "This review needs manual correction before publishing.",
                )
                return
            }

        _state.value = ExtractionReviewUiState.Applying(ui)
        viewModelScope.launch {
            try {
                val result = repository.reviewAndApply(import.menuImportId, request)
                _state.value = ExtractionReviewUiState.Applied(
                    AppliedUiModel(
                        menuImportId = result.menuImportId,
                        appliedAt = result.appliedAt,
                        added = result.result.added,
                        updated = result.result.updated,
                        removed = result.result.removed,
                        ignored = result.result.ignored,
                    )
                )
                currentReview = null
            } catch (error: BottleMapApiException) {
                when (error.code) {
                    "REVIEW_OUTDATED" -> {
                        fetchReview(
                            import.menuImportId,
                            messageAfterLoad = "The menu changed while you were reviewing it. Review the refreshed proposal before publishing.",
                        )
                    }

                    "TEMPORARY_WRITE_CONFLICT" -> {
                        _state.value = ExtractionReviewUiState.Ready(
                            review = ui,
                            message = "The server had a temporary write conflict. It is safe to submit this same review again.",
                        )
                    }

                    "DUPLICATE_BRAND_FOUND", "DUPLICATE_PRODUCT_FOUND" -> {
                        _state.value = ExtractionReviewUiState.Ready(
                            review = ui,
                            message = error.message + " This case needs product/brand selection before publish.",
                        )
                    }

                    else -> {
                        _state.value = ExtractionReviewUiState.Ready(
                            review = ui,
                            message = error.message,
                        )
                    }
                }
            } catch (error: Throwable) {
                _state.value = ExtractionReviewUiState.Ready(
                    review = ui,
                    message = error.message ?: "Publishing failed.",
                )
            }
        }
    }

    private suspend fun fetchReview(
        menuImportId: String,
        messageAfterLoad: String? = null,
    ) {
        try {
            val status = repository.getMenuImport(menuImportId)
            when (status.status) {
                "ready_for_review" -> {
                    currentReview = status
                    val ui = status.toReviewUiModelOrNull()
                        ?: throw IllegalStateException("Review response is missing reviewVersion.")
                    _state.value = ExtractionReviewUiState.Ready(
                        review = ui,
                        message = messageAfterLoad,
                    )
                }

                "applied" -> {
                    currentReview = null
                    _state.value = ExtractionReviewUiState.Applied(
                        AppliedUiModel(
                            menuImportId = status.menuImportId,
                            appliedAt = status.appliedAt ?: "Published",
                        )
                    )
                }

                "failed" -> {
                    currentReview = null
                    _state.value = ExtractionReviewUiState.Error(
                        status.failure?.message ?: "Menu extraction failed.",
                    )
                }

                else -> {
                    currentReview = null
                    _state.value = ExtractionReviewUiState.Error(
                        "This import is still " + status.status + ". Return to the upload screen and continue polling.",
                    )
                }
            }
        } catch (error: Throwable) {
            currentReview = null
            _state.value = ExtractionReviewUiState.Error(
                error.message ?: "Failed to load review data.",
            )
        }
    }
}

private fun MenuImportStatusDto.toReviewUiModelOrNull(): ReviewUiModel? {
    val version = reviewVersion ?: return null
    val formatter = NumberFormat.getIntegerInstance(Locale.KOREA)
    return ReviewUiModel(
        menuImportId = menuImportId,
        reviewVersion = version,
        items = images
            .sortedBy { it.imageOrder }
            .flatMap { image -> image.items.sortedBy { it.itemOrder } }
            .map { item ->
                val proposal = item.candidates
                    .firstOrNull { it.productId == item.proposedProductId }
                    ?.displayName
                val title = item.extractedProductName ?: item.rawText.take(80)
                val decision = when {
                    item.effectiveLineType != "product" -> "Confirm as " + item.effectiveLineType
                    item.proposedProductId != null -> "Use existing product: " + (proposal ?: item.proposedProductId)
                    else -> "Create new product: " + (item.newProductDraft?.displayName ?: title)
                }
                ReviewItemUiModel(
                    extractedItemId = item.extractedItemId,
                    title = title,
                    rawText = item.rawText,
                    lineType = item.effectiveLineType,
                    decisionText = decision,
                    options = item.options
                        .sortedBy { it.optionOrder }
                        .map { option ->
                            val detail = listOfNotNull(
                                option.extractedOptionLabel,
                                option.extractedPourMl?.let { it.toString() + " ml" },
                            ).joinToString(" · ")
                            val price = option.extractedPriceKrw
                                ?.let { "₩" + formatter.format(it) }
                                ?: "No price"
                            ReviewOptionUiModel(
                                label = if (detail.isBlank()) "Option" else detail,
                                priceText = price,
                            )
                        },
                    needsReview = item.initialResolutionStatus != "exact_match" &&
                        item.effectiveLineType == "product",
                )
            },
        proposedChanges = proposedChanges.map { it.summary },
    )
}

internal fun MenuImportStatusDto.buildDefaultReviewRequest(): ReviewAndApplyRequestDto {
    val version = reviewVersion ?: error("Review version is missing.")
    val itemDecisions = images
        .sortedBy { it.imageOrder }
        .flatMap { image -> image.items.sortedBy { it.itemOrder } }
        .map { it.defaultDecision() }

    return ReviewAndApplyRequestDto(
        reviewVersion = version,
        itemDecisions = itemDecisions,
        changeDecisions = proposedChanges.map {
            ChangeDecisionDto(
                changeId = it.changeId,
                decision = "apply",
            )
        },
    )
}

internal fun ReviewItemDto.defaultDecision(): Map<String, Any?> {
    val base = linkedMapOf<String, Any?>(
        "extractedItemId" to extractedItemId,
        "finalLineType" to effectiveLineType,
    )

    if (effectiveLineType != "product") {
        base["action"] = "confirm_non_product"
        return base
    }

    if (proposedProductId != null) {
        base["action"] = "select_existing_product"
        base["productId"] = proposedProductId
        return base
    }

    val draft = newProductDraft ?: error(
        "No product proposal exists for " + (extractedProductName ?: rawText) + ".",
    )
    val displayName = draft.displayName ?: extractedProductName
        ?: error("A new product needs a display name.")
    val brandName = draft.brandText ?: displayName

    base["action"] = "create_product"
    base["brand"] = mapOf(
        "type" to "new",
        "canonicalName" to brandName,
    )
    base["product"] = linkedMapOf<String, Any?>(
        "category" to draft.category,
        "displayName" to displayName,
        "ageYears" to draft.ageYears,
        "editionName" to draft.editionName,
        "abv" to draft.abv,
    )
    return base
}
