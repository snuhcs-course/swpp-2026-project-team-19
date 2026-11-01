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
import android.view.MotionEvent
import android.widget.FrameLayout
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
import com.zerotoone.bottlemap.data.BarPin
import com.zerotoone.bottlemap.data.mapBoundsFromCorners
import com.zerotoone.bottlemap.data.viewportCornerPixels
import com.zerotoone.bottlemap.data.MapPlace
import com.zerotoone.bottlemap.data.NearbyCoordinate
import com.zerotoone.bottlemap.ui.common.DelayedLoading
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.delay

private sealed interface NearbyMapStatus {
    data object Loading : NearbyMapStatus
    data object Ready : NearbyMapStatus
    data object Error : NearbyMapStatus
}

/**
 * Observes native map down events even if an SDK child view consumes the gesture.
 * Does not intercept or consume touches: native panning, pin clicks and zoom remain intact.
 */
internal class MapTouchImeDismissLayout(
    context: android.content.Context, private val onDown: () -> Unit,
) : FrameLayout(context) {
    override fun dispatchTouchEvent(event: MotionEvent): Boolean {
        if (event.actionMasked == MotionEvent.ACTION_DOWN) onDown()
        return super.dispatchTouchEvent(event)
    }
}

@Composable
fun NearbyKakaoMap(
    origin: NearbyCoordinate,
    bars: List<BarPin>,
    selectedBarId: String?,
    focusTarget: BarPin?,
    focusBarId: String?,
    initialCamera: DiscoveryCamera?,
    listCovered: Boolean,
    searchedPlace: MapPlace?,
    focusSearchedPlace: MapPlace?,
    onSearchedPlaceFocusApplied: () -> Unit,
    onFocusApplied: () -> Unit,
    onCameraChanged: (NearbyCoordinate, Int) -> Unit,
    onMapCameraMoving: () -> Unit,
    onMapViewportUnavailable: () -> Unit,
    viewportRetryToken: Int,
    onSelectBar: (String) -> Unit,
    onViewportChanged: (MapViewport) -> Unit,
    recenterToken: Int,
    onMapViewChanged: (MapView?) -> Unit,
    onMapTouch: () -> Unit = {},
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
        var placeLabel by remember { mutableStateOf<Label?>(null) }
        var requestViewportSnapshot by remember { mutableStateOf<(() -> Unit)?>(null) }
        val currentSelect = rememberUpdatedState(onSelectBar)
        val currentMoving = rememberUpdatedState(onMapCameraMoving)
        val currentUnavailable = rememberUpdatedState(onMapViewportUnavailable)
        val currentViewport = rememberUpdatedState(onViewportChanged)
        val currentCameraChanged = rememberUpdatedState(onCameraChanged)
        val currentNativeMap = rememberUpdatedState(nativeMap)
        val currentMapTouch = rememberUpdatedState(onMapTouch)
        val currentCovered = rememberUpdatedState(listCovered)
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

        // Generic geocoder places are never treated as Backend bars. Their pin
        // has no BottleMap barId and cannot navigate to Bar Detail.
        LaunchedEffect(nativeMap, searchedPlace, bars) {
            placeLabel?.remove()
            placeLabel = null
            val map = nativeMap ?: return@LaunchedEffect
            val place = searchedPlace ?: return@LaunchedEffect
            // Avoid drawing a second pin over an existing Backend bar marker.
            if (place.coordinate.isValid() && (place.barId == null ||
                    bars.none { it.barId == place.barId })) {
                placeLabel = map.labelManager?.layer?.addLabel(
                    LabelOptions.from("__searched_location__",
                        LatLng.from(place.coordinate.latitude, place.coordinate.longitude))
                        .setStyles(searchPlaceMarkerStyle())
                        .setClickable(false),
                )
            }
        }
        LaunchedEffect(nativeMap, focusSearchedPlace) {
            val map = nativeMap ?: return@LaunchedEffect
            val place = focusSearchedPlace ?: return@LaunchedEffect
            if (!place.coordinate.isValid()) return@LaunchedEffect
            currentMoving.value()
            map.moveCamera(CameraUpdateFactory.newCenterPosition(
                LatLng.from(place.coordinate.latitude, place.coordinate.longitude)))
            requestViewportSnapshot?.invoke()
            onSearchedPlaceFocusApplied()
        }

        // Selection styling updates without restarting the map or requiring a
        // new nearby HTTP result.
        LaunchedEffect(nativeMap, selectedBarId) {
            if (nativeMap != null) markers.forEach { (id, pair) ->
                pair.second.setStyles(nearbyMarkerStyle(id == selectedBarId))
                pair.second.invalidate()
            }
        }

        // Only deliberate selection requests can focus a bar. Returning from
        // Bar Detail must NOT re-focus the selected pin over the saved viewport.
        LaunchedEffect(focusBarId, focusTarget, nativeMap) {
            val map = nativeMap ?: return@LaunchedEffect
            val target = focusTarget?.takeIf { it.barId == focusBarId }
                ?: return@LaunchedEffect
            currentMoving.value()
            map.moveCamera(CameraUpdateFactory.newCenterPosition(
                LatLng.from(target.location.latitude, target.location.longitude),
            ))
            requestViewportSnapshot?.invoke()
            onFocusApplied()
        }
        LaunchedEffect(recenterToken, nativeMap) {
            val map = nativeMap
            if (recenterToken > 0 && map != null) {
                currentMoving.value()
                map.moveCamera(CameraUpdateFactory.newCenterPosition(
                    LatLng.from(origin.latitude, origin.longitude)))
                requestViewportSnapshot?.invoke()
            }
        }
        LaunchedEffect(viewportRetryToken, nativeMap, listCovered) {
            if (nativeMap != null && !listCovered) {
                requestViewportSnapshot?.invoke()
            }
        }

        Box(modifier = modifier) {
            if (view != null) {
                // Native Kakao MapView handles touch events outside Compose's gesture
                // hierarchy. Observe ACTION_DOWN in the Android View parent without
                // intercepting or consuming the gesture, preserving pan/zoom/markers.
                AndroidView(factory = { context ->
                    MapTouchImeDismissLayout(context) {
                        currentMapTouch.value.invoke()
                    }.apply {
                        addView(view, FrameLayout.LayoutParams(
                            FrameLayout.LayoutParams.MATCH_PARENT,
                            FrameLayout.LayoutParams.MATCH_PARENT))
                    }
                }, modifier = Modifier.fillMaxSize())
                DisposableEffect(view, owner) {
                    onMapViewChanged(view)
                    val disposed = AtomicBoolean(false)
                    val handler = Handler(Looper.getMainLooper())
                    fun post(action: () -> Unit) {
                        handler.post { if (!disposed.get()) action() }
                    }
                    // Every native camera event gets a new generation. A
                    // delayed projection from an older position cannot publish
                    // stale bounds after the user pans/searches/zooms again.
                    var viewportGeneration = 0L
                    fun scheduleViewportSample(map: KakaoMap, firstDelayMs: Long = 140L) {
                        val generation = ++viewportGeneration
                        var previousProjection: Pair<com.zerotoone.bottlemap.data.MapBounds, Int>? = null
                        fun sample(attempt: Int) {
                            if (disposed.get() || generation != viewportGeneration) return
                            // Kakao MapView dimensions and its actual map viewport
                            // can differ (padding/resize/SurfaceView startup).
                            val position = runCatching { map.cameraPosition }.getOrNull()
                            val rect = runCatching { map.viewport }.getOrNull()
                            val pixels = rect?.let {
                                viewportCornerPixels(it.left, it.top, it.right, it.bottom)
                            }
                            val corners = pixels?.mapNotNull { (x, y) ->
                                runCatching { map.fromScreenPoint(x, y) }.getOrNull()?.let {
                                    NearbyCoordinate(it.latitude, it.longitude)
                                }
                            }.orEmpty()
                            val center = position?.position?.let {
                                NearbyCoordinate(it.latitude, it.longitude)
                            }
                            val bounds = mapBoundsFromCorners(corners, center)
                            if (bounds != null && center != null && position != null) {
                                val previous = previousProjection
                                val stable = previous != null &&
                                    previous.second == position.zoomLevel &&
                                    kotlin.math.abs(previous.first.south - bounds.south) < 0.000002 &&
                                    kotlin.math.abs(previous.first.west - bounds.west) < 0.000002 &&
                                    kotlin.math.abs(previous.first.north - bounds.north) < 0.000002 &&
                                    kotlin.math.abs(previous.first.east - bounds.east) < 0.000002
                                if (stable) {
                                    post {
                                        if (generation == viewportGeneration) {
                                            currentCameraChanged.value(center, position.zoomLevel)
                                            currentViewport.value(MapViewport(bounds))
                                        }
                                    }
                                    return
                                }
                                previousProjection = bounds to position.zoomLevel
                            } else {
                                previousProjection = null
                            }
                            if (attempt < 6) {
                                // The camera and its screen projection can briefly
                                // reflect different frames during animation/resize.
                                // Require two consecutive, stable valid samples.
                                val delayMs = if (previousProjection != null) 140L
                                    else 180L + 70L * attempt
                                handler.postDelayed({ sample(attempt + 1) }, delayMs)
                            } else {
                                post {
                                    if (generation == viewportGeneration) {
                                        currentUnavailable.value()
                                    }
                                }
                            }
                        }
                        handler.postDelayed({ sample(0) }, firstDelayMs)
                    }
                    val observer = LifecycleEventObserver { _, event ->
                        when (event) {
                            Lifecycle.Event.ON_RESUME -> {
                                runCatching { view.resume() }
                                if (currentCovered.value) hideNearbyNativeSurface(view)
                                else {
                                    showNearbyNativeSurface(view)
                                    currentNativeMap.value?.let { scheduleViewportSample(it, 220L) }
                                }
                            }
                            Lifecycle.Event.ON_PAUSE -> {
                                ++viewportGeneration
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
                                        map.setOnCameraMoveStartListener(
                                            object : KakaoMap.OnCameraMoveStartListener {
                                                override fun onCameraMoveStart(
                                                    kakaoMap: KakaoMap,
                                                    gestureType: GestureType,
                                                ) {
                                                    post {
                                                        ++viewportGeneration
                                                        currentMoving.value()
                                                    }
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
                                                    // Read the SDK camera + projection *after*
                                                    // the move, rather than using the event's
                                                    // potentially early camera snapshot.
                                                    post { scheduleViewportSample(kakaoMap) }
                                                }
                                            },
                                        )
                                        map.setOnViewportChangeListener(
                                            object : KakaoMap.OnViewportChangeListener {
                                                override fun onViewportChanged(
                                                    kakaoMap: KakaoMap,
                                                    rect: android.graphics.Rect,
                                                ) {
                                                    post { scheduleViewportSample(kakaoMap) }
                                                }
                                            },
                                        )
                                        post {
                                            requestViewportSnapshot = {
                                                scheduleViewportSample(map, 200L)
                                            }
                                            nativeMap = map
                                            status = NearbyMapStatus.Ready
                                            scheduleViewportSample(map, 220L)
                                        }
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
                        ++viewportGeneration
                        requestViewportSnapshot = null
                        val lastPosition = currentNativeMap.value?.cameraPosition
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
                        placeLabel = null
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

private fun searchPlaceMarkerStyle(): LabelStyle {
    val bitmap = Bitmap.createBitmap(42, 42, Bitmap.Config.ARGB_8888)
    Canvas(bitmap).apply {
        drawCircle(21f, 21f, 18f, Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
        })
        drawCircle(21f, 21f, 14f, Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.rgb(121, 78, 201)
        })
        drawCircle(21f, 21f, 5f, Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
        })
    }
    return LabelStyle.from(bitmap).setAnchorPoint(0.5f, 0.5f)
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

