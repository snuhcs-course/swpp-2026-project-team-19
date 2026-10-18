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
    val owner = LocalLifecycleOwner.current
    val state by viewModel.state.collectAsStateWithLifecycle()
    val selectedBarId by viewModel.selectedBarId.collectAsStateWithLifecycle()
    var hasRequestedPermission by rememberSaveable { mutableStateOf(false) }
    var mapView by remember { mutableStateOf<MapView?>(null) }
    var leaving by remember { mutableStateOf(false) }
    var navigatingToDetail by remember { mutableStateOf(false) }

    fun openDetail(id: String) {
        if (navigatingToDetail || leaving) return
        navigatingToDetail = true
        // The native GL Surface can outlive the outgoing Compose destination.
        mapView?.let(::hideNearbyNativeSurface)
        onOpenBarDetail(id)
    }

    fun back() {
        if (leaving) return
        leaving = true
        mapView?.let(::hideNearbyNativeSurface)
        onBack()
    }
    BackHandler(enabled = !leaving, onBack = ::back)

    val activity = context as? Activity
    fun updatePermissions() {
        viewModel.updatePermission(
            nearbyPermission(context, activity, hasRequestedPermission),
        )
    }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) {
        hasRequestedPermission = true
        updatePermissions()
    }

    LaunchedEffect(Unit) { updatePermissions() }
    // No automatic permission dialog on app launch, resume or refusal.
    val currentRefresh = rememberUpdatedState(newValue = {
        navigatingToDetail = false
        updatePermissions()
    })
    DisposableEffect(owner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) currentRefresh.value()
        }
        owner.lifecycle.addObserver(observer)
        onDispose { owner.lifecycle.removeObserver(observer) }
    }

    I2CustomerSearchTheme {
        Column(modifier = Modifier.fillMaxSize()) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(onClick = ::back) { Text("←") }
                Text(
                    text = "내 주변 바 · 500m",
                    style = MaterialTheme.typography.titleLarge,
                    color = MaterialTheme.colorScheme.onBackground,
                )
            }

            when (val current = state) {
                NearbyUiState.Initial -> NearbyStatus("위치 권한 상태를 확인하고 있습니다.")
                NearbyUiState.PermissionRequired -> NearbyStatus(
                    message = "내 주변 바를 보려면 위치 권한이 필요합니다. 기존 주류 검색은 권한 없이 사용할 수 있어요.",
                    button = "위치 권한 허용",
                    onAction = {
                        permissionLauncher.launch(arrayOf(
                            Manifest.permission.ACCESS_COARSE_LOCATION,
                            Manifest.permission.ACCESS_FINE_LOCATION,
                        ))
                    },
                )
                NearbyUiState.PermissionPermanentlyDenied -> NearbyStatus(
                    message = "위치 권한을 사용할 수 없습니다. Android 앱 설정에서 위치 권한을 변경할 수 있어요.",
                    button = "앱 설정 열기",
                    onAction = {
                        context.startActivity(
                            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                                data = Uri.parse("package:${context.packageName}")
                            },
                        )
                    },
                )
                NearbyUiState.ApproximateOnly -> NearbyStatus(
                    message = "대략적 위치만으로는 500m 범위를 정확하게 판정할 수 없습니다. 정확한 위치를 허용해 주세요.",
                    button = "정확한 위치 허용",
                    onAction = {
                        permissionLauncher.launch(arrayOf(
                            Manifest.permission.ACCESS_COARSE_LOCATION,
                            Manifest.permission.ACCESS_FINE_LOCATION,
                        ))
                    },
                )
                NearbyUiState.LocationServicesDisabled -> NearbyStatus(
                    message = "위치 서비스가 꺼져 있습니다. 휴대폰 위치 서비스를 켠 뒤 다시 시도해 주세요.",
                    button = "위치 설정 열기",
                    onAction = {
                        context.startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS))
                    },
                )
                NearbyUiState.LoadingLocation -> NearbyStatus(
                    message = "현재 위치를 확인하고 있습니다.", loading = true,
                )
                NearbyUiState.LoadingBars -> NearbyStatus(
                    message = "500m 안의 바를 확인하고 있습니다.", loading = true,
                )
                NearbyUiState.Empty -> NearbyStatus(
                    message = "반경 500m 안에 등록된 활성 바가 없습니다.",
                    button = "다시 검색", onAction = viewModel::refresh,
                )
                is NearbyUiState.Error -> NearbyStatus(
                    message = current.message,
                    button = if (current.canRetry) "다시 시도" else null,
                    onAction = viewModel::refresh,
                )
                is NearbyUiState.Success -> {
                    // Map controls and carousel both observe selectedBarId.
                    // Selection state never lives inside Kakao marker objects.
                    NearbyResultContent(
                        bars = current.bars,
                        selectedBarId = selectedBarId,
                        onSelect = viewModel::selectBar,
                        onOpenBarDetail = ::openDetail,
                        onMapViewChanged = { mapView = it },
                    )
                }
            }
        }
    }
}

@Composable
private fun nearbyBarsViewModel(): NearbyBarsViewModel {
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
    return viewModel(factory = factory)
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
private fun NearbyResultContent(
    bars: List<NearbyBar>,
    selectedBarId: String?,
    onSelect: (String) -> Boolean,
    onOpenBarDetail: (String) -> Unit,
    onMapViewChanged: (MapView?) -> Unit,
) {
    val selectedBar = bars.firstOrNull { it.barId == selectedBarId }
    val listState = rememberLazyListState()
    LaunchedEffect(selectedBarId, bars) {
        val index = bars.indexOfFirst { it.barId == selectedBarId }
        if (index >= 0) listState.animateScrollToItem(index)
    }
    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        NearbyKakaoMap(
            bars = bars,
            selectedBarId = selectedBarId,
            onSelectBar = { onSelect(it) },
            onMapViewChanged = onMapViewChanged,
            modifier = Modifier.fillMaxWidth().weight(1f),
        )
        Text(
            "거리순 · 현재 위치에서 직선거리 500m 이내",
            modifier = Modifier.padding(horizontal = 16.dp),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            style = MaterialTheme.typography.bodySmall,
        )
        LazyRow(
            state = listState,
            contentPadding = PaddingValues(horizontal = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
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
                    Column(
                        modifier = Modifier.padding(12.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Text(bar.name, style = MaterialTheme.typography.titleMedium)
                        Text(
                            "${bar.distanceMeters.toInt()}m 떨어짐",
                            color = MaterialTheme.colorScheme.primary,
                        )
                        Text(bar.address, style = MaterialTheme.typography.bodySmall)
                        Text(
                            bar.menuUpdatedAt?.let(::formatMenuTimestamp)
                                ?: "아직 등록된 메뉴가 없습니다",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        if (selected) Text(
                            "지도에서 선택됨",
                            style = MaterialTheme.typography.labelSmall,
                        )
                    }
                }
            }
        }
        Button(
            enabled = selectedBar != null,
            onClick = { selectedBar?.let { onOpenBarDetail(it.barId) } },
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp),
        ) { Text("선택한 바 상세 보기") }
    }
}

internal fun hideNearbyNativeSurface(view: MapView) {
    view.visibility = View.INVISIBLE
    view.surfaceView?.visibility = View.INVISIBLE
}
