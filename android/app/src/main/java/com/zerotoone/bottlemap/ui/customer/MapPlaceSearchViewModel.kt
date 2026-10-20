package com.zerotoone.bottlemap.ui.customer

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import com.zerotoone.bottlemap.data.AndroidMapPlaceSearchSource
import com.zerotoone.bottlemap.data.BackendBarNameSearchSource
import com.zerotoone.bottlemap.data.CombinedMapPlaceSearchSource
import com.zerotoone.bottlemap.data.MapPlace
import com.zerotoone.bottlemap.data.MapPlaceSearchSource
import com.zerotoone.bottlemap.data.sanitizePlaces
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface MapPlaceSearchState {
    data object Idle : MapPlaceSearchState
    data object Loading : MapPlaceSearchState
    data class Results(val places: List<MapPlace>) : MapPlaceSearchState
    data class Error(val message: String) : MapPlaceSearchState
}

class MapPlaceSearchViewModel(private val source: MapPlaceSearchSource) : ViewModel() {
    private val _state = MutableStateFlow<MapPlaceSearchState>(MapPlaceSearchState.Idle)
    val state: StateFlow<MapPlaceSearchState> = _state.asStateFlow()

    private val _selected = MutableStateFlow<MapPlace?>(null)
    val selected: StateFlow<MapPlace?> = _selected.asStateFlow()

    private val _focus = MutableStateFlow<MapPlace?>(null)
    val focus: StateFlow<MapPlace?> = _focus.asStateFlow()

    private var job: Job? = null
    private var generation = 0L

    fun search(rawQuery: String) {
        val query = rawQuery.trim()
        ++generation
        job?.cancel()
        when {
            query.isEmpty() -> {
                _state.value = MapPlaceSearchState.Error("검색할 장소를 입력해 주세요.")
                return
            }
            query.length > 100 -> {
                _state.value = MapPlaceSearchState.Error("검색어는 100자 이하로 입력해 주세요.")
                return
            }
        }
        val version = generation
        _state.value = MapPlaceSearchState.Loading
        job = viewModelScope.launch {
            try {
                val places = sanitizePlaces(source.search(query))
                if (version == generation) {
                    _state.value = MapPlaceSearchState.Results(places)
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                if (version == generation) {
                    _state.value = MapPlaceSearchState.Error(
                        "장소를 검색하지 못했습니다. 네트워크 또는 기기 지도 서비스를 확인해 주세요.")
                }
            }
        }
    }

    fun select(place: MapPlace): Boolean {
        val candidates = (_state.value as? MapPlaceSearchState.Results)?.places.orEmpty()
        if (place !in candidates) return false
        _selected.value = place
        _focus.value = place
        return true
    }

    fun consumeFocus() {
        _focus.value = null
    }

    fun dismissResults() {
        ++generation
        job?.cancel()
        _state.value = MapPlaceSearchState.Idle
    }

    fun clear() {
        dismissResults()
        _selected.value = null
        _focus.value = null
    }

    override fun onCleared() {
        job?.cancel()
        super.onCleared()
    }
}

@Composable
internal fun mapPlaceSearchViewModel(): MapPlaceSearchViewModel {
    val context = LocalContext.current.applicationContext
    val factory = remember(context) {
        object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T =
                MapPlaceSearchViewModel(
                    CombinedMapPlaceSearchSource(
                        BackendBarNameSearchSource(),
                        AndroidMapPlaceSearchSource(context),
                    )
                ) as T
        }
    }
    return viewModel(factory = factory)
}
