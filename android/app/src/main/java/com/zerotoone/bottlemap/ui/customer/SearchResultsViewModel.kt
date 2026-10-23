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
            // Invalid navigation/input must invalidate an in-flight request.
            // Otherwise a late old response could overwrite InvalidQuery.
            ++requestVersion
            requestJob?.cancel()
            currentQuery = ""
            _state.value = CustomerSearchUiState.InvalidQuery(
                if (trimmed.isEmpty()) "BLANK" else "STRING_TOO_LONG",
            )
            return
        }
        // A recomposed or recreated destination must not auto-retry an existing error.
        if (currentQuery == trimmed) return
        currentQuery = trimmed
        load()
    }

    fun retry() {
        if (currentQuery.isNotBlank() &&
            _state.value is CustomerSearchUiState.Error &&
            (_state.value as CustomerSearchUiState.Error).canRetry
        ) {
            load()
        }
    }

    /** Only BAR_NOT_FOUND from the detail screen requests this refresh.
     * Normal back navigation retains the existing result list unchanged.
     */
    fun refreshAfterMissingBar() {
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
                    _state.value = classifySearchError(error)
                }
            }
        }
    }
}

/**
 * The backend contract uses error.code rather than HTTP status for client behavior.
 * Only query validation errors are returned to the editable search field.
 */
internal fun classifySearchError(error: Exception): CustomerSearchUiState {
    if (error is BottleMapApiException && error.code == "VALIDATION_FAILED") {
        val queryFieldCode = error.fieldErrors.firstOrNull {
            it.path == "query" && it.code in setOf(
                "MISSING", "BLANK", "STRING_TOO_LONG", "NOT_SEARCHABLE",
            )
        }?.code
        return if (queryFieldCode != null) {
            CustomerSearchUiState.InvalidQuery(queryFieldCode)
        } else {
            // Validation failure on an unexpected field is still not retryable.
            CustomerSearchUiState.Error(
                message = "검색 요청의 입력값을 확인해 주세요.",
                canRetry = false,
            )
        }
    }
    return CustomerSearchUiState.Error(searchErrorMessage(error))
}

internal fun searchErrorMessage(error: Exception): String = when (error) {
    is BottleMapApiException -> when (error.code) {
        "NETWORK_ERROR" -> "네트워크 연결을 확인한 뒤 다시 시도해 주세요."
        "SERVICE_UNAVAILABLE" -> "검색 서버를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해 주세요."
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
