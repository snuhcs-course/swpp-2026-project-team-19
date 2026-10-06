package com.zerotoone.bottlemap.ui.customer

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zerotoone.bottlemap.data.Repositories
import com.zerotoone.bottlemap.network.SearchBarsResponseDto
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class SearchResultsViewModel : ViewModel() {
    private val repository = Repositories.customer
    private val _state = MutableStateFlow<CustomerSearchUiState>(CustomerSearchUiState.Loading)
    val state: StateFlow<CustomerSearchUiState> = _state.asStateFlow()

    private var currentQuery: String = ""

    fun search(query: String) {
        val trimmed = query.trim()
        if (trimmed.isEmpty()) {
            _state.value = CustomerSearchUiState.Empty(EmptySearchReason.UNKNOWN_PRODUCT)
            return
        }
        if (currentQuery == trimmed && _state.value !is CustomerSearchUiState.Error) {
            return
        }
        currentQuery = trimmed
        load()
    }

    fun retry() {
        if (currentQuery.isNotEmpty()) {
            load()
        }
    }

    private fun load() {
        _state.value = CustomerSearchUiState.Loading
        viewModelScope.launch {
            _state.value = runCatching {
                repository.searchBars(currentQuery).toUiState()
            }.getOrElse { error ->
                CustomerSearchUiState.Error(
                    message = error.message ?: "We couldn't load search results.",
                )
            }
        }
    }
}

private fun SearchBarsResponseDto.toUiState(): CustomerSearchUiState {
    if (matchedProducts.isEmpty()) {
        return CustomerSearchUiState.Empty(EmptySearchReason.UNKNOWN_PRODUCT)
    }
    if (items.isEmpty()) {
        return CustomerSearchUiState.Empty(EmptySearchReason.NO_BARS)
    }
    return CustomerSearchUiState.Success(
        results = items.map { item ->
            SearchResultUiModel(
                barId = item.barId,
                barName = item.barName,
                productDisplayName = item.productDisplayName,
                menuDisplayName = item.menuDisplayName,
                options = item.options
                    .sortedBy { it.sortOrder }
                    .map { option ->
                        SearchOptionUiModel(
                            priceKrw = option.priceKrw,
                            optionLabel = option.optionLabel,
                            pourMl = option.pourMl,
                        )
                    },
                menuUpdatedText = formatMenuTimestamp(item.menuUpdatedAt),
            )
        },
        truncated = truncated,
    )
}

private val menuDateFormatter = DateTimeFormatter.ofPattern("MMM d, yyyy")
    .withZone(ZoneId.systemDefault())

private fun formatMenuTimestamp(value: String): String =
    runCatching {
        "Updated " + menuDateFormatter.format(Instant.parse(value))
    }.getOrElse {
        "Updated " + value
    }
