// AI-assisted implementation draft (2026-10-17, I2-P24). Human verification pending.
package com.zerotoone.bottlemap.ui.customer

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zerotoone.bottlemap.data.CustomerBarDetailSource
import com.zerotoone.bottlemap.data.Repositories
import com.zerotoone.bottlemap.network.BarMenuResponseDto
import com.zerotoone.bottlemap.network.BottleMapApiException
import java.text.NumberFormat
import java.util.Locale
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface BarDetailUiState {
    data object Loading : BarDetailUiState

    data class Success(val bar: BarDetailUiModel) : BarDetailUiState

    data class Empty(
        val bar: BarDetailUiModel,
        val reason: EmptyMenuReason,
    ) : BarDetailUiState

    data class Error(
        val message: String,
        val canRetry: Boolean = true,
    ) : BarDetailUiState
}

enum class EmptyMenuReason {
    NO_PUBLISHED_MENU,
    NO_CURRENT_ITEMS,
}

data class BarDetailUiModel(
    val barId: String,
    val name: String,
    val address: String,
    val phone: String?,
    val latitude: Double,
    val longitude: Double,
    val publishedAtText: String?,
    val items: List<BarMenuItemUiModel>,
)

data class BarMenuItemUiModel(
    val menuBoardEntryId: String,
    val productId: String,
    // This is the published menu label, NOT the canonical catalog product name.
    val menuDisplayName: String,
    val options: List<BarMenuOptionUiModel>,
)

data class BarMenuOptionUiModel(
    val text: String,
)

class BarDetailViewModel(
    private val source: CustomerBarDetailSource = Repositories.customer,
) : ViewModel() {
    private val _state = MutableStateFlow<BarDetailUiState>(BarDetailUiState.Loading)
    val state: StateFlow<BarDetailUiState> = _state.asStateFlow()

    private var currentBarId: String? = null
    private var requestJob: Job? = null
    private var requestVersion = 0L

    fun load(barId: String) {
        // Recomposition, rotation, and returning from the back stack must not refetch.
        if (currentBarId == barId) return
        currentBarId = barId
        if (barId.isBlank()) {
            _state.value = BarDetailUiState.Error("업장을 찾을 수 없습니다.", canRetry = false)
            return
        }
        request()
    }

    fun retry() {
        val id = currentBarId
        if (!id.isNullOrBlank() &&
            (_state.value as? BarDetailUiState.Error)?.canRetry == true
        ) {
            request()
        }
    }

    private fun request() {
        val barId = currentBarId ?: return
        val version = ++requestVersion
        requestJob?.cancel()
        _state.value = BarDetailUiState.Loading
        requestJob = viewModelScope.launch {
            try {
                val response = source.getPublishedBarMenu(barId)
                if (version == requestVersion) _state.value = response.toBarDetailUiState()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if (version == requestVersion) {
                    _state.value = classifyBarDetailError(error)
                }
            }
        }
    }
}

internal fun classifyBarDetailError(error: Exception): BarDetailUiState.Error =
    when (error) {
        is BottleMapApiException -> when (error.code) {
            "BAR_NOT_FOUND" -> BarDetailUiState.Error(
                message = "업장을 찾을 수 없습니다. 검색 결과로 돌아가 주세요.",
                canRetry = false,
            )
            "NETWORK_ERROR" -> BarDetailUiState.Error(
                "네트워크 연결을 확인한 뒤 다시 시도해 주세요.",
            )
            "SERVICE_UNAVAILABLE" -> BarDetailUiState.Error(
                "서비스를 일시적으로 이용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
            )
            "UNAUTHENTICATED" -> BarDetailUiState.Error(
                "인증 상태를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.",
            )
            else -> BarDetailUiState.Error("업장 메뉴를 불러오지 못했습니다. 다시 시도해 주세요.")
        }
        else -> BarDetailUiState.Error("메뉴 응답을 처리하지 못했습니다. 다시 시도해 주세요.")
    }

/**
 * 3.9 contract: options and menu entries arrive in sortOrder. Keep that order.
 * The endpoint does NOT provide canonical product names for every menu entry.
 */
internal fun BarMenuResponseDto.toBarDetailUiState(): BarDetailUiState {
    val bar = BarDetailUiModel(
        barId = barId,
        name = name,
        address = address,
        phone = phone,
        latitude = latitude,
        longitude = longitude,
        publishedAtText = publishedAt?.let(::formatMenuTimestamp),
        items = items.map { item ->
            BarMenuItemUiModel(
                menuBoardEntryId = item.menuBoardEntryId,
                productId = item.productId,
                menuDisplayName = item.displayName,
                options = item.options.map { option ->
                    BarMenuOptionUiModel(
                        text = formatBarMenuOption(
                            option.optionLabel,
                            option.pourMl,
                            option.priceKrw,
                        ),
                    )
                },
            )
        },
    )
    if (items.isNotEmpty()) return BarDetailUiState.Success(bar)
    return BarDetailUiState.Empty(
        bar = bar,
        reason = if (menuBoardId == null) {
            EmptyMenuReason.NO_PUBLISHED_MENU
        } else {
            EmptyMenuReason.NO_CURRENT_ITEMS
        },
    )
}

internal fun formatBarMenuOption(label: String?, pourMl: Int?, priceKrw: Int): String {
    val description = listOfNotNull(
        label?.takeIf { it.isNotBlank() },
        pourMl?.let { "$it ml" },
    ).joinToString(" · ")
    val price = "₩" + NumberFormat.getIntegerInstance(Locale.KOREA).format(priceKrw)
    return if (description.isEmpty()) price else "$description  $price"
}
