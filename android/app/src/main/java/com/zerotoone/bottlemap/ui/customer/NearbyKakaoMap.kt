// AI-assisted Kakao multi-bar map (2026-10-18, I2-A8). Actual catalog pending.
package com.zerotoone.bottlemap.ui.customer

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.os.Handler
import android.os.Looper
import android.view.View
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.kakao.vectormap.KakaoMap
import com.kakao.vectormap.KakaoMapReadyCallback
import com.kakao.vectormap.LatLng
import com.kakao.vectormap.MapLifeCycleCallback
import com.kakao.vectormap.MapView
import com.kakao.vectormap.camera.CameraUpdateFactory
import com.kakao.vectormap.label.Label
import com.kakao.vectormap.label.LabelLayer
import com.kakao.vectormap.label.LabelOptions
import com.kakao.vectormap.label.LabelStyle
import com.kakao.vectormap.label.LabelTextBuilder
import com.zerotoone.bottlemap.BuildConfig
import com.zerotoone.bottlemap.data.NearbyBar
import com.zerotoone.bottlemap.ui.common.DelayedLoading
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.delay

private sealed interface NearbyMapStatus {
    data object Loading : NearbyMapStatus
    data object Ready : NearbyMapStatus
    data object Error : NearbyMapStatus
}

@Composable
fun NearbyKakaoMap(
    bars: List<NearbyBar>,
    selectedBarId: String?,
    onSelectBar: (String) -> Unit,
    onMapViewChanged: (MapView?) -> Unit,
    modifier: Modifier = Modifier,
) {
    if (bars.isEmpty()) return
    if (BuildConfig.KAKAO_NATIVE_APP_KEY.isBlank()) {
        Text("Kakao Native App Key 설정이 필요합니다.", modifier = modifier.padding(16.dp))
        return
    }
    var attempt by remember { mutableIntStateOf(0) }
    // A new map instance is constructed only when the data set or Retry changes;
    // selecting a different card does not recreate native MapView or labels.
    key(bars, attempt) {
        var status by remember { mutableStateOf<NearbyMapStatus>(NearbyMapStatus.Loading) }
        var map by remember { mutableStateOf<KakaoMap?>(null) }
        var labels by remember { mutableStateOf<Map<String, Label>>(emptyMap()) }
        val selected = bars.firstOrNull { it.barId == selectedBarId }

        // Fail visibly instead of leaving an endless loader when the native
        // Kakao SDK never calls onMapReady/onMapError.
        LaunchedEffect(status) {
            if (status == NearbyMapStatus.Loading) {
                delay(25_000)
                if (status == NearbyMapStatus.Loading) status = NearbyMapStatus.Error
            }
        }

        // This updates in place: NO duplicate addLabel on carousel swipes.
        LaunchedEffect(selectedBarId, map, labels) {
            val kakaoMap = map ?: return@LaunchedEffect
            labels.forEach { (id, label) ->
                val style = nearbyMarkerStyle(id == selectedBarId)
                label.setStyles(style)
                label.invalidate()
            }
            if (selected != null && labels.containsKey(selected.barId)) {
                kakaoMap.moveCamera(
                    CameraUpdateFactory.newCenterPosition(
                        LatLng.from(selected.location.latitude, selected.location.longitude),
                    ),
                )
            }
        }

        Box(modifier = modifier) {
            NearbyNativeMap(
                bars = bars,
                initialBarId = selectedBarId,
                onMapViewChanged = onMapViewChanged,
                onSelectBar = onSelectBar,
                onReady = { readyMap, readyLabels ->
                    map = readyMap
                    labels = readyLabels
                    status = NearbyMapStatus.Ready
                },
                onError = { status = NearbyMapStatus.Error },
                modifier = Modifier.fillMaxSize(),
            )
            when (status) {
                NearbyMapStatus.Loading -> DelayedLoading(Modifier.fillMaxSize()) {
                    Box(
                        modifier = Modifier.fillMaxSize().background(
                            MaterialTheme.colorScheme.surface.copy(alpha = 0.95f),
                        ),
                        contentAlignment = Alignment.Center,
                    ) { CircularProgressIndicator() }
                }
                NearbyMapStatus.Ready -> Unit
                NearbyMapStatus.Error -> Box(
                    modifier = Modifier.fillMaxSize()
                        .background(MaterialTheme.colorScheme.surface),
                    contentAlignment = Alignment.Center,
                ) {
                    Button(onClick = { attempt++ }) { Text("지도 다시 시도") }
                }
            }
        }
    }
}

