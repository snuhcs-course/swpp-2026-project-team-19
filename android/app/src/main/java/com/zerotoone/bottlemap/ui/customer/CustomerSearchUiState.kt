// AI-generated with ChatGPT (Hojin Nam, 2026-10-06, PR #7, #15). Reviewed by Hojin Nam.
package com.zerotoone.bottlemap.ui.customer

sealed interface CustomerSearchUiState {
    data object Loading : CustomerSearchUiState

    data class Success(
        val results: List<SearchResultUiModel>,
        val truncated: Boolean,
    ) : CustomerSearchUiState

    data class Empty(
        val reason: EmptySearchReason,
    ) : CustomerSearchUiState

    data class Error(
        val message: String,
    ) : CustomerSearchUiState
}

enum class EmptySearchReason {
    UNKNOWN_PRODUCT,
    NO_BARS,
}

data class SearchOptionUiModel(
    val priceKrw: Int,
    val optionLabel: String?,
    val pourMl: Int?,
)

data class SearchResultUiModel(
    val barId: String,
    val barName: String,
    val productDisplayName: String,
    val menuDisplayName: String,
    val options: List<SearchOptionUiModel>,
    val menuUpdatedText: String,
)
