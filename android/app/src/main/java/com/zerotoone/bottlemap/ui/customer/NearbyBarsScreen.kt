// AI-assisted Compose UI (2026-10-18, I2-A7/A8). Integrated with A9 API PR #43.
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
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
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
import com.zerotoone.bottlemap.data.NearbyBar

@Composable
fun NearbyBarsScreen(
    onBack: () -> Unit,
    onOpenBarDetail: (String) -> Unit,
    viewModel: NearbyBarsViewModel = nearbyBarsViewModel(),
) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current
    val state by viewModel.state.collectAsStateWithLifecycle()
    val origin by viewModel.origin.collectAsStateWithLifecycle()
    val mapState by viewModel.map.collectAsStateWithLifecycle()
    val mapBars by viewModel.markers.collectAsStateWithLifecycle()
    val selectedId by viewModel.selectedBarId.collectAsStateWithLifecycle()
    val carousel = (state as? NearbyUiState.Success)?.bars.orEmpty()
    val selected = (mapBars + carousel).firstOrNull { it.barId == selectedId }
    var hasRequestedPermission by rememberSaveable { mutableStateOf(false) }
    var recenterToken by rememberSaveable { mutableIntStateOf(0) }
    var mapView by remember { mutableStateOf<MapView?>(null) }
    var leaving by remember { mutableStateOf(false) }
    var navigating by remember { mutableStateOf(false) }

    fun back() {
        if (!leaving) {
            leaving = true
            mapView?.let(::hideNearbyNativeSurface)
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
    BackHandler(enabled = !leaving, onBack = ::back)

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
    LaunchedEffect(Unit) { updatePermissions() }
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

    I2CustomerSearchTheme {
        Column(Modifier.fillMaxSize()) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = ::back) { Text("←") }
                Text("지도에서 바 찾기", style = MaterialTheme.typography.titleLarge)
            }
            val fix = origin
            if (fix != null && !leaving) {
                Box(Modifier.fillMaxWidth().weight(1f)) {
                    NearbyKakaoMap(
                        origin = fix,
                        bars = mapBars,
                        selectedBarId = selectedId,
                        focusTarget = selected,
                        onSelectBar = { viewModel.selectBar(it) },
                        onViewportChanged = { viewModel.onViewportChanged(it) },
                        recenterToken = recenterToken,
                        onMapViewChanged = {
                            mapView = it
                            if (leaving) it?.let(::hideNearbyNativeSurface)
                        },
                        modifier = Modifier.fillMaxSize(),
                    )
                    OutlinedButton(onClick = { recenterToken++ },
                        modifier = Modifier.align(Alignment.TopEnd).padding(12.dp)) {
                        Text("⌖ 내 위치")
                    }
                }
                if (ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION)
                    != PackageManager.PERMISSION_GRANTED) {
                    Text("대략적인 위치를 사용 중입니다. 거리에는 오차가 있을 수 있습니다.",
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.bodySmall)
                }
                when (val mapResult = mapState) {
                    MapDiscoveryState.Initial, MapDiscoveryState.Loading ->
                        Text("지도에서 바를 찾는 중…", modifier = Modifier.padding(horizontal = 16.dp),
                            style = MaterialTheme.typography.bodySmall)
                    is MapDiscoveryState.Ready ->
                        Text(
                            when {
                                mapResult.partiallyCovered ->
                                    "지도 범위가 3km 한도를 초과합니다. 중심 3km 이내 바만 표시됩니다."
                                mapResult.bars.isEmpty() ->
                                    "이 지도 영역에 등록된 바가 없습니다. 지도를 이동해 보세요."
                                else -> "지도 중심 ${mapResult.radiusMeters}m · ${mapResult.bars.size}개 바"
                            },
                            modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                            style = MaterialTheme.typography.bodySmall)
                    is MapDiscoveryState.Error ->
                        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                            verticalAlignment = Alignment.CenterVertically) {
                            Text(mapResult.message, modifier = Modifier.weight(1f),
                                style = MaterialTheme.typography.bodySmall)
                            TextButton(onClick = viewModel::retryMap) { Text("재시도") }
                        }
                }
                if (selected != null) OutlinedCard(
                    onClick = { detail(selected.barId) },
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
                ) {
                    Column(Modifier.padding(10.dp)) {
                        Text(selected.name, style = MaterialTheme.typography.titleSmall)
                        Text(selected.address, style = MaterialTheme.typography.bodySmall)
                        Text("Bar Detail 보기 →", color = MaterialTheme.colorScheme.primary)
                    }
                }
                Text("내 위치에서 1km · 가까운 순서",
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                    style = MaterialTheme.typography.titleSmall)
                when (val current = state) {
                    NearbyUiState.LoadingBars, NearbyUiState.LoadingLocation, NearbyUiState.Initial ->
                        NearbyStatus("1km 안의 바를 조회 중입니다.", loading = true)
                    NearbyUiState.Empty ->
                        NearbyStatus("현재 위치에서 1km 이내에 등록된 바가 없습니다.",
                            button = "다시 검색", onAction = viewModel::refresh)
                    is NearbyUiState.Error ->
                        NearbyStatus(current.message,
                            button = if (current.canRetry) "다시 시도" else null,
                            onAction = viewModel::refresh)
                    is NearbyUiState.Success -> NearbyCarousel(
                        bars = current.bars, selectedBarId = selectedId,
                        onSelect = viewModel::selectBar, onOpenDetail = ::detail)
                    else -> Unit
                }
            } else if (!leaving) {
                when (val current = state) {
                    NearbyUiState.Initial -> NearbyStatus("위치 권한을 확인하고 있습니다.")
                    NearbyUiState.PermissionRequired -> NearbyStatus(
                        "지도를 보려면 위치 권한이 필요합니다. 주류 검색은 권한 없이 사용할 수 있어요.",
                        button = "위치 권한 허용",
                        onAction = {
                            permissionLauncher.launch(arrayOf(
                                Manifest.permission.ACCESS_COARSE_LOCATION,
                                Manifest.permission.ACCESS_FINE_LOCATION))
                        })
                    NearbyUiState.PermissionPermanentlyDenied -> NearbyStatus(
                        "위치 권한을 사용할 수 없습니다. Android 앱 설정에서 변경해 주세요.",
                        button = "앱 설정 열기",
                        onAction = {
                            context.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                                data = Uri.parse("package:${context.packageName}")
                            })
                        })
                    NearbyUiState.LocationServicesDisabled -> NearbyStatus(
                        "위치 서비스가 꺼져 있습니다. 위치 서비스를 켜고 다시 시도해 주세요.",
                        button = "위치 설정 열기",
                        onAction = { context.startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)) })
                    NearbyUiState.LoadingLocation, NearbyUiState.LoadingBars ->
                        NearbyStatus("현재 위치를 확인하고 있습니다.", loading = true)
                    is NearbyUiState.Error -> NearbyStatus(current.message,
                        button = if (current.canRetry) "다시 시도" else null,
                        onAction = viewModel::refresh)
                    else -> NearbyStatus("위치 정보를 확인할 수 없습니다.",
                        button = "다시 시도", onAction = viewModel::refresh)
                }
                TextButton(onClick = ::back) { Text("검색으로 돌아가기") }
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
        modifier = Modifier.fillMaxWidth().padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        if (loading) CircularProgressIndicator()
        Text(message, color = MaterialTheme.colorScheme.onBackground)
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
