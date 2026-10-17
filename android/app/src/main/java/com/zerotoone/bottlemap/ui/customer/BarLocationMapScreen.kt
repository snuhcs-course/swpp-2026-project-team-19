// AI-assisted implementation draft (2026-10-17, I2-P25/A6). Device verification pending.
package com.zerotoone.bottlemap.ui.customer

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.os.Handler
import android.os.Looper
import android.util.Log
import androidx.compose.foundation.background
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
import androidx.compose.ui.Alignment
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
    I2CustomerSearchTheme {
        Column(
            modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(onClick = onBack) { Text("←") }
                Text(
                    text = "지도에서 위치 보기",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onBackground,
                )
            }
            when (detailState) {
                BarDetailUiState.Loading -> MapStatusMessage("바 정보를 불러오고 있습니다.", loading = true)
                is BarDetailUiState.Error -> MapStatusMessage(
                    message = detailState.message,
                    retry = if (detailState.canRetry) onRetryDetail else null,
                )
                is BarDetailUiState.Success -> BarLocationContent(barId, detailState.bar)
                is BarDetailUiState.Empty -> BarLocationContent(barId, detailState.bar)
            }
        }
    }
}

@Composable
private fun BarLocationContent(barId: String, bar: BarDetailUiModel) {
    if (barId != bar.barId) {
        MapStatusMessage("선택한 바의 정보가 일치하지 않습니다.")
        return
    }
    val target = validatedBarLocation(bar)
    if (target == null) {
        MapStatusMessage("이 바의 위치 정보가 없거나 올바르지 않습니다.")
        return
    }
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
            )
            Text(
                text = "지도에서 바의 위치를 확인하세요.",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodySmall,
            )
            if (!compactHeight) {
                Surface(
                    modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp),
                    color = MaterialTheme.colorScheme.surface,
                    shape = RoundedCornerShape(15.dp),
                ) {
                    Column(
                        modifier = Modifier.padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        Text(
                            text = "BAR ADDRESS",
                            color = MaterialTheme.colorScheme.primary,
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            text = target.address,
                            color = MaterialTheme.colorScheme.onSurface,
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun KakaoMapPanel(target: BarMapTarget, modifier: Modifier) {
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
            )
            when (val current = state) {
                MapRenderStatus.Loading -> Box(
                    modifier = Modifier.fillMaxSize()
                        .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.9f)),
                    contentAlignment = Alignment.Center,
                ) { CircularProgressIndicator() }
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
        val disposed = AtomicBoolean(false)
        val handler = Handler(Looper.getMainLooper())
        fun report(value: MapRenderStatus) {
            handler.post {
                if (!disposed.get()) onStatusChange(value)
            }
        }
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> runCatching { view.resume() }
                Lifecycle.Event.ON_PAUSE -> runCatching { view.pause() }
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
            owner.lifecycle.removeObserver(observer)
            runCatching { view.pause() }
            runCatching { view.finish() }
        }
    }
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
