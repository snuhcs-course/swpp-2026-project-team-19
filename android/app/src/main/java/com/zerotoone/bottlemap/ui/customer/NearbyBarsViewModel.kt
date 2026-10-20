// Map-first customer discovery; carousel remains anchored to the user's location.
package com.zerotoone.bottlemap.ui.customer

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.zerotoone.bottlemap.data.BackendMapBarsRepository
import com.zerotoone.bottlemap.data.MapBar
import com.zerotoone.bottlemap.data.MapBarsSource
import com.zerotoone.bottlemap.data.MapBounds
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
    data class Ready(val bars: List<MapBar>, val bounds: MapBounds) : MapDiscoveryState
    data object TooWide : MapDiscoveryState
    data class Error(val message: String) : MapDiscoveryState
}

/** Route-scoped center/zoom survives Bar Detail navigation. */
data class DiscoveryCamera(val center: NearbyCoordinate, val zoomLevel: Int)

/** Camera viewport is a WGS84 box, not a center/radius approximation. */
data class MapViewport(val bounds: MapBounds)

/** Selected bar is a single shared ID across map markers and the 1km carousel. */
class NearbyBarsViewModel(
    private val locationSource: NearbyLocationSource,
    private val barsSource: NearbyBarsSource,
    private val savedStateHandle: SavedStateHandle = SavedStateHandle(),
    private val mapBarsSource: MapBarsSource = BackendMapBarsRepository(),
) : ViewModel() {
    private val _state = MutableStateFlow<NearbyUiState>(NearbyUiState.Initial)
    val state: StateFlow<NearbyUiState> = _state.asStateFlow()
    private val _origin = MutableStateFlow<NearbyCoordinate?>(null)
    val origin: StateFlow<NearbyCoordinate?> = _origin.asStateFlow()
    private val _map = MutableStateFlow<MapDiscoveryState>(MapDiscoveryState.Initial)
    val map: StateFlow<MapDiscoveryState> = _map.asStateFlow()
    // Keep the previous visible markers while a new viewport request is in flight.
    private val _markers = MutableStateFlow<List<MapBar>>(emptyList())
    val markers: StateFlow<List<MapBar>> = _markers.asStateFlow()

    val selectedBarId: StateFlow<String?> =
        savedStateHandle.getStateFlow<String?>("nearbySelectedBarId", null)
    val focusBarId: StateFlow<String?> =
        savedStateHandle.getStateFlow<String?>("nearbyFocusBarId", null)

    fun savedCamera(): DiscoveryCamera? {
        val latitude = savedStateHandle.get<Double>("mapCenterLatitude") ?: return null
        val longitude = savedStateHandle.get<Double>("mapCenterLongitude") ?: return null
        val zoom = savedStateHandle.get<Int>("mapZoomLevel") ?: return null
        val point = NearbyCoordinate(latitude, longitude)
        return point.takeIf { it.isValid() && zoom in 1..21 }
            ?.let { DiscoveryCamera(it, zoom) }
    }

    fun rememberCamera(center: NearbyCoordinate, zoomLevel: Int) {
        if (!acceptingCameraChanges || !center.isValid() ||
            zoomLevel !in 1..21 || _origin.value == null
        ) return
        savedStateHandle["mapCenterLatitude"] = center.latitude
        savedStateHandle["mapCenterLongitude"] = center.longitude
        savedStateHandle["mapZoomLevel"] = zoomLevel
    }

    fun consumeFocusRequest() {
        savedStateHandle["nearbyFocusBarId"] = null
    }

    private fun clearCamera() {
        savedStateHandle.remove<Double>("mapCenterLatitude")
        savedStateHandle.remove<Double>("mapCenterLongitude")
        savedStateHandle.remove<Int>("mapZoomLevel")
    }

    private var currentPermission = NearbyPermission.NONE
    private var query: Job? = null
    private var mapQuery: Job? = null
    private var requestVersion = 0L
    private var mapVersion = 0L
    private var lastViewport: MapViewport? = null
    // A late MapView.onDispose after popping Nearby must not persist the exited camera.
    private var acceptingCameraChanges = true

    fun beginDiscovery() {
        acceptingCameraChanges = true
    }

    fun updatePermission(permission: NearbyPermission) {
        if (permission == NearbyPermission.NONE || permission == NearbyPermission.PERMANENTLY_DENIED) {
            requestVersion++
            mapVersion++
            query?.cancel()
            mapQuery?.cancel()
            currentPermission = permission
            _origin.value = null
            _map.value = MapDiscoveryState.Initial
            _markers.value = emptyList()
            lastViewport = null
            savedStateHandle["nearbySelectedBarId"] = null
            savedStateHandle["nearbyFocusBarId"] = null
            clearCamera()
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
        ) refreshInternal(clearSavedCamera = previouslyGranted)
    }

    fun refresh() = refreshInternal(clearSavedCamera = true)

    private fun refreshInternal(clearSavedCamera: Boolean) {
        if (currentPermission != NearbyPermission.PRECISE &&
            currentPermission != NearbyPermission.APPROXIMATE) return
        val version = ++requestVersion
        query?.cancel()
        mapVersion++
        mapQuery?.cancel()
        lastViewport = null
        // A recreated Activity still has a SavedStateHandle camera snapshot.
        // Only an explicit user refresh or permission accuracy change resets it.
        if (clearSavedCamera) clearCamera()
        _map.value = MapDiscoveryState.Initial
        _markers.value = emptyList()
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

    /** Load the exact visible bounds after the camera gesture. No 3km circle. */
    fun onViewportChanged(viewport: MapViewport, force: Boolean = false) {
        if (_origin.value == null) return
        val previous = lastViewport
        if (!force && previous != null &&
            previous.bounds.isNearlySameAs(viewport.bounds) &&
            _map.value !is MapDiscoveryState.Error
        ) return
        lastViewport = viewport
        val version = ++mapVersion
        mapQuery?.cancel()
        if (!viewport.bounds.isSupportedByBackend()) {
            // Contract max span 0.2 degrees on each axis. Never send 422 knowingly.
            _map.value = MapDiscoveryState.TooWide
            return
        }
        _map.value = MapDiscoveryState.Loading
        mapQuery = viewModelScope.launch {
            delay(350)
            try {
                val bars = mapBarsSource.listMapBars(viewport.bounds).distinctBy { it.barId }
                if (version != mapVersion || _origin.value == null) return@launch
                _markers.value = bars
                _map.value = MapDiscoveryState.Ready(bars, viewport.bounds)
                val id = selectedBarId.value
                val carousel = (_state.value as? NearbyUiState.Success)?.bars.orEmpty()
                if (id != null && bars.none { it.barId == id } &&
                    carousel.none { it.barId == id }
                ) savedStateHandle["nearbySelectedBarId"] = null
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if (version != mapVersion) return@launch
                _map.value = if (error is com.zerotoone.bottlemap.network.BottleMapApiException &&
                    error.fieldErrors.any { it.code == "BOUNDS_TOO_LARGE" }
                ) MapDiscoveryState.TooWide else MapDiscoveryState.Error(
                    "이 지도 영역의 매장을 불러오지 못했습니다.")
            }
        }
    }

    fun retryMap() {
        lastViewport?.let { onViewportChanged(it, force = true) }
    }

    /** Dismiss a previous selection only when exiting discovery back to Search.
     *  Returning from Bar Detail to the same map retains the chosen bar.
     */
    fun leaveDiscovery() {
        acceptingCameraChanges = false
        mapVersion++
        mapQuery?.cancel()
        lastViewport = null
        _map.value = MapDiscoveryState.Initial
        _markers.value = emptyList()
        savedStateHandle["nearbySelectedBarId"] = null
        savedStateHandle["nearbyFocusBarId"] = null
        clearCamera()
    }

    fun clearSelection() {
        savedStateHandle["nearbySelectedBarId"] = null
        savedStateHandle["nearbyFocusBarId"] = null
    }

    fun selectBar(barId: String): Boolean {
        val carousel = (_state.value as? NearbyUiState.Success)?.bars.orEmpty()
        val markers = _markers.value
        if ((carousel + markers).none { it.barId == barId }) return false
        savedStateHandle["nearbySelectedBarId"] = barId
        savedStateHandle["nearbyFocusBarId"] = barId
        return true
    }

    override fun onCleared() {
        query?.cancel()
        mapQuery?.cancel()
        super.onCleared()
    }
}
