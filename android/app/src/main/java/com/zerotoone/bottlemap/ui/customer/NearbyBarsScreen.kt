package com.zerotoone.bottlemap.ui.customer

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import android.view.View
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.material3.Surface
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.CreationExtras
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.createSavedStateHandle
import com.kakao.vectormap.MapView
import com.zerotoone.bottlemap.data.AndroidNearbyLocationSource
import com.zerotoone.bottlemap.data.BackendNearbyBarsRepository
import com.zerotoone.bottlemap.data.BarPin
import com.zerotoone.bottlemap.data.MapBar
import com.zerotoone.bottlemap.data.MapPlace
import com.zerotoone.bottlemap.data.NearbyBar

@Composable
fun NearbyBarsScreen(
    onBack: () -> Unit,
    onOpenBarDetail: (String) -> Unit,
    viewModel: NearbyBarsViewModel = nearbyBarsViewModel(),
    placeSearchViewModel: MapPlaceSearchViewModel = mapPlaceSearchViewModel(),
) {
    val context = LocalContext.current
    val keyboard = LocalSoftwareKeyboardController.current
    val focusManager = LocalFocusManager.current
    val lifecycle = LocalLifecycleOwner.current
    val state by viewModel.state.collectAsStateWithLifecycle()
    val origin by viewModel.origin.collectAsStateWithLifecycle()
    val mapState by viewModel.map.collectAsStateWithLifecycle()
    val mapBars by viewModel.markers.collectAsStateWithLifecycle()
    val selectedId by viewModel.selectedBarId.collectAsStateWithLifecycle()
    val focusBarId by viewModel.focusBarId.collectAsStateWithLifecycle()
    val placeState by placeSearchViewModel.state.collectAsStateWithLifecycle()
    val searchedPlace by placeSearchViewModel.selected.collectAsStateWithLifecycle()
    val focusSearchedPlace by placeSearchViewModel.focus.collectAsStateWithLifecycle()
    val carousel = (state as? NearbyUiState.Success)?.bars.orEmpty()
    val selected: BarPin? = mapBars.firstOrNull { it.barId == selectedId }
        ?: carousel.firstOrNull { it.barId == selectedId }
    var hasRequestedPermission by rememberSaveable { mutableStateOf(false) }
    // Keep Native MapView mounted beneath the full-page list so switching modes
    // does not lose its camera/labels or reinitialize the Kakao SDK.
    var listVisible by rememberSaveable { mutableStateOf(false) }
    var placeQuery by rememberSaveable { mutableStateOf("") }
    var placeResultsVisible by rememberSaveable { mutableStateOf(false) }
    var recenterToken by remember { mutableIntStateOf(0) }
    var viewportRetryToken by remember { mutableIntStateOf(0) }
    var mapView by remember { mutableStateOf<MapView?>(null) }
    var leaving by remember { mutableStateOf(false) }
    var navigating by remember { mutableStateOf(false) }

    fun searchPlaces() {
        listVisible = false
        placeResultsVisible = true
        focusManager.clearFocus()
        keyboard?.hide()
        placeSearchViewModel.search(placeQuery)
    }
    fun choosePlace(place: MapPlace) {
        if (placeSearchViewModel.select(place)) {
            viewModel.clearSelection()
            listVisible = false
            placeResultsVisible = false
            placeQuery = ""
            focusManager.clearFocus()
            keyboard?.hide()
        }
    }
    fun back() {
        if (!leaving) {
            placeSearchViewModel.clear()
            leaving = true
            mapView?.let(::hideNearbyNativeSurface)
            viewModel.leaveDiscovery()
            onBack()
        }
    }
    fun detail(id: String) {
        if (!leaving && !navigating) {
            navigating = true
            mapView?.let(::hideNearbyNativeSurface)
            onOpenBarDetail(id)
        }
    }
    BackHandler(enabled = !leaving && !placeResultsVisible, onBack = ::back)
    BackHandler(enabled = !leaving && placeResultsVisible) {
        placeResultsVisible = false
        keyboard?.hide()
    }

    fun updatePermissions() {
        viewModel.updatePermission(nearbyPermission(
            context, context as? Activity, hasRequestedPermission))
    }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) {
        hasRequestedPermission = true
        updatePermissions()
    }
    LaunchedEffect(Unit) {
        viewModel.beginDiscovery()
        updatePermissions()
    }
    val onResume = rememberUpdatedState(newValue = {
        navigating = false
        updatePermissions()
    })
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) onResume.value()
        }
        lifecycle.lifecycle.addObserver(observer)
        onDispose { lifecycle.lifecycle.removeObserver(observer) }
    }
    LaunchedEffect(listVisible, mapView) {
        mapView?.let {
            if (listVisible) hideNearbyNativeSurface(it)
            else showNearbyNativeSurface(it)
        }
    }

    I2CustomerSearchTheme {
        // The map owns the entire screen; header, list and selected-card overlay
        // draw on TOP of it instead of shrinking the map's available height.
        Box(Modifier.fillMaxSize()) {
            val fix = origin
            if (fix != null && !leaving) {
                NearbyKakaoMap(
                    origin = fix,
                    bars = mapBars,
                    selectedBarId = selectedId,
                    focusTarget = selected,
                    focusBarId = focusBarId,
                    initialCamera = viewModel.savedCamera(),
                    listCovered = listVisible,
                    searchedPlace = searchedPlace,
                    focusSearchedPlace = focusSearchedPlace,
                    onSearchedPlaceFocusApplied = placeSearchViewModel::consumeFocus,
                    onFocusApplied = viewModel::consumeFocusRequest,
                    onCameraChanged = viewModel::rememberCamera,
                    onMapCameraMoving = viewModel::onMapCameraMoving,
                    onMapViewportUnavailable = viewModel::onMapViewportUnavailable,
                    viewportRetryToken = viewportRetryToken,
                    onSelectBar = {
                        placeSearchViewModel.clear()
                        viewModel.selectBar(it)
                    },
                    onViewportChanged = { viewModel.onViewportChanged(it) },
                    recenterToken = recenterToken,
                    onMapViewChanged = { attached ->
                        mapView = attached
                        if (leaving || listVisible) attached?.let(::hideNearbyNativeSurface)
                    },
                    modifier = Modifier.fillMaxSize(),
                )
            } else if (!leaving) {
                Box(
                    Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background),
                    contentAlignment = Alignment.Center,
                ) {
                    when (val current = state) {
                        NearbyUiState.Initial, NearbyUiState.LoadingLocation, NearbyUiState.LoadingBars ->
                            NearbyStatus("현재 위치를 확인하고 있습니다.", loading = true)
                        NearbyUiState.PermissionRequired -> NearbyStatus(
                            "지도를 보려면 위치 권한이 필요합니다.",
                            button = "위치 권한 허용",
                            onAction = {
                                permissionLauncher.launch(arrayOf(
                                    Manifest.permission.ACCESS_COARSE_LOCATION,
                                    Manifest.permission.ACCESS_FINE_LOCATION))
                            })
                        NearbyUiState.PermissionPermanentlyDenied -> NearbyStatus(
                            "위치 권한을 사용할 수 없습니다.",
                            button = "앱 설정 열기",
                            onAction = {
                                context.startActivity(
                                    Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                                        data = Uri.parse("package:${context.packageName}")
                                    })
                            })
                        NearbyUiState.LocationServicesDisabled -> NearbyStatus(
                            "위치 서비스를 켠 뒤 다시 시도해 주세요.",
                            button = "위치 설정",
                            onAction = { context.startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)) })
                        is NearbyUiState.Error -> NearbyStatus(
                            current.message,
                            button = if (current.canRetry) "다시 시도" else null,
                            onAction = viewModel::refresh)
                        else -> NearbyStatus("현재 위치를 확인할 수 없습니다.",
                            button = "다시 시도", onAction = viewModel::refresh)
                    }
                }
            }

            if (fix != null && !leaving && listVisible) {
                // Full map-area overlay, not another destination or bottom sheet.
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    NearbyFullList(
                        state = mapState,
                        bars = mapBars,
                        onRetry = { viewportRetryToken++ },
                        onSelect = { barId ->
                            placeSearchViewModel.clear()
                            if (viewModel.selectBar(barId)) listVisible = false
                        },
                        onOpenDetail = ::detail,
                    )
                }
            }

            if (fix != null && !leaving && !listVisible) {
                // Display messages only when actionable or when Backend cannot
                // cover the full viewport. No permanent caption below the map.
                val hint = when (val current = mapState) {
                    is MapDiscoveryState.Error -> current.message
                    is MapDiscoveryState.Ready ->
                        if (current.bars.isEmpty()) "이 지도 영역에 매장이 없습니다." else null
                    MapDiscoveryState.TooWide -> "지도를 확대하면 매장을 볼 수 있습니다."
                    else -> null
                }
                // A single bottom-anchored stack prevents the status message
                // from colliding with a selected bar card on different font
                // scales or when its address wraps to two lines.
                val selectedBar = selected
                if (hint != null || selectedBar != null) {
                    Column(
                        modifier = Modifier.align(Alignment.BottomCenter)
                            .fillMaxWidth()
                            .padding(
                                start = 18.dp,
                                end = 18.dp,
                                bottom = if (selectedBar != null) 90.dp else 148.dp,
                            ),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        if (hint != null) {
                            Surface(
                                shape = RoundedCornerShape(18.dp),
                                color = MaterialTheme.colorScheme.surface.copy(alpha = 0.96f),
                                shadowElevation = 3.dp,
                            ) {
                                Row(
                                    modifier = Modifier.padding(
                                        horizontal = 14.dp, vertical = 9.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                                ) {
                                    Text(hint, style = MaterialTheme.typography.bodySmall)
                                    if (mapState is MapDiscoveryState.Error) {
                                        TextButton(onClick = { viewportRetryToken++ }) {
                                            Text("재시도")
                                        }
                                    }
                                }
                            }
                        }
                        if (selectedBar != null) {
                            Surface(
                                onClick = { detail(selectedBar.barId) },
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(18.dp),
                                shadowElevation = 6.dp,
                                color = MaterialTheme.colorScheme.surface,
                            ) {
                                Row(
                                    modifier = Modifier.padding(
                                        horizontal = 16.dp, vertical = 14.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    Column(Modifier.weight(1f)) {
                                        Text(
                                            selectedBar.name,
                                            style = MaterialTheme.typography.titleMedium,
                                            maxLines = 1,
                                        )
                                        Text(
                                            selectedBar.address,
                                            style = MaterialTheme.typography.bodySmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                                            maxLines = 2,
                                        )
                                    }
                                    Text(
                                        "상세 보기 ›",
                                        style = MaterialTheme.typography.labelMedium,
                                        color = MaterialTheme.colorScheme.primary,
                                    )
                                }
                            }
                        }
                    }
                }
                // Compact target-style location control near the bottom right.
                Surface(
                    onClick = { recenterToken++ },
                    modifier = Modifier.align(Alignment.BottomEnd)
                        .padding(end = 16.dp, bottom = 24.dp)
                        .size(52.dp),
                    shape = CircleShape,
                    shadowElevation = 5.dp,
                    color = MaterialTheme.colorScheme.surface,
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text("⌖", style = MaterialTheme.typography.headlineMedium,
                            modifier = Modifier.semantics { contentDescription = "내 위치로 이동" })
                    }
                }
            }

            if (fix != null && !leaving) {
                Surface(
                    onClick = { listVisible = !listVisible },
                    modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 24.dp),
                    shape = RoundedCornerShape(50.dp),
                    shadowElevation = 5.dp,
                    color = MaterialTheme.colorScheme.surface,
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 22.dp, vertical = 13.dp),
                        horizontalArrangement = Arrangement.spacedBy(9.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(if (listVisible) "▣" else "☰", style = MaterialTheme.typography.titleMedium)
                        Text(if (listVisible) "지도보기" else "목록보기",
                            style = MaterialTheme.typography.titleSmall)
                    }
                }
            }

            if (placeResultsVisible && !leaving) {
                // Location-name results stay in this destination and overlay
                // the map; selecting one recenters Kakao Map without creating
                // a BottleMap bar detail route.
                Surface(
                    modifier = Modifier.align(Alignment.TopCenter)
                        .fillMaxWidth()
                        .padding(start = 72.dp, end = 12.dp, top = 78.dp)
                        .heightIn(max = 320.dp),
                    color = MaterialTheme.colorScheme.surface,
                    shape = RoundedCornerShape(16.dp),
                    shadowElevation = 8.dp,
                ) {
                    when (val result = placeState) {
                        MapPlaceSearchState.Idle -> Text(
                            "장소 이름을 입력해 주세요.",
                            modifier = Modifier.padding(16.dp),
                            textAlign = TextAlign.Center,
                        )
                        MapPlaceSearchState.Loading -> Box(
                            Modifier.fillMaxWidth().padding(24.dp),
                            contentAlignment = Alignment.Center,
                        ) { CircularProgressIndicator() }
                        is MapPlaceSearchState.Error -> Column(
                            modifier = Modifier.fillMaxWidth().padding(14.dp),
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            Text(result.message, textAlign = TextAlign.Center)
                            TextButton(onClick = ::searchPlaces) { Text("다시 검색") }
                        }
                        is MapPlaceSearchState.Results -> {
                            if (result.places.isEmpty()) {
                                Text(
                                    "검색 결과가 없습니다.\n다른 장소명으로 검색해 보세요.",
                                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                                    textAlign = TextAlign.Start,
                                )
                            } else {
                                LazyColumn {
                                    items(result.places) { place ->
                                        Surface(
                                            onClick = { choosePlace(place) },
                                            modifier = Modifier.fillMaxWidth(),
                                            color = MaterialTheme.colorScheme.surface,
                                        ) {
                                            Column(
                                                modifier = Modifier.padding(
                                                    horizontal = 16.dp, vertical = 10.dp),
                                                verticalArrangement = Arrangement.spacedBy(3.dp),
                                            ) {
                                                Text(place.name,
                                                    style = MaterialTheme.typography.titleSmall)
                                                if (place.address.isNotBlank()) {
                                                    Text(place.address,
                                                        style = MaterialTheme.typography.bodySmall,
                                                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // A compact back arrow + Search tab. No separate page title/filters/tags.
            Row(
                modifier = Modifier.fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Surface(
                    onClick = ::back,
                    shape = CircleShape,
                    shadowElevation = 4.dp,
                    color = MaterialTheme.colorScheme.surface,
                    modifier = Modifier.size(48.dp),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text("‹", style = MaterialTheme.typography.headlineMedium,
                            modifier = Modifier.semantics { contentDescription = "검색 화면으로 돌아가기" })
                    }
                }
                TextField(
                    value = placeQuery,
                    onValueChange = {
                        placeQuery = it
                        placeResultsVisible = false
                    },
                    modifier = Modifier.weight(1f).height(56.dp),
                    singleLine = true,
                    shape = RoundedCornerShape(28.dp),
                    placeholder = { Text("지하철역 · 매장 · 주소 검색", maxLines = 1) },
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                    keyboardActions = KeyboardActions(onSearch = { searchPlaces() }),
                    trailingIcon = {
                        TextButton(onClick = ::searchPlaces) { Text("검색") }
                    },
                    colors = TextFieldDefaults.colors(
                        focusedContainerColor = MaterialTheme.colorScheme.surface,
                        unfocusedContainerColor = MaterialTheme.colorScheme.surface,
                        // Material3 TextField draws an underline even with a
                        // rounded shape. It appears gold when focused and pale
                        // when unfocused; this map search should have no line.
                        focusedIndicatorColor = Color.Transparent,
                        unfocusedIndicatorColor = Color.Transparent,
                        disabledIndicatorColor = Color.Transparent,
                        errorIndicatorColor = Color.Transparent,
                    ),
                )
            }
        }
    }
}

@Composable
internal fun nearbyBarsViewModel(
    owner: androidx.lifecycle.ViewModelStoreOwner =
        checkNotNull(androidx.lifecycle.viewmodel.compose.LocalViewModelStoreOwner.current),
): NearbyBarsViewModel {
    val context = LocalContext.current.applicationContext
    val factory = remember(context) {
        object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(
                modelClass: Class<T>,
                extras: CreationExtras,
            ): T = NearbyBarsViewModel(
                locationSource = AndroidNearbyLocationSource(context),
                barsSource = BackendNearbyBarsRepository(),
                savedStateHandle = extras.createSavedStateHandle(),
            ) as T
        }
    }
    return viewModel(viewModelStoreOwner = owner, factory = factory)
}

private fun nearbyPermission(
    context: Context,
    activity: Activity?,
    hasRequested: Boolean,
): NearbyPermission {
    val fine = ContextCompat.checkSelfPermission(
        context, Manifest.permission.ACCESS_FINE_LOCATION,
    ) == PackageManager.PERMISSION_GRANTED
    if (fine) return NearbyPermission.PRECISE
    val coarse = ContextCompat.checkSelfPermission(
        context, Manifest.permission.ACCESS_COARSE_LOCATION,
    ) == PackageManager.PERMISSION_GRANTED
    if (coarse) return NearbyPermission.APPROXIMATE

    // shouldShowRequestPermissionRationale=false can mean initial state.
    // Distinguish using a persisted record of an explicit user request.
    val shouldExplain = activity != null && (
        ActivityCompat.shouldShowRequestPermissionRationale(
            activity, Manifest.permission.ACCESS_FINE_LOCATION,
        ) || ActivityCompat.shouldShowRequestPermissionRationale(
            activity, Manifest.permission.ACCESS_COARSE_LOCATION,
        )
    )
    return if (hasRequested && !shouldExplain) {
        NearbyPermission.PERMANENTLY_DENIED
    } else {
        NearbyPermission.NONE
    }
}

@Composable
private fun NearbyStatus(
    message: String,
    button: String? = null,
    onAction: () -> Unit = {},
    loading: Boolean = false,
) {
    Column(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 20.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        if (loading) CircularProgressIndicator()
        Text(
            message,
            modifier = Modifier.fillMaxWidth(),
            textAlign = TextAlign.Center,
            color = MaterialTheme.colorScheme.onBackground,
        )
        if (button != null) OutlinedButton(onClick = onAction) { Text(button) }
    }
}

@Composable
private fun NearbyCarousel(
    bars: List<NearbyBar>,
    selectedBarId: String?,
    onSelect: (String) -> Boolean,
    onOpenDetail: (String) -> Unit,
) {
    val listState = rememberLazyListState()
    LaunchedEffect(selectedBarId, bars) {
        val index = bars.indexOfFirst { it.barId == selectedBarId }
        if (index >= 0) listState.animateScrollToItem(index)
    }
    LazyRow(
        state = listState,
        contentPadding = PaddingValues(horizontal = 16.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        modifier = Modifier.padding(bottom = 10.dp),
    ) {
        items(bars, key = { it.barId }) { bar ->
            val selected = bar.barId == selectedBarId
            OutlinedCard(
                onClick = { onSelect(bar.barId) },
                modifier = Modifier.fillParentMaxWidth(0.78f).heightIn(min = 112.dp),
                border = BorderStroke(
                    if (selected) 2.dp else 1.dp,
                    if (selected) MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.outlineVariant,
                ),
            ) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(bar.name, style = MaterialTheme.typography.titleMedium)
                    Text("${bar.distanceMeters.toInt()}m",
                        color = MaterialTheme.colorScheme.primary)
                    Text(bar.address, style = MaterialTheme.typography.bodySmall)
                    Text(bar.menuUpdatedAt?.let(::formatMenuTimestamp) ?: "메뉴 등록 전",
                        style = MaterialTheme.typography.labelSmall)
                    if (selected) TextButton(onClick = { onOpenDetail(bar.barId) }) {
                        Text("Bar Detail →")
                    }
                }
            }
        }
    }
}

internal fun hideNearbyNativeSurface(view: MapView) {
    view.visibility = View.INVISIBLE
    view.surfaceView?.visibility = View.INVISIBLE
}
/**
 * The entire visible map data set, NOT the independent user-centered 1km
 * carousel. The overlay occupies the full map screen, with a fixed toggle.
 */
@Composable
private fun NearbyFullList(
    state: MapDiscoveryState,
    bars: List<MapBar>,
    onRetry: () -> Unit,
    onSelect: (String) -> Unit,
    onOpenDetail: (String) -> Unit,
) {
    when (state) {
        MapDiscoveryState.Initial, MapDiscoveryState.Loading ->
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        is MapDiscoveryState.Error ->
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                NearbyStatus("매장 목록을 불러오지 못했습니다.",
                    button = "다시 시도", onAction = onRetry)
            }
        MapDiscoveryState.TooWide ->
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                NearbyStatus("지도 영역이 너무 넓습니다. 지도를 확대해 주세요.")
            }
        is MapDiscoveryState.Ready -> {
            if (bars.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("이 지도 영역에 매장이 없습니다.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(top = 84.dp, bottom = 106.dp,
                        start = 16.dp, end = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    items(bars, key = { it.barId }) { bar ->
                        OutlinedCard(
                            onClick = { onSelect(bar.barId) },
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Row(
                                Modifier.fillMaxWidth().padding(16.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Column(Modifier.weight(1f),
                                    verticalArrangement = Arrangement.spacedBy(5.dp)) {
                                    Text(bar.name, style = MaterialTheme.typography.titleMedium)
                                    Text(bar.address, style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                                }
                                TextButton(onClick = { onOpenDetail(bar.barId) }) {
                                    Text("상세 보기")
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}


internal fun showNearbyNativeSurface(view: MapView) {
    view.visibility = View.VISIBLE
    view.surfaceView?.visibility = View.VISIBLE
}
