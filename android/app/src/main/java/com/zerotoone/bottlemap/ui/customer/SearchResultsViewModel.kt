// AI-assisted implementation draft (2026-10-13, I2-P13/P14). Human build/review pending.
package com.zerotoone.bottlemap.ui.customer

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zerotoone.bottlemap.data.CustomerSearchSource
import com.zerotoone.bottlemap.data.Repositories
import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.network.SearchBarsResponseDto
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class SearchResultsViewModel(
    private val repository: CustomerSearchSource = Repositories.customer,
) : ViewModel() {
    private val _state = MutableStateFlow<CustomerSearchUiState>(CustomerSearchUiState.Loading)
    val state: StateFlow<CustomerSearchUiState> = _state.asStateFlow()

    private var currentQuery: String = ""
    private var requestJob: Job? = null
    private var requestVersion: Long = 0

    fun search(query: String) {
        val trimmed = query.trim()
        if (trimmed.isEmpty() || trimmed.length > 100) {
            _state.value = CustomerSearchUiState.Error("검색어를 1~100자로 입력해 주세요.")
            return
        }
        // LaunchedEffect(query) can run again after recomposition/navigation.
        if (currentQuery == trimmed && _state.value !is CustomerSearchUiState.Error) return
        currentQuery = trimmed
        load()
    }

    fun retry() {
        if (currentQuery.isNotBlank() && _state.value !is CustomerSearchUiState.Loading) {
            load()
        }
    }

    private fun load() {
        val query = currentQuery
        val version = ++requestVersion
        requestJob?.cancel()
        _state.value = CustomerSearchUiState.Loading
        requestJob = viewModelScope.launch {
            try {
                val response = repository.searchBars(query)
                if (version == requestVersion) _state.value = response.toUiState()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if (version == requestVersion) {
                    _state.value = CustomerSearchUiState.Error(searchErrorMessage(error))
                }
            }
        }
    }
}

internal fun searchErrorMessage(error: Exception): String = when (error) {
    is BottleMapApiException -> when {
        error.code == "NETWORK_ERROR" -> "네트워크 연결을 확인한 뒤 다시 시도해 주세요."
        error.httpStatus == 401 || error.httpStatus == 403 ->
            "게스트 검색에 접근할 수 없습니다. 잠시 후 다시 시도해 주세요."
        error.httpStatus != null && error.httpStatus >= 500 ->
            "검색 서버에 문제가 발생했습니다. 잠시 후 다시 시도해 주세요."
        else -> "검색 결과를 불러오지 못했습니다. 다시 시도해 주세요."
    }
    else -> "검색 응답을 처리하지 못했습니다. 다시 시도해 주세요."
}

internal fun SearchBarsResponseDto.toUiState(): CustomerSearchUiState {
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
                address = item.address,
                productId = item.productId,
                productDisplayName = item.productDisplayName,
                menuDisplayName = item.menuDisplayName,
                options = item.options.sortedBy { it.sortOrder }.map { option ->
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

private val menuDateFormatter = DateTimeFormatter.ofPattern("yyyy.MM.dd")
    .withZone(ZoneId.systemDefault())

internal fun formatMenuTimestamp(value: String): String =
    runCatching {
        "갱신 " + menuDateFormatter.format(Instant.parse(value))
    }.getOrElse {
        // Invalid server date is not a fabricated update time.
        "갱신일 확인 불가"
    }
