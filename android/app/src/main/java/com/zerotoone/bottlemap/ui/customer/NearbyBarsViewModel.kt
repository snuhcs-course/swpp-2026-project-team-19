// AI-assisted frontend state management (2026-10-18, I2-A7/A8).
package com.zerotoone.bottlemap.ui.customer

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zerotoone.bottlemap.data.NearbyBar
import com.zerotoone.bottlemap.data.NearbyBarsSource
import com.zerotoone.bottlemap.data.NearbyCoordinate
import com.zerotoone.bottlemap.data.NearbyLocationInaccurateException
import com.zerotoone.bottlemap.data.NearbyLocationServicesDisabledException
import com.zerotoone.bottlemap.data.NearbyLocationSource
import com.zerotoone.bottlemap.data.NearbyLocationUnavailableException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

enum class NearbyPermission {
    NONE, APPROXIMATE, PRECISE, PERMANENTLY_DENIED,
}

sealed interface NearbyUiState {
    data object Initial : NearbyUiState
    data object PermissionRequired : NearbyUiState
    data object PermissionPermanentlyDenied : NearbyUiState
    data object ApproximateOnly : NearbyUiState
    data object LoadingLocation : NearbyUiState
    data object LocationServicesDisabled : NearbyUiState
    data object LoadingBars : NearbyUiState
    data class Success(val origin: NearbyCoordinate, val bars: List<NearbyBar>) : NearbyUiState
    data object Empty : NearbyUiState
    data class Error(val message: String, val canRetry: Boolean = true) : NearbyUiState
}

/** Selected bar ID is the sole source of truth for carousel and Kakao labels. */
class NearbyBarsViewModel(
    private val locationSource: NearbyLocationSource,
    private val barsSource: NearbyBarsSource,
    private val savedStateHandle: SavedStateHandle = SavedStateHandle(),
) : ViewModel() {
    private val _state = MutableStateFlow<NearbyUiState>(NearbyUiState.Initial)
    val state: StateFlow<NearbyUiState> = _state.asStateFlow()

    val selectedBarId: StateFlow<String?> =
        savedStateHandle.getStateFlow<String?>("nearbySelectedBarId", null)

    private var currentPermission = NearbyPermission.NONE
    private var query: Job? = null
    private var requestVersion = 0L

    fun updatePermission(permission: NearbyPermission) {
        if (permission != NearbyPermission.PRECISE) {
            ++requestVersion
            query?.cancel()
            currentPermission = permission
            _state.value = when (permission) {
                NearbyPermission.NONE -> NearbyUiState.PermissionRequired
                NearbyPermission.APPROXIMATE -> NearbyUiState.ApproximateOnly
                NearbyPermission.PERMANENTLY_DENIED -> NearbyUiState.PermissionPermanentlyDenied
                NearbyPermission.PRECISE -> error("Unreachable")
            }
            return
        }
        val newlyGranted = currentPermission != NearbyPermission.PRECISE
        currentPermission = permission
        if (newlyGranted || _state.value is NearbyUiState.Initial ||
            _state.value is NearbyUiState.PermissionRequired ||
            _state.value is NearbyUiState.LocationServicesDisabled
        ) refresh()
    }

    fun refresh() {
        if (currentPermission != NearbyPermission.PRECISE) return
        val version = ++requestVersion
        query?.cancel()
        _state.value = NearbyUiState.LoadingLocation
        query = viewModelScope.launch {
            try {
                val origin = locationSource.currentLocation()
                if (version != requestVersion) return@launch
                _state.value = NearbyUiState.LoadingBars
                // Backend A9 already filters on the rounded integer distance,
                // returns ALL active bars, and sorts nearest first. Never re-filter.
                val nearby = barsSource.listNearbyBars(origin)
                if (version != requestVersion) return@launch
                if (nearby.isEmpty()) {
                    savedStateHandle["nearbySelectedBarId"] = null
                    _state.value = NearbyUiState.Empty
                } else {
                    val remembered = selectedBarId.value
                    savedStateHandle["nearbySelectedBarId"] =
                        remembered?.takeIf { id -> nearby.any { it.barId == id } }
                            ?: nearby.first().barId
                    _state.value = NearbyUiState.Success(origin, nearby)
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if (version != requestVersion) return@launch
                _state.value = when (error) {
                    is NearbyLocationServicesDisabledException ->
                        NearbyUiState.LocationServicesDisabled
                    is NearbyLocationInaccurateException ->
                        NearbyUiState.Error("정확한 위치를 확인하지 못했습니다. 실외에서 다시 시도해 주세요.")
                    is NearbyLocationUnavailableException ->
                        NearbyUiState.Error("현재 위치를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.")
                    is com.zerotoone.bottlemap.network.BottleMapApiException ->
                        when (error.code) {
                            "VALIDATION_FAILED" ->
                                NearbyUiState.Error("위치 요청에 문제가 있습니다. 앱을 다시 실행해 주세요.", canRetry = false)
                            "HTTP_404" ->
                                NearbyUiState.Error("서버에서 주변 바 기능을 아직 제공하지 않습니다. 배포 상태를 확인해 주세요.")
                            "NETWORK_ERROR" ->
                                NearbyUiState.Error("네트워크 연결을 확인하고 다시 시도해 주세요.")
                            else -> NearbyUiState.Error("주변 바 조회에 실패했습니다. 잠시 후 다시 시도해 주세요.")
                        }
                    is SecurityException -> NearbyUiState.PermissionRequired
                    else -> NearbyUiState.Error("주변 바를 불러오지 못했습니다. 연결을 확인해 주세요.")
                }
            }
        }
    }

    fun selectBar(barId: String): Boolean {
        val existing = _state.value as? NearbyUiState.Success ?: return false
        if (existing.bars.none { it.barId == barId }) return false
        savedStateHandle["nearbySelectedBarId"] = barId
        return true
    }

    override fun onCleared() {
        query?.cancel()
        super.onCleared()
    }
}
