// Map-first customer discovery; carousel remains anchored to the user's location.
package com.zerotoone.bottlemap.ui.customer

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zerotoone.bottlemap.data.MAX_NEARBY_API_RADIUS_METERS
import com.zerotoone.bottlemap.data.NEARBY_CAROUSEL_RADIUS_METERS
import com.zerotoone.bottlemap.data.NearbyBar
import com.zerotoone.bottlemap.data.NearbyBarsSource
import com.zerotoone.bottlemap.data.NearbyCoordinate
import com.zerotoone.bottlemap.data.NearbyLocationInaccurateException
import com.zerotoone.bottlemap.data.NearbyLocationServicesDisabledException
import com.zerotoone.bottlemap.data.NearbyLocationSource
import com.zerotoone.bottlemap.data.NearbyLocationUnavailableException
import com.zerotoone.bottlemap.data.distanceMeters
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
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
    data object ApproximateOnly : NearbyUiState // Legacy state, never blocks coarse discovery.
    data object LoadingLocation : NearbyUiState
    data object LocationServicesDisabled : NearbyUiState
    data object LoadingBars : NearbyUiState
    data class Success(val origin: NearbyCoordinate, val bars: List<NearbyBar>) : NearbyUiState
    data object Empty : NearbyUiState
    data class Error(val message: String, val canRetry: Boolean = true) : NearbyUiState
}

/** This result is independent of the 1km carousel. Every marker comes from the backend. */
sealed interface MapDiscoveryState {
    data object Initial : MapDiscoveryState
    data object Loading : MapDiscoveryState
    data class Ready(val bars: List<NearbyBar>, val radiusMeters: Int, val partiallyCovered: Boolean) : MapDiscoveryState
    data class Error(val message: String) : MapDiscoveryState
}

/** The SDK computes the radius from visible screen corners, never to filter bars locally. */
data class NearbyViewport(
    val center: NearbyCoordinate,
    val radiusMeters: Int,
    val partiallyCovered: Boolean = false,
) {
    init {
        require(center.isValid())
        require(radiusMeters in 1..MAX_NEARBY_API_RADIUS_METERS)
    }
}

