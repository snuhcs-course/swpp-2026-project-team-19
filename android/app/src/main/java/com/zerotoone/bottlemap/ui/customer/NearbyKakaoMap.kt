// Map-first discovery: one native map instance per Retry, markers diffed by barId.
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.kakao.vectormap.GestureType
import com.kakao.vectormap.KakaoMap
import com.kakao.vectormap.KakaoMapReadyCallback
import com.kakao.vectormap.LatLng
import com.kakao.vectormap.MapLifeCycleCallback
import com.kakao.vectormap.MapView
import com.kakao.vectormap.camera.CameraPosition
import com.kakao.vectormap.camera.CameraUpdateFactory
import com.kakao.vectormap.label.Label
import com.kakao.vectormap.label.LabelLayer
import com.kakao.vectormap.label.LabelOptions
import com.kakao.vectormap.label.LabelStyle
import com.kakao.vectormap.label.LabelTextBuilder
import com.zerotoone.bottlemap.BuildConfig
import com.zerotoone.bottlemap.data.MAX_NEARBY_API_RADIUS_METERS
import com.zerotoone.bottlemap.data.NearbyBar
import com.zerotoone.bottlemap.data.NearbyCoordinate
import com.zerotoone.bottlemap.data.distanceMeters
import com.zerotoone.bottlemap.ui.common.DelayedLoading
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.ceil
import kotlinx.coroutines.delay

private sealed interface NearbyMapStatus {
    data object Loading : NearbyMapStatus
    data object Ready : NearbyMapStatus
    data object Error : NearbyMapStatus
}

/**
 * Compute a request circle covering visible corners where possible. If the radius
 * exceeds 3000m the server CANNOT cover the full viewport; report that honestly.
 * Geometry is for API query size only, NEVER for re-filtering response markers.
 */
internal fun discoveryViewport(
    center: NearbyCoordinate,
    corners: List<NearbyCoordinate>,
): NearbyViewport {
    require(center.isValid())
    val furthest = corners.asSequence().filter { it.isValid() }
        .map { distanceMeters(center, it) }.maxOrNull()
        ?: MAX_NEARBY_API_RADIUS_METERS.toDouble()
    val padded = ceil(furthest * 1.1).toInt().coerceAtLeast(100)
    return NearbyViewport(
        center,
        padded.coerceAtMost(MAX_NEARBY_API_RADIUS_METERS),
        padded > MAX_NEARBY_API_RADIUS_METERS || corners.size < 4,
    )
}

