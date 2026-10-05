package com.zerotoone.bottlemap.ui.owner

/**
 * UI-only state for P19.
 *
 * These types are intentionally not backend/API DTOs. P18/P25 integration should
 * replace the mock wiring with the confirmed REST contract when it is available.
 */
enum class MenuUploadUiState {
    EMPTY,
    SELECTED,
    PROCESSING,
    ERROR,
}

data class MockExtractedMenuItem(
    val productName: String,
    val priceText: String,
    val pourSizeText: String,
    val needsReview: Boolean = false,
)

sealed interface ExtractionReviewUiState {
    data object Loading : ExtractionReviewUiState

    data class Success(
        val items: List<MockExtractedMenuItem>,
    ) : ExtractionReviewUiState

    data object Empty : ExtractionReviewUiState

    data class Error(
        val message: String,
    ) : ExtractionReviewUiState
}

internal val mockExtractedMenuItems = listOf(
    MockExtractedMenuItem(
        productName = "Deanston 12",
        priceText = "18,000",
        pourSizeText = "30 ml",
    ),
    MockExtractedMenuItem(
        productName = "Ardbeg 10",
        priceText = "20,000",
        pourSizeText = "30 ml",
    ),
    MockExtractedMenuItem(
        productName = "Talisker 10",
        priceText = "16,000",
        pourSizeText = "30 ml",
        needsReview = true,
    ),
)
