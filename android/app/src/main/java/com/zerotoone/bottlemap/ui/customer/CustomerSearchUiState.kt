package com.zerotoone.bottlemap.ui.customer

/**
 * UI-only state for P22.
 *
 * This file intentionally does not define backend/API DTOs. P25 should replace
 * the mock source with the confirmed REST contract and map that response into UI state.
 */
sealed interface CustomerSearchUiState {
    data object Idle : CustomerSearchUiState

    data object Loading : CustomerSearchUiState

    data class Success(
        val results: List<MockSearchResult>,
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

data class MockSearchOption(
    val priceKrw: Int,
    val pourMl: Int,
)

data class MockSearchResult(
    val barName: String,
    val productDisplayName: String,
    val options: List<MockSearchOption>,
    val menuUpdatedText: String,
)

/**
 * P22-only fake results. These are display data, not backend fixtures or API examples.
 */
internal val mockSearchResults = listOf(
    MockSearchResult(
        barName = "The Malt House",
        productDisplayName = "Deanston 12",
        options = listOf(
            MockSearchOption(priceKrw = 18_000, pourMl = 30),
        ),
        menuUpdatedText = "Updated Oct 4, 2026",
    ),
    MockSearchResult(
        barName = "Bar Grain",
        productDisplayName = "Deanston 12",
        options = listOf(
            MockSearchOption(priceKrw = 10_000, pourMl = 15),
            MockSearchOption(priceKrw = 20_000, pourMl = 30),
        ),
        menuUpdatedText = "Updated Oct 2, 2026",
    ),
    MockSearchResult(
        barName = "Whisky Room",
        productDisplayName = "Deanston 12",
        options = listOf(
            MockSearchOption(priceKrw = 17_000, pourMl = 20),
        ),
        menuUpdatedText = "Updated Sep 28, 2026",
    ),
    MockSearchResult(
        barName = "A Very Long Gwanak Whisky Bar Name for Layout Testing",
        productDisplayName = "Deanston 12",
        options = listOf(
            MockSearchOption(priceKrw = 16_000, pourMl = 30),
        ),
        menuUpdatedText = "Updated Sep 25, 2026",
    ),
    MockSearchResult(
        barName = "Oak & Glass",
        productDisplayName = "Deanston 12",
        options = listOf(
            MockSearchOption(priceKrw = 19_000, pourMl = 30),
        ),
        menuUpdatedText = "Updated Sep 21, 2026",
    ),
)

/**
 * Hidden P22 smoke-test triggers until P25 replaces this fake source:
 * - "unknown" -> product not recognized
 * - "no bars" -> product recognized but no current bar listing
 * - "error" -> recoverable error state
 */
internal fun mockSearchStateForQuery(query: String): CustomerSearchUiState =
    when (query.trim().lowercase()) {
        "unknown" -> CustomerSearchUiState.Empty(EmptySearchReason.UNKNOWN_PRODUCT)
        "no bars" -> CustomerSearchUiState.Empty(EmptySearchReason.NO_BARS)
        "error" -> CustomerSearchUiState.Error(
            message = "We couldn't load search results. Please try again.",
        )
        else -> CustomerSearchUiState.Success(mockSearchResults)
    }