@Composable
fun NearbyKakaoMap(
    origin: NearbyCoordinate,
    bars: List<NearbyBar>,
    selectedBarId: String?,
    focusTarget: NearbyBar?,
    focusBarId: String?,
    initialCamera: DiscoveryCamera?,
    onFocusApplied: () -> Unit,
    onCameraChanged: (NearbyCoordinate, Int) -> Unit,
    onSelectBar: (String) -> Unit,
    onViewportChanged: (NearbyViewport) -> Unit,
    recenterToken: Int,
    onMapViewChanged: (MapView?) -> Unit,
    modifier: Modifier = Modifier,
) {
    if (BuildConfig.KAKAO_NATIVE_APP_KEY.isBlank()) {
        Text("Kakao Native App Key 설정이 필요합니다.", modifier = modifier.padding(16.dp))
        return
    }
    var attempt by remember { mutableIntStateOf(0) }
    // Changes to bars/selection DO NOT recreate or restart the Native MapView.
    key(attempt) {
        var status by remember { mutableStateOf<NearbyMapStatus>(NearbyMapStatus.Loading) }
        var nativeMap by remember { mutableStateOf<KakaoMap?>(null) }
        val markers = remember { linkedMapOf<String, Pair<NearbyCoordinate, Label>>() }
        val currentSelect = rememberUpdatedState(onSelectBar)
        val currentViewport = rememberUpdatedState(onViewportChanged)
        val currentCameraChanged = rememberUpdatedState(onCameraChanged)
        val ctx = LocalContext.current
        val owner = LocalLifecycleOwner.current
        val view = remember {
            try { MapView(ctx) } catch (_: Exception) { null }
        }

        LaunchedEffect(status) {
            if (status == NearbyMapStatus.Loading) {
                delay(25_000)
                if (status == NearbyMapStatus.Loading) status = NearbyMapStatus.Error
            }
        }

        // In-place, idempotent diff; no duplicate labels across map pans or API replies.
        LaunchedEffect(nativeMap, bars) {
            val map = nativeMap ?: return@LaunchedEffect
            val layer = map.labelManager?.layer ?: return@LaunchedEffect
            val current = bars.filter { it.barId.isNotBlank() && it.location.isValid() &&
                !(it.location.latitude == 0.0 && it.location.longitude == 0.0) }
                .distinctBy { it.barId }.associateBy { it.barId }
            markers.toMap().forEach { (id, stored) ->
                if (current[id]?.location != stored.first) {
                    stored.second.remove()
                    markers.remove(id)
                }
            }
            current.forEach { (id, bar) ->
                if (!markers.containsKey(id)) {
                    val label = layer.addLabel(
                        LabelOptions.from(id,
                            LatLng.from(bar.location.latitude, bar.location.longitude))
                            .setStyles(nearbyMarkerStyle(id == selectedBarId))
                            .setClickable(true)
                            .setTag(id)
                            .setTexts(LabelTextBuilder().setTexts(bar.name)),
                    )
                    if (label != null) markers[id] = bar.location to label
                }
            }
            markers.forEach { (id, stored) ->
                stored.second.setStyles(nearbyMarkerStyle(id == selectedBarId))
                stored.second.invalidate()
            }
        }

        // Only deliberate selection requests can focus a bar. Returning from
        // Bar Detail must NOT re-focus the selected pin over the saved viewport.
        LaunchedEffect(focusBarId, focusTarget, nativeMap) {
            val map = nativeMap ?: return@LaunchedEffect
            val target = focusTarget?.takeIf { it.barId == focusBarId }
                ?: return@LaunchedEffect
            map.moveCamera(CameraUpdateFactory.newCenterPosition(
                LatLng.from(target.location.latitude, target.location.longitude),
            ))
            onFocusApplied()
        }
        LaunchedEffect(recenterToken, nativeMap) {
            if (recenterToken > 0) nativeMap?.moveCamera(
                CameraUpdateFactory.newCenterPosition(
                    LatLng.from(origin.latitude, origin.longitude)))
        }

        Box(modifier = modifier) {
            if (view != null) {
                AndroidView(factory = { view }, modifier = Modifier.fillMaxSize())
                DisposableEffect(view, owner) {
                    onMapViewChanged(view)
                    val disposed = AtomicBoolean(false)
                    val handler = Handler(Looper.getMainLooper())
                    fun post(action: () -> Unit) {
                        handler.post { if (!disposed.get()) action() }
                    }
                    fun publishViewport(map: KakaoMap, cameraPosition: CameraPosition?) {
                        val position = cameraPosition?.position ?: return
                        val center = NearbyCoordinate(position.latitude, position.longitude)
                        if (!center.isValid()) return
                        val width = view.width
                        val height = view.height
                        // If Kakao's surface has not laid out yet, request the
                        // maximum supported 3km and disclose incomplete coverage.
                        val corners = if (width > 0 && height > 0) {
                            listOf(0 to 0, width to 0, 0 to height, width to height)
                                .mapNotNull { (x, y) ->
                                    runCatching { map.fromScreenPoint(x, y) }.getOrNull()
                                        ?.let { NearbyCoordinate(it.latitude, it.longitude) }
                                }
                        } else emptyList()
                        post {
                            currentCameraChanged.value(center, position.zoomLevel)
                            currentViewport.value(discoveryViewport(center, corners))
                        }
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
                                override fun onMapDestroy() { post { status = NearbyMapStatus.Error } }
                                override fun onMapError(error: Exception) {
                                    post { status = NearbyMapStatus.Error }
                                }
                            },
                            object : KakaoMapReadyCallback() {
                                override fun getPosition(): LatLng {
                                    val center = initialCamera?.center ?: origin
                                    return LatLng.from(center.latitude, center.longitude)
                                }
                                override fun getZoomLevel(): Int = initialCamera?.zoomLevel ?: 16
                                override fun onMapReady(map: KakaoMap) {
                                    try {
                                        val layer = map.labelManager?.layer
                                            ?: throw IllegalStateException("No Kakao label layer")
                                        layer.addLabel(
                                            LabelOptions.from("__user_location__",
                                                LatLng.from(origin.latitude, origin.longitude))
                                                .setStyles(userLocationStyle())
                                                .setClickable(false),
                                        )
                                        map.setOnLabelClickListener(
                                            object : KakaoMap.OnLabelClickListener {
                                                override fun onLabelClicked(
                                                    kakaoMap: KakaoMap,
                                                    layer: LabelLayer,
                                                    label: Label,
                                                ): Boolean {
                                                    val id = label.tag as? String ?: return false
                                                    post {
                                                        if (markers.containsKey(id)) currentSelect.value(id)
                                                    }
                                                    return true
                                                }
                                            },
                                        )
                                        map.setOnCameraMoveEndListener(
                                            object : KakaoMap.OnCameraMoveEndListener {
                                                override fun onCameraMoveEnd(
                                                    kakaoMap: KakaoMap,
                                                    position: CameraPosition,
                                                    gestureType: GestureType,
                                                ) {
                                                    publishViewport(kakaoMap, position)
                                                }
                                            },
                                        )
                                        post {
                                            nativeMap = map
                                            status = NearbyMapStatus.Ready
                                        }
                                        // The initial camera position is valid before any gesture.
                                        handler.postDelayed({
                                            if (!disposed.get()) {
                                                publishViewport(map, map.cameraPosition)
                                            }
                                        }, 350L)
                                    } catch (_: Exception) {
                                        post { status = NearbyMapStatus.Error }
                                    }
                                }
                            },
                        )
                        view.setFinishManually(true)
                        if (owner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) {
                            view.resume()
                        }
                    } catch (_: Exception) {
                        post { status = NearbyMapStatus.Error }
                    }
                    onDispose {
                        val lastPosition = nativeMap?.cameraPosition
                        if (lastPosition != null) {
                            val center = NearbyCoordinate(
                                lastPosition.position.latitude, lastPosition.position.longitude)
                            if (center.isValid()) currentCameraChanged.value(center, lastPosition.zoomLevel)
                        }
                        disposed.set(true)
                        onMapViewChanged(null)
                        hideNearbyNativeSurface(view)
                        owner.lifecycle.removeObserver(observer)
                        runCatching { view.pause() }
                        runCatching { view.finish() }
                        markers.clear()
                    }
                }
            } else {
                LaunchedEffect(Unit) { status = NearbyMapStatus.Error }
            }
            when (status) {
                NearbyMapStatus.Loading -> DelayedLoading(Modifier.fillMaxSize()) {
                    Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surface),
                        contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                }
                NearbyMapStatus.Ready -> Unit
                NearbyMapStatus.Error -> Box(
                    Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surface),
                    contentAlignment = Alignment.Center,
                ) {
                    Button(onClick = { attempt++ }) { Text("지도 다시 시도") }
                }
            }
        }
    }
}

private fun userLocationStyle(): LabelStyle {
    val bitmap = Bitmap.createBitmap(32, 32, Bitmap.Config.ARGB_8888)
    Canvas(bitmap).apply {
        drawCircle(16f, 16f, 13f, Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
        })
        drawCircle(16f, 16f, 10f, Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.rgb(39, 126, 225)
        })
    }
    return LabelStyle.from(bitmap).setAnchorPoint(0.5f, 0.5f)
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

