package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.SelectedMenuImage

enum class ImportModeUi(
    val apiValue: String,
    val label: String,
    val description: String,
) {
    PARTIAL_UPDATE(
        apiValue = "partial_update",
        label = "Partial update",
        description = "Keeps existing menu entries unless this upload updates them.",
    ),
    FULL_REPLACE(
        apiValue = "full_replace",
        label = "Full replace",
        description = "Entries not present in the uploaded menu can be proposed for removal.",
    ),
}

data class OwnerBarUiModel(
    val barId: String,
    val name: String,
    val address: String,
    val activeImportId: String? = null,
    val activeImportStatus: String? = null,
)

data class MenuUploadUiState(
    val loadingBars: Boolean = true,
    val bars: List<OwnerBarUiModel> = emptyList(),
    val selectedBarId: String? = null,
    val selectedImage: SelectedMenuImage? = null,
    val mode: ImportModeUi = ImportModeUi.PARTIAL_UPDATE,
    val working: Boolean = false,
    val statusMessage: String? = null,
    val errorMessage: String? = null,
    val openReviewImportId: String? = null,
)

data class ReviewOptionUiModel(
    val label: String,
    val priceText: String,
)

data class ReviewItemUiModel(
    val extractedItemId: String,
    val title: String,
    val rawText: String,
    val lineType: String,
    val decisionText: String,
    val options: List<ReviewOptionUiModel>,
    val needsReview: Boolean,
)

data class ReviewUiModel(
    val menuImportId: String,
    val reviewVersion: Int,
    val items: List<ReviewItemUiModel>,
    val proposedChanges: List<String>,
)

data class AppliedUiModel(
    val menuImportId: String,
    val appliedAt: String,
    val added: Int? = null,
    val updated: Int? = null,
    val removed: Int? = null,
    val ignored: Int? = null,
)

sealed interface ExtractionReviewUiState {
    data object Loading : ExtractionReviewUiState

    data class Ready(
        val review: ReviewUiModel,
        val message: String? = null,
    ) : ExtractionReviewUiState

    data class Applying(
        val review: ReviewUiModel,
    ) : ExtractionReviewUiState

    data class Applied(
        val result: AppliedUiModel,
    ) : ExtractionReviewUiState

    data class Error(
        val message: String,
    ) : ExtractionReviewUiState
}
