// AI-assisted implementation draft (2026-10-17, I2-P25/A6). Device verification pending.
package com.zerotoone.bottlemap.ui.customer

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.widget.Toast
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.View
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.Alignment
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
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
import com.kakao.vectormap.label.LabelOptions
import com.kakao.vectormap.label.LabelStyle
import com.kakao.vectormap.label.LabelTextBuilder
import com.zerotoone.bottlemap.BuildConfig
import com.zerotoone.bottlemap.ui.common.DelayedLoading
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.delay

internal sealed interface MapRenderStatus {
    data object Loading : MapRenderStatus
    data object Ready : MapRenderStatus
    data class Error(val message: String) : MapRenderStatus
}

/**
 * Uses the already-loaded P24 destination-scoped ViewModel via the NavHost.
 * No additional backend request is made when entering a map for a loaded bar.
 */
@Composable
fun BarLocationMapScreen(
    barId: String,
    detailState: BarDetailUiState,
    onBack: () -> Unit,
    onRetryDetail: () -> Unit,
) {
    // Kakao MapView embeds a native GL Surface. Navigation Compose may keep
    // the outgoing destination composed during its pop animation, leaving that
    // Surface briefly drawn above the Bar Detail destination. Hide it
    // synchronously BEFORE changing the back stack.
    var activeMapView by remember { mutableStateOf<MapView?>(null) }
    var leavingMap by remember { mutableStateOf(false) }
    fun exitMap() {
        if (leavingMap) return
        leavingMap = true
        activeMapView?.let(::hideMapSurface)
        onBack()
    }
    BackHandler(enabled = !leavingMap, onBack = ::exitMap)

    I2CustomerSearchTheme {
        Column(
            modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(onClick = ::exitMap) { Text("←") }
                Text(
                    text = "지도에서 위치 보기",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onBackground,
                )
            }
            // The exiting destination may remain composed during NavHost's
            // transition. Remove its AndroidView from composition immediately.
            if (!leavingMap) when (detailState) {
                BarDetailUiState.Loading -> DelayedLoading {
                    MapStatusMessage("바 정보를 불러오고 있습니다.", loading = true)
                }
                is BarDetailUiState.Error -> MapStatusMessage(
                    message = detailState.message,
                    retry = if (detailState.canRetry) onRetryDetail else null,
                )
                is BarDetailUiState.Success -> BarLocationContent(
                    barId, detailState.bar,
                    onMapViewChanged = { view ->
                        activeMapView = view
                        // A late SDK/map attachment must never revive an
                        // outgoing GL surface after Back was requested.
                        if (leavingMap) view?.let(::hideMapSurface)
                    },
                )
                is BarDetailUiState.Empty -> BarLocationContent(
                    barId, detailState.bar,
                    onMapViewChanged = { view ->
                        activeMapView = view
                        // A late SDK/map attachment must never revive an
                        // outgoing GL surface after Back was requested.
                        if (leavingMap) view?.let(::hideMapSurface)
                    },
                )
            }
        }
    }
}

