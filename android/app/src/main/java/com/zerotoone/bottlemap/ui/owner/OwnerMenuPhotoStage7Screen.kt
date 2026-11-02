package com.zerotoone.bottlemap.ui.owner

import android.net.Uri
import com.zerotoone.bottlemap.BuildConfig
import com.zerotoone.bottlemap.data.owner.MockExtractedLine
import com.zerotoone.bottlemap.data.owner.MockLineKind
import com.zerotoone.bottlemap.data.owner.MockMenuOption
import com.zerotoone.bottlemap.data.owner.MockBrand
import com.zerotoone.bottlemap.data.owner.MockCatalogProduct
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.core.EaseInOutSine
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zerotoone.bottlemap.data.owner.MockImportStatus
import com.zerotoone.bottlemap.data.owner.MockMenuImport
import com.zerotoone.bottlemap.data.owner.MockOwnerLoadState
import com.zerotoone.bottlemap.data.owner.MockPhoto
import com.zerotoone.bottlemap.data.owner.MockPhotoKind
import com.zerotoone.bottlemap.data.owner.MockPhotoExtractionSource
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private fun photoBar(state: MockOwnerLoadState) = when(state) {
    is MockOwnerLoadState.Ready -> state.snapshot
    is MockOwnerLoadState.Empty -> state.snapshot
    else -> null
}

private fun selectedBar(state: MockOwnerLoadState) =
    photoBar(state)?.let { snap ->
        snap.bars.firstOrNull { it.barId == snap.selectedBarId } ?: snap.bars.firstOrNull()
    }

private fun latestImport(state: MockOwnerLoadState): MockMenuImport? {
    val barId = selectedBar(state)?.barId
    return photoBar(state)?.imports?.lastOrNull { it.barId == barId }
}

private fun activeImport(job: MockMenuImport?) = job?.status in listOf(
    MockImportStatus.UPLOADED, MockImportStatus.PROCESSING,
    MockImportStatus.READY_FOR_REVIEW
)

@Composable
private fun MenuPhotoSteps(step: Int, failed: Boolean = false) {
    val labels = listOf("사진 올리기", "읽기", "확인", "더하기")
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        labels.forEachIndexed { i, label ->
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                Box(Modifier.fillMaxWidth().height(2.dp)
                    .background(if (failed && i == step) Color(0xFFFFB4AB) else if (i <= step) V4Color.primary else V4Color.line))
                Text(label, color = if (failed && i == step) Color(0xFFFFB4AB) else if (i <= step) V4Color.primary else V4Color.sub,
                    fontSize = 10.sp, maxLines = 1)
            }
        }
    }
}

@Composable
private fun MenuPhotoPrimary(
    label: String, enabled: Boolean = true, tag: String? = null,
    leadingIcon: (@Composable () -> Unit)? = null, onClick: () -> Unit,
) {
    Button(onClick = onClick, enabled = enabled,
        modifier = Modifier.fillMaxWidth().height(56.dp).then(
            if (tag == null) Modifier else Modifier.testTag(tag)),
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.buttonColors(containerColor = V4Color.primary,
            contentColor = V4Color.background,
            disabledContainerColor = Color(0xFF65513C),
            disabledContentColor = V4Color.sub)) {
        if (leadingIcon != null) { leadingIcon(); Spacer(Modifier.width(8.dp)) }
        Text(label, fontWeight = FontWeight.Bold, fontSize = 15.sp)
    }
}

@Composable
private fun MenuPhotoSecondary(label: String, onClick: () -> Unit) {
    OutlinedButton(onClick = onClick, modifier = Modifier.fillMaxWidth().height(49.dp),
        shape = RoundedCornerShape(8.dp), colors = ButtonDefaults.outlinedButtonColors(
            contentColor = V4Color.text)) {
        Text(label, fontSize = 12.sp)
    }
}

/**
 * Draw the glass-and-liquid illustration from Action-first p82 with native
 * vector primitives; do not ship a bitmap screenshot of the reference.
 */