@Composable
private fun NearbyNativeMap(
    bars: List<NearbyBar>,
    initialBarId: String?,
    onMapViewChanged: (MapView?) -> Unit,
    onSelectBar: (String) -> Unit,
    onReady: (KakaoMap, Map<String, Label>) -> Unit,
    onError: () -> Unit,
    modifier: Modifier,
) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val owner = LocalLifecycleOwner.current
    val latestSelection = rememberUpdatedState(onSelectBar)
    val view = remember(bars) {
        try { MapView(context) } catch (_: Exception) { null }
    }
    if (view == null) {
        LaunchedEffect(bars) { onError() }
        return
    }
    AndroidView(factory = { view }, modifier = modifier)

    DisposableEffect(view, owner, bars) {
        onMapViewChanged(view)
        val disposed = AtomicBoolean(false)
        val handler = Handler(Looper.getMainLooper())
        fun report(action: () -> Unit) {
            handler.post { if (!disposed.get()) action() }
        }
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> {
                    view.visibility = View.VISIBLE
                    view.surfaceView?.visibility = View.VISIBLE
                    runCatching { view.resume() }
                }
                Lifecycle.Event.ON_PAUSE -> {
                    hideNearbyNativeSurface(view)
                    runCatching { view.pause() }
                }
                else -> Unit
            }
        }
        owner.lifecycle.addObserver(observer)
        try {
            view.start(
                object : MapLifeCycleCallback() {
                    override fun onMapDestroy() {
                        report(onError)
                    }
                    override fun onMapError(error: Exception) {
                        report(onError)
                    }
                },
                object : KakaoMapReadyCallback() {
                    override fun getPosition(): LatLng {
                        val initial = bars.firstOrNull { it.barId == initialBarId }
                            ?: bars.first()
                        return LatLng.from(initial.location.latitude, initial.location.longitude)
                    }
                    override fun getZoomLevel(): Int = 16

                    override fun onMapReady(kakaoMap: KakaoMap) {
                        try {
                            val layer = kakaoMap.labelManager?.layer
                                ?: throw IllegalStateException("Kakao label layer unavailable")
                            val created = linkedMapOf<String, Label>()
                            bars.forEach { bar ->
                                val options = LabelOptions.from(
                                    bar.barId,
                                    LatLng.from(bar.location.latitude, bar.location.longitude),
                                )
                                    .setStyles(nearbyMarkerStyle(bar.barId == initialBarId))
                                    .setClickable(true)
                                    .setTag(bar.barId)
                                    .setTexts(LabelTextBuilder().setTexts(bar.name))
                                val label = layer.addLabel(options)
                                    ?: throw IllegalStateException("Missing Kakao label")
                                created[bar.barId] = label
                            }
                            kakaoMap.setOnLabelClickListener(
                                object : KakaoMap.OnLabelClickListener {
                                    override fun onLabelClicked(
                                        kakaoMap: KakaoMap,
                                        layer: LabelLayer,
                                        label: Label,
                                    ): Boolean {
                                        val selectedId = label.tag as? String ?: return false
                                        if (!created.containsKey(selectedId)) return false
                                        report { latestSelection.value(selectedId) }
                                        return true
                                    }
                                },
                            )
                            report { onReady(kakaoMap, created) }
                        } catch (_: Exception) {
                            report(onError)
                        }
                    }
                },
            )
            view.setFinishManually(true)
            if (owner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) {
                view.resume()
            }
        } catch (_: Exception) {
            report(onError)
        }

        onDispose {
            disposed.set(true)
            onMapViewChanged(null)
            hideNearbyNativeSurface(view)
            owner.lifecycle.removeObserver(observer)
            runCatching { view.pause() }
            runCatching { view.finish() }
        }
    }
}

/** Shared icon anchor (bottom-center): no position drift when zooming. */
private fun nearbyMarkerStyle(selected: Boolean): LabelStyle {
    val pin = Bitmap.createBitmap(40, 52, Bitmap.Config.ARGB_8888)
    val canvas = Canvas(pin)
    val path = Path().apply {
        moveTo(20f, 51f)
        cubicTo(10f, 38f, 4f, 26f, 4f, 20f)
        cubicTo(4f, 10f, 11f, 4f, 20f, 4f)
        cubicTo(29f, 4f, 36f, 10f, 36f, 20f)
        cubicTo(36f, 26f, 30f, 38f, 20f, 51f)
        close()
    }
    canvas.drawPath(
        path,
        Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = if (selected) Color.rgb(214, 183, 126) else Color.rgb(63, 91, 122)
        },
    )
    canvas.drawCircle(
        20f, 20f, 6f,
        Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE },
    )
    return LabelStyle.from(pin)
        .setAnchorPoint(0.5f, 1.0f)
        .setTextStyles(18, Color.WHITE, 2, Color.rgb(12, 22, 38))
}