@Composable
private fun BarLocationContent(
    barId: String,
    bar: BarDetailUiModel,
    onMapViewChanged: (MapView?) -> Unit,
) {
    if (barId != bar.barId) {
        MapStatusMessage("선택한 바의 정보가 일치하지 않습니다.")
        return
    }
    val target = validatedBarLocation(bar)
    if (target == null) {
        MapStatusMessage("이 바의 위치 정보가 없거나 올바르지 않습니다.")
        return
    }
    val context = LocalContext.current
    val addressToCopy = copyableBarAddress(target.address)
    BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
        // The BAR ADDRESS card repeats the address already shown above the map.
        // On short portrait screens, preserve room for the interactive map.
        val compactHeight = maxHeight < 560.dp
        Column(
            modifier = Modifier.fillMaxSize().padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            // Keep long bar names/addresses readable without shrinking the
            // interactive map to zero height on a small portrait device.
            Column(
                modifier = Modifier.fillMaxWidth()
                    .heightIn(max = if (compactHeight) 112.dp else 180.dp)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    text = target.name,
                    color = MaterialTheme.colorScheme.onBackground,
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = target.address,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
            KakaoMapPanel(
                target = target,
                modifier = Modifier.weight(1f).fillMaxWidth(),
                onMapViewChanged = onMapViewChanged,
            )
            // The exact Backend address is copied. Empty addresses are not actionable.
            Surface(
                modifier = Modifier.fillMaxWidth()
                    .padding(bottom = if (compactHeight) 6.dp else 16.dp)
                    .clickable(enabled = addressToCopy != null, role = Role.Button) {
                        val address = addressToCopy ?: return@clickable
                        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE)
                            as ClipboardManager
                        clipboard.setPrimaryClip(
                            ClipData.newPlainText("Bar Address", address))
                        Toast.makeText(context, "주소가 복사되었습니다.", Toast.LENGTH_SHORT).show()
                    },
                color = MaterialTheme.colorScheme.surface,
                shape = RoundedCornerShape(15.dp),
            ) {
                Column(
                    modifier = Modifier.padding(if (compactHeight) 8.dp else 14.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Text(
                            text = target.address,
                            modifier = Modifier.weight(1f),
                            color = MaterialTheme.colorScheme.onSurface,
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        if (addressToCopy != null) {
                            val iconColor = MaterialTheme.colorScheme.primary
                            Canvas(
                                modifier = Modifier.size(24.dp).semantics {
                                    contentDescription = "주소 복사"
                                },
                            ) {
                                val line = 2.dp.toPx()
                                drawRect(
                                    color = iconColor,
                                    topLeft = Offset(size.width * 0.29f, size.height * 0.10f),
                                    size = Size(size.width * 0.57f, size.height * 0.65f),
                                    style = Stroke(line),
                                )
                                drawRect(
                                    color = iconColor,
                                    topLeft = Offset(size.width * 0.13f, size.height * 0.29f),
                                    size = Size(size.width * 0.57f, size.height * 0.61f),
                                    style = Stroke(line),
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun KakaoMapPanel(
    target: BarMapTarget,
    modifier: Modifier,
    onMapViewChanged: (MapView?) -> Unit,
) {
    if (BuildConfig.KAKAO_NATIVE_APP_KEY.isBlank()) {
        MapStatusMessage(
            "Kakao 지도 앱 키가 설정되지 않았습니다. 개발 환경의 Kakao Native App Key를 확인해 주세요.",
        )
        return
    }

    var attempt by rememberSaveable(target.barId) { mutableIntStateOf(0) }
    key(target.barId, target.latitude, target.longitude, attempt) {
        var state by remember { mutableStateOf<MapRenderStatus>(MapRenderStatus.Loading) }

        LaunchedEffect(state) {
            if (state == MapRenderStatus.Loading) {
                delay(25_000)
                if (state == MapRenderStatus.Loading) {
                    state = MapRenderStatus.Error("지도 초기화 시간이 초과되었습니다.")
                }
            }
        }

        Box(modifier = modifier) {
            KakaoMapView(
                target = target,
                modifier = Modifier.fillMaxSize(),
                onStatusChange = { state = it },
                onMapViewChanged = onMapViewChanged,
            )
            when (val current = state) {
                MapRenderStatus.Loading -> DelayedLoading(
                    modifier = Modifier.fillMaxSize(),
                ) {
                    Box(
                        modifier = Modifier.fillMaxSize()
                            .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.9f)),
                        contentAlignment = Alignment.Center,
                    ) { CircularProgressIndicator() }
                }
                MapRenderStatus.Ready -> Unit
                is MapRenderStatus.Error -> Column(
                    modifier = Modifier.fillMaxSize()
                        .background(MaterialTheme.colorScheme.surface)
                        .verticalScroll(rememberScrollState())
                        .padding(18.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(
                        text = current.message,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurface,
                    )
                    Button(onClick = { attempt++ }) { Text("다시 시도") }
                }
            }
        }
    }
}

@Composable
private fun KakaoMapView(
    target: BarMapTarget,
    modifier: Modifier,
    onStatusChange: (MapRenderStatus) -> Unit,
    onMapViewChanged: (MapView?) -> Unit,
) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val owner = LocalLifecycleOwner.current
    val view = remember(target.barId, target.latitude, target.longitude) {
        try {
            MapView(context)
        } catch (error: LinkageError) {
            Log.e("BottleMapKakao", "Native MapView library unavailable", error)
            null
        } catch (error: Exception) {
            Log.e("BottleMapKakao", "MapView creation failed", error)
            null
        }
    }
    if (view == null) {
        LaunchedEffect(target.barId) {
            onStatusChange(MapRenderStatus.Error(
                "이 기기에서 Kakao 지도 엔진을 실행할 수 없습니다. ARM 지원 기기에서 확인해 주세요.",
            ))
        }
        return
    }

    AndroidView(
        factory = { view },
        modifier = modifier.border(
            1.dp,
            MaterialTheme.colorScheme.outlineVariant,
            RoundedCornerShape(16.dp),
        ),
    )

    DisposableEffect(view, owner, target) {
        onMapViewChanged(view)
        val disposed = AtomicBoolean(false)
        val handler = Handler(Looper.getMainLooper())
        fun report(value: MapRenderStatus) {
            handler.post {
                if (!disposed.get()) onStatusChange(value)
            }
        }
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> runCatching {
                    // Returning from the app background: show and resume.
                    showMapSurface(view)
                    view.resume()
                }
                Lifecycle.Event.ON_PAUSE -> runCatching {
                    // Also cover system Back / navigation outside the arrow button.
                    hideMapSurface(view)
                    view.pause()
                }
                else -> Unit
            }
        }
        owner.lifecycle.addObserver(observer)

        try {
            // Compose detaches AndroidView when this destination leaves.
            // Start before selecting manual cleanup, per SDK 2.13.5 lifecycle guidance.
            view.start(
                object : MapLifeCycleCallback() {
                    override fun onMapDestroy() {
                        if (!disposed.get()) {
                            report(MapRenderStatus.Error("지도가 종료되었습니다. 다시 시도해 주세요."))
                        }
                    }
                    override fun onMapError(error: Exception) {
                        Log.e("BottleMapKakao", "Kakao Map error: " + error.javaClass.simpleName, error)
                        report(MapRenderStatus.Error("지도를 불러올 수 없습니다. 연결과 Kakao 앱 키 설정을 확인해 주세요."))
                    }
                },
                object : KakaoMapReadyCallback() {
                    override fun getPosition(): LatLng = LatLng.from(
                        target.latitude, target.longitude,
                    )
                    override fun getZoomLevel(): Int = 16

                    override fun onMapReady(kakaoMap: KakaoMap) {
                        try {
                            // Kakao Label is the native map marker. Its position
                            // uses latitude FIRST and longitude SECOND.
                            val position = LatLng.from(target.latitude, target.longitude)
                            // A typographic "●" shares the text box's layout,
                            // which makes the apparent marker drift off the exact
                            // location when users zoom. Use a real SDK icon label
                            // anchored by its bottom-center tip to this LatLng.
                            val options = LabelOptions.from(target.barId, position)
                                .setStyles(
                                    LabelStyle.from(createBarPinBitmap())
                                        .setAnchorPoint(0.5f, 1.0f)
                                        .setTextStyles(
                                            18,
                                            Color.WHITE,
                                            2,
                                            Color.rgb(12, 22, 38),
                                        ),
                                )
                                .setTexts(LabelTextBuilder().setTexts(target.name))
                            val label = kakaoMap.labelManager?.layer?.addLabel(options)
                            if (label == null) {
                                report(MapRenderStatus.Error("바 위치 마커를 표시할 수 없습니다."))
                            } else {
                                report(MapRenderStatus.Ready)
                            }
                        } catch (error: Exception) {
                            Log.e("BottleMapKakao", "Marker initialization error", error)
                            report(MapRenderStatus.Error("바 위치 마커를 표시할 수 없습니다."))
                        }
                    }
                },
            )
            view.setFinishManually(true)
            if (owner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) {
                view.resume()
            }
        } catch (error: LinkageError) {
            Log.e("BottleMapKakao", "MapView native startup unavailable", error)
            report(MapRenderStatus.Error("이 기기에서 지도 엔진을 사용할 수 없습니다."))
        } catch (error: Exception) {
            Log.e("BottleMapKakao", "MapView startup error", error)
            report(MapRenderStatus.Error("지도를 시작할 수 없습니다."))
        }

        onDispose {
            disposed.set(true)
            onMapViewChanged(null)
            // Native GL surfaces must be hidden before SDK teardown, not only
            // when AndroidView is eventually detached after pop animations.
            hideMapSurface(view)
            owner.lifecycle.removeObserver(observer)
            runCatching { view.pause() }
            runCatching { view.finish() }
        }
    }
}

/**
 * SurfaceView/GLSurfaceView is composited separately from Compose. Changing
 * both levels avoids a leftover map layer above the returning detail screen.
 * These calls must be made on the main thread (BackHandler/Lifecycle observer).
 */
private fun hideMapSurface(view: MapView) {
    view.visibility = View.INVISIBLE
    runCatching { view.surfaceView?.visibility = View.INVISIBLE }
}

private fun showMapSurface(view: MapView) {
    view.visibility = View.VISIBLE
    runCatching { view.surfaceView?.visibility = View.VISIBLE }
}

/**
 * Pixel-precise pin whose point sits at the bottom center of its bitmap.
 * Kakao's LabelStyle anchor (0.5, 1.0) then binds this point to the
 * backend LatLng. The SDK moves the icon geographically while zooming/panning.
 */
private fun createBarPinBitmap(): Bitmap {
    val bitmap = Bitmap.createBitmap(48, 64, Bitmap.Config.ARGB_8888)
    val canvas = Canvas(bitmap)
    val pinShape = Path().apply {
        moveTo(24f, 64f)
        cubicTo(17f, 53f, 5f, 38f, 5f, 24f)
        cubicTo(5f, 13f, 13f, 5f, 24f, 5f)
        cubicTo(35f, 5f, 43f, 13f, 43f, 24f)
        cubicTo(43f, 38f, 31f, 53f, 24f, 64f)
        close()
    }
    val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(214, 183, 126)
        style = Paint.Style.FILL
    }
    canvas.drawPath(pinShape, fill)
    val outline = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(12, 22, 38)
        style = Paint.Style.STROKE
        strokeWidth = 2.5f
    }
    canvas.drawPath(pinShape, outline)
    val hole = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.rgb(12, 22, 38)
        style = Paint.Style.FILL
    }
    canvas.drawCircle(24f, 24f, 8f, hole)
    return bitmap
}

@Composable
private fun MapStatusMessage(
    message: String,
    loading: Boolean = false,
    retry: (() -> Unit)? = null,
) {
    Surface(
        modifier = Modifier.fillMaxWidth().padding(16.dp),
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(16.dp),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (loading) CircularProgressIndicator()
            Text(
                text = message,
                color = MaterialTheme.colorScheme.onSurface,
                style = MaterialTheme.typography.bodyMedium,
            )
            if (retry != null) {
                OutlinedButton(onClick = retry) { Text("다시 시도") }
            }
        }
    }
}
