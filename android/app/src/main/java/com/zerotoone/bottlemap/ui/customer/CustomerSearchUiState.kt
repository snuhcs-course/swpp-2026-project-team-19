package com.zerotoone.bottlemap.ui.customer

/** Search request state is owned by SearchResultsViewModel. */
sealed interface CustomerSearchUiState {
    data object Loading : CustomerSearchUiState

    data class Success(
        val results: List<SearchResultUiModel>,
        val truncated: Boolean,
    ) : CustomerSearchUiState

    data class Empty(
        val reason: EmptySearchReason,
    ) : CustomerSearchUiState

    /** Input validation must be fixed by editing the query, not by retrying. */
    data class InvalidQuery(
        val fieldErrorCode: String,
    ) : CustomerSearchUiState

    data class Error(
        val message: String,
        val canRetry: Boolean = true,
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
    val address: String,
    val productId: String,
    val productDisplayName: String,
    val menuDisplayName: String,
    val options: List<SearchOptionUiModel>,
    val menuUpdatedText: String,
)