/** Hand-drawn thin-outline camera from v4 PDF p83, not a platform emoji. */
@Composable private fun MenuPhotoCameraIcon() {
    Canvas(Modifier.size(24.dp).testTag("stage7-retry-camera-icon")) {
        val unit = size.width / 24f
        // Exact action-first v4 icon path: M4 8h3l2-3h6l2 3h3v11H4z.
        val outline = Path().apply {
            moveTo(4f*unit,8f*unit)
            lineTo(7f*unit,8f*unit)
            lineTo(9f*unit,5f*unit)
            lineTo(15f*unit,5f*unit)
            lineTo(17f*unit,8f*unit)
            lineTo(20f*unit,8f*unit)
            lineTo(20f*unit,19f*unit)
            lineTo(4f*unit,19f*unit)
            close()
        }
        val c = Color(0xFF211A14)
        drawPath(outline,c,style=Stroke(width=1.5f*unit,cap=StrokeCap.Round,
            join=StrokeJoin.Round))
        drawCircle(c,radius=3.5f*unit,
            center=Offset(12f*unit,13f*unit),
            style=Stroke(width=1.5f*unit))
    }
}

@Composable
private fun MenuPhotoProcessingIllustration() {
    // ACTION_FIRST v4: the wave moves inside a clipped glass, not the glass itself.
    // Keep the progress motion decorative; it must not imply a completed OCR line.
    val transition = rememberInfiniteTransition(label = "menu-photo-liquid")
    val wave by transition.animateFloat(
        initialValue = 3f, targetValue = -3f,
        animationSpec = infiniteRepeatable(
            animation = tween(1700, easing = EaseInOutSine),
            repeatMode = RepeatMode.Reverse
        ), label = "menu-photo-wave"
    )
    Canvas(Modifier.size(96.dp).testTag("stage7-processing-glass")) {
        val scale = size.width / 48f
        val glassInterior = Path().apply {
            moveTo(11.4f * scale, 13f * scale)
            lineTo(13f * scale, 38.5f * scale)
            quadraticBezierTo(13.2f * scale, 41f * scale, 16f * scale, 41f * scale)
            lineTo(32f * scale, 41f * scale)
            quadraticBezierTo(35f * scale, 41f * scale, 35f * scale, 38.5f * scale)
            lineTo(36.6f * scale, 13f * scale)
            close()
        }
        // A long wave crosses the entire clipped interior at every animation frame.
        // This is the glassFill / whiskey-liquid geometry from the v4 HTML.
        val y = (26f + wave) * scale
        val liquid = Path().apply {
            moveTo(-12f * scale, y)
            quadraticBezierTo(-6f * scale, y - 3f * scale, 0f, y)
            quadraticBezierTo(6f * scale, y + 3f * scale, 12f * scale, y)
            quadraticBezierTo(18f * scale, y - 3f * scale, 24f * scale, y)
            quadraticBezierTo(30f * scale, y + 3f * scale, 36f * scale, y)
            quadraticBezierTo(42f * scale, y - 3f * scale, 48f * scale, y)
            quadraticBezierTo(54f * scale, y + 3f * scale, 60f * scale, y)
            lineTo(60f * scale, 48f * scale)
            lineTo(-12f * scale, 48f * scale)
            close()
        }
        clipPath(glassInterior) { drawPath(liquid, V4Color.primary) }
        val rim = Path().apply {
            moveTo(10f * scale, 11f * scale)
            lineTo(12.8f * scale, 38.2f * scale)
            quadraticBezierTo(13.2f * scale, 41f * scale, 16f * scale, 41f * scale)
            lineTo(32f * scale, 41f * scale)
            quadraticBezierTo(35f * scale, 41f * scale, 35.2f * scale, 38.2f * scale)
            lineTo(38f * scale, 11f * scale)
        }
        drawPath(rim, Color(0xFFC7BBB0), style = Stroke(
            width = 2f * scale, cap = StrokeCap.Round, join = StrokeJoin.Round))
    }
}
@Composable
internal fun OwnerMenuPhotoSelectionScreen(
    state: MockOwnerLoadState,
    viewModel: OwnerMockViewModel,
    onBack: () -> Unit,
    onJob: () -> Unit,
) {
    val context = LocalContext.current
    val store = remember(context) { OwnerMenuPhotoStore(context) }
    val scope = rememberCoroutineScope()
    val bar = selectedBar(state)
    val active = latestImport(state)?.takeIf(::activeImport)
    val failed = latestImport(state)?.takeIf { it.status == MockImportStatus.FAILED }
    // Durable photo IDs are kept in the local repository after submission; this
    // lightweight list survives rotation/process recreation while still editing.
    var entries by rememberSaveable(bar?.barId) {
        mutableStateOf(failed?.images?.map { it.imageId + "|" + it.sourceUri }.orEmpty())
    }
    val photos = entries.mapNotNull {
        val index = it.indexOf('|')
        if (index < 1) null else MockPhoto(
            it.substring(0, index), it.substring(index + 1), MockPhotoKind.MENU_CAPTURE)
    }
    // An interrupted file-copy coroutine must not restore a permanent busy state.
    var busy by remember { mutableStateOf(false) }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    val picker = rememberLauncherForActivityResult(
        ActivityResultContracts.PickMultipleVisualMedia(OWNER_MENU_MAX_PHOTOS)
    ) { uris ->
        if (uris.isNotEmpty() && !busy) {
            busy = true
            scope.launch {
                try {
                    val next = withContext(Dispatchers.IO) { store.add(photos, uris) }
                    entries = next.map { it.photoId + "|" + it.uri }
                    error = null
                } catch (e: Exception) {
                    error = e.message ?: "사진을 읽을 수 없어요. 다시 선택해 주세요."
                } finally { busy = false }
            }
        }
    }
    fun pick() {
        if (!busy && active == null) picker.launch(PickVisualMediaRequest(
            ActivityResultContracts.PickVisualMedia.ImageOnly))
    }
    val valid = photos.isNotEmpty() && photos.size <= OWNER_MENU_MAX_PHOTOS &&
        photos.all(store::isReadable) &&
        validateMenuPhotoSizes(photos.map(store::size)) == null
    Column(Modifier.fillMaxSize().background(V4Color.background)) {
        V4Toolbar(null, onBack)
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState())
            .padding(horizontal = 18.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            MenuPhotoSteps(0)
            if (bar == null) {
                val loadingMessage = when (state) {
                    MockOwnerLoadState.Loading -> "매장 정보를 불러오고 있어요."
                    is MockOwnerLoadState.Error -> state.message
                    else -> "사진을 추가할 매장을 선택해 주세요."
                }
                Text(loadingMessage, color = V4Color.sub, fontSize = 12.sp)
                if (state is MockOwnerLoadState.Error)
                    MenuPhotoSecondary("다시 시도", viewModel::retry)
            }
            Text("메뉴판 사진 선택",
                fontSize = 24.sp, fontWeight = FontWeight.Bold,
                fontFamily = FontFamily.Serif, color = V4Color.text)
            Text("사진을 최대 15장까지 올릴 수 있어요.", fontSize = 12.sp, color = V4Color.sub)
            if (active != null) {
                Text("진행 중인 메뉴판 작업이 있어요. 먼저 기존 작업을 확인해 주세요.",
                    color = V4Color.primary, fontSize = 12.sp)
                MenuPhotoSecondary("기존 작업 확인", onJob)
            }
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                photos.forEachIndexed { index, photo ->
                    Box(Modifier.width(112.dp).height(144.dp).testTag("stage7-photo-${index+1}")
                        .background(Color(0xFFE9DDC9), RoundedCornerShape(7.dp))) {
                        val picture = remember(photo.uri) {
                            runCatching { store.preview(photo)?.asImageBitmap() }.getOrNull()
                        }
                        if (picture != null)
                            Image(picture, "메뉴판 사진 ${index+1}",
                                Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
                        else Text("사진을 읽을 수 없어요", Modifier.align(Alignment.Center),
                            color = V4Color.background, fontSize = 10.sp)
                        Text((index + 1).toString(),
                            Modifier.align(Alignment.BottomStart).padding(5.dp)
                                .background(V4Color.background, RoundedCornerShape(50))
                                .padding(horizontal = 6.dp, vertical = 3.dp),
                            color = V4Color.text, fontSize = 10.sp)
                        Text("×", Modifier.align(Alignment.TopEnd)
                            .padding(4.dp).background(V4Color.background,
                                RoundedCornerShape(50))
                            .ownerQuietClick(enabled = !busy && active == null) {
                                entries = entries.filterIndexed { i, _ -> i != index }
                                // Do not erase a photo held by a prior failed import:
                                // Stage 7 retry can still refer to that same file ID.
                                if (failed?.images?.none { it.imageId == photo.photoId } != false)
                                    store.delete(photo)
                                error = null
                            }.padding(horizontal = 7.dp),
                            color = V4Color.text, fontSize = 15.sp)
                    }
                }
                if (photos.size < OWNER_MENU_MAX_PHOTOS) {
                    Column(Modifier.width(112.dp).height(144.dp)
                        .border(1.dp, V4Color.line, RoundedCornerShape(7.dp))
                        .background(V4Color.surface, RoundedCornerShape(7.dp))
                        .ownerQuietClick(enabled = !busy && active == null, onClick = ::pick)
                        .testTag("stage7-photo-add"),
                        verticalArrangement = Arrangement.Center,
                        horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("+", color = V4Color.primary, fontSize = 28.sp,
                            fontWeight = FontWeight.Light, lineHeight = 28.sp)
                        Text("사진 추가", color = V4Color.sub, fontSize = 13.sp)
                    }
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically) {
                Text("메뉴판 순서대로 올려주세요.", color = V4Color.sub, fontSize = 12.sp)
                Text("${photos.size}/15", color = V4Color.sub, fontSize = 12.sp)
            }
            Column(verticalArrangement = Arrangement.spacedBy(11.dp)) {
                listOf("한 장에 한 면씩, 글자와 가격이 잘리지 않게",
                    "빛 반사 없이 정면에서").forEach { guidance ->
                    Row(verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(11.dp)) {
                        V4StrokeCheck(Modifier.size(16.dp), Color(0xFFB9DFC8))
                        Text(guidance, color = V4Color.sub, fontSize = 13.sp)
                    }
                }
            }
            error?.let { Text(it, color = Color(0xFFFFB4AB), fontSize = 12.sp,
                modifier = Modifier.testTag("stage7-photo-error")) }
            if (photos.isNotEmpty() && !valid && error == null)
                Text("사진이 손상되었거나 접근 권한이 만료됐어요. 다시 선택해 주세요.",
                    color = Color(0xFFFFB4AB), fontSize = 12.sp)
        }
        Box(Modifier.fillMaxWidth().navigationBarsPadding()
            .padding(start = 18.dp, end = 18.dp, top = 12.dp, bottom = 14.dp)) {
            MenuPhotoPrimary(
                if (busy) "사진을 확인하고 있어요" else "사진 ${photos.size}장 올리기",
                enabled = valid && !busy && active == null,
                tag = "stage7-photo-submit") {
                if (bar != null) {
                    busy = true
                    try {
                        viewModel.queuePhotoImport(bar.barId, photos)
                        error = null
                        onJob()
                    } catch (e: Exception) {
                        error = e.message ?: "사진을 제출하지 못했어요."
                    } finally { busy = false }
                }
            }
        }
    }
}