/** Selected bar is a single shared ID across map markers and the 1km carousel. */
class NearbyBarsViewModel(
    private val locationSource: NearbyLocationSource,
    private val barsSource: NearbyBarsSource,
    private val savedStateHandle: SavedStateHandle = SavedStateHandle(),
) : ViewModel() {
    private val _state = MutableStateFlow<NearbyUiState>(NearbyUiState.Initial)
    val state: StateFlow<NearbyUiState> = _state.asStateFlow()
    private val _origin = MutableStateFlow<NearbyCoordinate?>(null)
    val origin: StateFlow<NearbyCoordinate?> = _origin.asStateFlow()
    private val _map = MutableStateFlow<MapDiscoveryState>(MapDiscoveryState.Initial)
    val map: StateFlow<MapDiscoveryState> = _map.asStateFlow()

    val selectedBarId: StateFlow<String?> =
        savedStateHandle.getStateFlow<String?>("nearbySelectedBarId", null)

    private var currentPermission = NearbyPermission.NONE
    private var query: Job? = null
    private var mapQuery: Job? = null
    private var requestVersion = 0L
    private var mapVersion = 0L
    private var lastViewport: NearbyViewport? = null

    fun updatePermission(permission: NearbyPermission) {
        if (permission == NearbyPermission.NONE || permission == NearbyPermission.PERMANENTLY_DENIED) {
            requestVersion++
            mapVersion++
            query?.cancel()
            mapQuery?.cancel()
            currentPermission = permission
            _origin.value = null
            _map.value = MapDiscoveryState.Initial
            lastViewport = null
            savedStateHandle["nearbySelectedBarId"] = null
            _state.value = when (permission) {
                NearbyPermission.NONE -> NearbyUiState.PermissionRequired
                NearbyPermission.PERMANENTLY_DENIED -> NearbyUiState.PermissionPermanentlyDenied
                else -> error("unreachable")
            }
            return
        }
        val previouslyGranted = currentPermission == NearbyPermission.PRECISE ||
            currentPermission == NearbyPermission.APPROXIMATE
        val changedAccuracy = currentPermission != permission
        currentPermission = permission
        if (!previouslyGranted || changedAccuracy || _state.value is NearbyUiState.Initial ||
            _state.value is NearbyUiState.PermissionRequired ||
            _state.value is NearbyUiState.LocationServicesDisabled
        ) refresh()
    }

    fun refresh() {
        if (currentPermission != NearbyPermission.PRECISE &&
            currentPermission != NearbyPermission.APPROXIMATE) return
        val version = ++requestVersion
        query?.cancel()
        mapVersion++
        mapQuery?.cancel()
        lastViewport = null
        _map.value = MapDiscoveryState.Initial
        _origin.value = null
        _state.value = NearbyUiState.LoadingLocation
        query = viewModelScope.launch {
            try {
                val point = locationSource.currentLocation()
                if (version != requestVersion) return@launch
                _origin.value = point // MapView appears immediately, before carousel API finishes.
                _state.value = NearbyUiState.LoadingBars
                val nearby = barsSource.listNearbyBars(point, NEARBY_CAROUSEL_RADIUS_METERS)
                if (version != requestVersion) return@launch
                val id = selectedBarId.value
                if (id != null && nearby.none { it.barId == id } &&
                    (_map.value as? MapDiscoveryState.Ready)?.bars?.none { it.barId == id } != false
                ) savedStateHandle["nearbySelectedBarId"] = null
                _state.value = if (nearby.isEmpty()) NearbyUiState.Empty
                    else NearbyUiState.Success(point, nearby)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if (version != requestVersion) return@launch
                _state.value = when (error) {
                    is NearbyLocationServicesDisabledException -> NearbyUiState.LocationServicesDisabled
                    is NearbyLocationInaccurateException ->
                        NearbyUiState.Error("정확한 위치를 확인하지 못했습니다. 실외에서 다시 시도해 주세요.")
                    is NearbyLocationUnavailableException ->
                        NearbyUiState.Error("현재 위치를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.")
                    is com.zerotoone.bottlemap.network.BottleMapApiException ->
                        when (error.code) {
                            "VALIDATION_FAILED" -> NearbyUiState.Error(
                                "위치 요청에 문제가 있습니다. 앱을 다시 실행해 주세요.", canRetry = false)
                            "HTTP_404" -> NearbyUiState.Error(
                                "서버에서 주변 바 기능을 아직 제공하지 않습니다. 배포 상태를 확인해 주세요.")
                            "NETWORK_ERROR" -> NearbyUiState.Error(
                                "네트워크 연결을 확인하고 다시 시도해 주세요.")
                            else -> NearbyUiState.Error("1km 주변 바를 불러오지 못했습니다. 다시 시도해 주세요.")
                        }
                    is SecurityException -> NearbyUiState.PermissionRequired
                    else -> NearbyUiState.Error("주변 바를 불러오지 못했습니다. 연결을 확인해 주세요.")
                }
            }
        }
    }

    /** Called only after native camera movement ends. Coalesce fast gestures and ignore stale replies. */
    fun onViewportChanged(viewport: NearbyViewport, force: Boolean = false) {
        if (_origin.value == null) return
        val previous = lastViewport
        if (!force && previous != null &&
            distanceMeters(previous.center, viewport.center) < 80.0 &&
            kotlin.math.abs(previous.radiusMeters - viewport.radiusMeters) <
                kotlin.math.max(50, previous.radiusMeters / 10) &&
            previous.partiallyCovered == viewport.partiallyCovered &&
            _map.value !is MapDiscoveryState.Error
        ) return
        lastViewport = viewport
        val version = ++mapVersion
        mapQuery?.cancel()
        _map.value = MapDiscoveryState.Loading
        mapQuery = viewModelScope.launch {
            delay(350) // one request at the end of a gesture, not on every camera frame
            try {
                val bars = barsSource.listNearbyBars(viewport.center, viewport.radiusMeters)
                    .distinctBy { it.barId }
                if (version != mapVersion || _origin.value == null) return@launch
                _map.value = MapDiscoveryState.Ready(
                    bars, viewport.radiusMeters, viewport.partiallyCovered)
                val id = selectedBarId.value
                val carousel = (_state.value as? NearbyUiState.Success)?.bars.orEmpty()
                if (id != null && bars.none { it.barId == id } &&
                    carousel.none { it.barId == id }
                ) savedStateHandle["nearbySelectedBarId"] = null
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                if (version == mapVersion) _map.value =
                    MapDiscoveryState.Error("이 지도 영역의 바를 불러오지 못했습니다.")
            }
        }
    }

    fun retryMap() {
        lastViewport?.let { onViewportChanged(it, force = true) }
    }

    fun selectBar(barId: String): Boolean {
        val carousel = (_state.value as? NearbyUiState.Success)?.bars.orEmpty()
        val markers = (_map.value as? MapDiscoveryState.Ready)?.bars.orEmpty()
        if ((carousel + markers).none { it.barId == barId }) return false
        savedStateHandle["nearbySelectedBarId"] = barId
        return true
    }

    override fun onCleared() {
        query?.cancel()
        mapQuery?.cancel()
        super.onCleared()
    }
}