@Composable
internal fun OwnerMenuPhotoJobScreen(
    state: MockOwnerLoadState,
    viewModel: OwnerMockViewModel,
    onHome: () -> Unit,
    onRetryPhotos: () -> Unit,
    onReview: () -> Unit = {},
    fixture: MockPhotoExtractionSource = MockPhotoExtractionSource { emptyList() },
) {
    val job = latestImport(state)
    val active = activeImport(job)
    var cancelConfirmation by rememberSaveable { mutableStateOf(false) }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    // The persisted PROCESSING job is recoverable after leaving the screen.
    // This is a documented Mock-only resolution, NOT a real OCR server call.
    LaunchedEffect(job?.menuImportId, job?.status) {
        if (job != null && job.status in listOf(
                MockImportStatus.UPLOADED, MockImportStatus.PROCESSING)) {
            delay(900)
            runCatching { viewModel.finishPhotoImport(job.menuImportId, fixture) }
                .onFailure { error = it.message }
        }
    }
    // A DEBUG-only long press on the failure heading opens the demonstrator.
    // No developer UI distorts the pixel-perfect PDF failure screen.
    val startMockDemo: () -> Unit = demo@{
        if(!BuildConfig.DEBUG) return@demo
        val failedJob=job ?: return@demo
        if(failedJob.status != MockImportStatus.FAILED) return@demo

                    runCatching {
                        // Clearly labeled DEMO data: never inferred from selected image pixels.
                        val brands = listOf(
                            MockBrand("demo-brand-hakushu", "Suntory"),
                            MockBrand("demo-brand-russells", "Russell's Reserve"),
                            MockBrand("demo-brand-lagavulin", "Lagavulin"),
                            MockBrand("demo-brand-bookers", "Booker's"),
                            MockBrand("demo-brand-jack", "Jack Daniel's")
                        )
                        val products = listOf(
                            MockCatalogProduct("demo-hakushu-dr", "demo-brand-hakushu",
                                "Hakushu Distiller's Reserve"),
                            MockCatalogProduct("demo-russell-single", "demo-brand-russells",
                                "Russell's Reserve Single Barrel"),
                            MockCatalogProduct("demo-russell-rye", "demo-brand-russells",
                                "Russell's Reserve Single Barrel Rye"),
                            MockCatalogProduct("demo-lagavulin-16", "demo-brand-lagavulin",
                                "Lagavulin 16", ageYears = 16),
                            MockCatalogProduct("demo-bookers", "demo-brand-bookers", "Booker's"),
                            MockCatalogProduct("demo-jack-old", "demo-brand-jack", "Jack Daniel's Old No.7"),
                            MockCatalogProduct("demo-jack-proof", "demo-brand-jack", "Jack Daniel's Single Barrel 100 Proof"),
                            MockCatalogProduct("demo-jack-gentleman", "demo-brand-jack", "Jack Daniel's Gentleman Jack")
                        )
                        val existingSnapshot = photoBar(state)
                        brands.filter { b ->
                            existingSnapshot?.brands?.none { it.brandId == b.brandId } != false
                        }.forEach(viewModel::saveBrand)
                        products.filter { product ->
                            existingSnapshot?.products?.none { it.productId == product.productId } != false
                        }.forEach(viewModel::saveProduct)
                        val examples = listOf(
                            MockExtractedLine("demo-hakushu", "하쿠슈DR",
                                MockLineKind.PRODUCT, suggestedProductId = "demo-hakushu-dr",
                                options = listOf(MockMenuOption("demo-hakushu-glass",
                                    label = "잔", pourMl = 30, priceKrw = 19000))),
                            MockExtractedLine("demo-russell", "러셀 싱글배럴",
                                MockLineKind.PRODUCT, candidateProductIds = listOf(
                                    "demo-russell-single", "demo-russell-rye"),
                                options = listOf(MockMenuOption("demo-russell-glass",
                                    label = "잔", pourMl = 30, priceKrw = 15000))),
                            MockExtractedLine("demo-signatory", "시그나토리 쿨일라13",
                                MockLineKind.PRODUCT,
                                options = listOf(MockMenuOption("demo-signatory-glass",
                                    label = "잔", pourMl = 30, priceKrw = 20000))),
                            MockExtractedLine("demo-bookers", "부커스",
                                MockLineKind.PRODUCT, suggestedProductId = "demo-bookers",
                                options = listOf(MockMenuOption("demo-bookers-glass",
                                    label = "잔", pourMl = null, priceKrw = 0))),
                            MockExtractedLine("demo-lagavulin", "라가불린 16년",
                                MockLineKind.PRODUCT, suggestedProductId = "demo-lagavulin-16",
                                options = listOf(MockMenuOption("demo-lagavulin-bottle",
                                    label = "병", priceKrw = 280000)))
                        )
                        val photoUris = failedJob.images.map { it.sourceUri }
                        val demoResult = MockPhotoExtractionSource { uri ->
                            val imageIndex = photoUris.indexOf(uri)
                            if (imageIndex < 0) emptyList() else examples.filterIndexed { i, _ ->
                                i % photoUris.size == imageIndex
                            }
                        }
                        val newImportId = viewModel.retryFailedPhotoImport(failedJob.menuImportId)
                        viewModel.finishPhotoImport(newImportId, demoResult)
                        onReview()
                    }.onFailure { error = it.message }
    }
    if (cancelConfirmation && job != null) {
        AlertDialog(onDismissRequest = { cancelConfirmation = false },
            title = { Text("메뉴 등록 작업을 취소할까요?") },
            text = { Text("현재 게시된 메뉴는 그대로 유지됩니다.") },
            confirmButton = { TextButton(onClick = {
                try { viewModel.cancelPhotoImport(job.menuImportId) }
                catch (e: Exception) { error = e.message }
                cancelConfirmation = false
            }) { Text("작업 취소") } },
            dismissButton = { TextButton(onClick = { cancelConfirmation = false }) {
                Text("돌아가기")
            } })
    }
    Column(Modifier.fillMaxSize().background(V4Color.background)) {
        V4Toolbar(null, onHome)
        Column(Modifier.weight(1f).padding(horizontal = 18.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)) {
            MenuPhotoSteps(1, failed = job?.status == MockImportStatus.FAILED)
            if (job?.status != MockImportStatus.FAILED) Text(if (job?.status == MockImportStatus.READY_FOR_REVIEW) "메뉴 확인 준비"
                else "메뉴판 분석 중",
                color = V4Color.text, fontFamily = FontFamily.Serif,
                fontSize = 24.sp, fontWeight = FontWeight.Bold)
            if (job?.status != MockImportStatus.FAILED) Text(
                if (job?.status == MockImportStatus.PROCESSING ||
                    job?.status == MockImportStatus.UPLOADED) "다른 작업도 할 수 있어요."
                else if (job?.status == MockImportStatus.READY_FOR_REVIEW)
                    "사진별 추출 작업이 준비됐어요. 항목 검수는 다음 단계에서 제공됩니다."
                else "원래 게시된 메뉴는 변경되지 않았어요.",
                color = V4Color.sub, fontSize = 12.sp)
            Spacer(Modifier.weight(1f))
            Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(12.dp)) {
                if (job?.status == MockImportStatus.PROCESSING ||
                    job?.status == MockImportStatus.UPLOADED)
                    MenuPhotoProcessingIllustration()
                else {
                    Box(Modifier.size(64.dp)
                        .background(V4Color.surface, CircleShape),
                        contentAlignment = Alignment.Center) {
                        if (job?.status == MockImportStatus.FAILED) {
                            // v4 p83: outlined exclamation inside the shaded 64dp disk.
                            Canvas(Modifier.size(26.dp).testTag("stage7-failed-icon")) {
                                val accent = Color(0xFFFFB4AB)
                                val cx = size.width / 2f
                                val cy = size.height / 2f
                                drawCircle(accent, radius = size.minDimension * .44f,
                                    style = Stroke(width = 2.dp.toPx()))
                                drawLine(accent,
                                    start = androidx.compose.ui.geometry.Offset(cx, cy - 6.dp.toPx()),
                                    end = androidx.compose.ui.geometry.Offset(cx, cy + 2.dp.toPx()),
                                    strokeWidth = 2.dp.toPx(), cap = StrokeCap.Round)
                                drawCircle(accent, radius = 1.2.dp.toPx(),
                                    center = androidx.compose.ui.geometry.Offset(cx, cy + 6.dp.toPx()))
                            }
                        } else {
                            Text(when(job?.status) {
                                MockImportStatus.READY_FOR_REVIEW -> "✓"
                                MockImportStatus.CANCELED -> "×"
                                else -> "·"
                            }, color = V4Color.primary, fontSize = 30.sp)
                        }
                    }
                }
                if (job?.status !in listOf(MockImportStatus.PROCESSING, MockImportStatus.UPLOADED)) Text(when(job?.status) {
                    MockImportStatus.FAILED -> "메뉴판을 읽지 못했어요"
                    MockImportStatus.READY_FOR_REVIEW -> "메뉴 확인을 준비했어요"
                    MockImportStatus.CANCELED -> "작업이 취소됐어요"
                    MockImportStatus.APPLIED -> "이미 게시된 작업이에요"
                    MockImportStatus.PROCESSING, MockImportStatus.UPLOADED ->
                        "메뉴판을 읽고 있어요"
                    else -> "진행 중인 작업이 없어요"
                }, color = V4Color.text, fontWeight = FontWeight.Bold,
                    fontSize = if (job?.status == MockImportStatus.FAILED) 24.sp else 16.sp,
                    textAlign = TextAlign.Center,
                    modifier = if (BuildConfig.DEBUG && job?.status == MockImportStatus.FAILED)
                        Modifier.pointerInput(job.menuImportId) {
                            detectTapGestures(onLongPress = { startMockDemo() })
                        } else Modifier)
                Text(when(job?.status) {
                    MockImportStatus.FAILED ->
                        "사진 분석을 완료하지 못했어요.\n메뉴판을 화면에 꽉 채우고, 흔들리지 않게 다시 찍어주세요."
                    MockImportStatus.PROCESSING, MockImportStatus.UPLOADED ->
                        "사진 ${job.images.size}장 중 0장을 읽었어요"
                    MockImportStatus.READY_FOR_REVIEW ->
                        "${job.images.size}장의 사진이 작업 ${job.menuImportId}에 연결됐어요."
                    else -> "매장 관리로 돌아갈 수 있어요."
                }, color = if (job?.status in listOf(MockImportStatus.PROCESSING, MockImportStatus.UPLOADED)) V4Color.text else V4Color.sub,
                    fontWeight = if (job?.status in listOf(MockImportStatus.PROCESSING, MockImportStatus.UPLOADED)) FontWeight.Bold else FontWeight.Normal,
                    fontSize = if (job?.status in listOf(MockImportStatus.FAILED, MockImportStatus.PROCESSING, MockImportStatus.UPLOADED)) 16.sp else 14.sp,
                    lineHeight = if (job?.status == MockImportStatus.FAILED) 24.sp else 20.sp,
                    textAlign = TextAlign.Center)
                error?.let { Text(it, color = Color(0xFFFFB4AB), fontSize = 12.sp) }
            }
            Spacer(Modifier.weight(2f))
        }
        Column(Modifier.fillMaxWidth().navigationBarsPadding()
            .padding(horizontal = 18.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (job?.status == MockImportStatus.FAILED)
                MenuPhotoPrimary("사진 다시 올리기", tag = "stage7-failed-retry",
                    leadingIcon = { MenuPhotoCameraIcon() },
                    onClick = onRetryPhotos)
            if (job?.status == MockImportStatus.READY_FOR_REVIEW) {
                MenuPhotoPrimary("검수 결과 확인하기", onClick = onReview)
            }

            // A running mock extraction cannot be canceled from this screen.
            // The READY_FOR_REVIEW cancellation path remains for already-prepared jobs.
            if (job?.status == MockImportStatus.READY_FOR_REVIEW)
                TextButton(onClick = { cancelConfirmation = true },
                    modifier = Modifier.fillMaxWidth()) {
                    Text("메뉴 등록 작업 취소", color = V4Color.sub, fontSize = 12.sp)
                }
            if (job?.status == MockImportStatus.FAILED) {
                TextButton(onClick = onHome, modifier = Modifier.fillMaxWidth().height(48.dp)) {
                    Text("내 매장으로 돌아가기", color = V4Color.sub, fontSize = 14.sp)
                }
            } else MenuPhotoSecondary("내 매장으로 돌아가기", onHome)
        }
    }
}
