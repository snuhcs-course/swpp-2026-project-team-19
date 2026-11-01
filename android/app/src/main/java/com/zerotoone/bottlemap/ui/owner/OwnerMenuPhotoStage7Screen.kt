package com.zerotoone.bottlemap.ui.owner

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
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
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
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
private fun MenuPhotoSteps(step: Int) {
    val labels = listOf("사진 올리기", "읽기", "확인", "게시")
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        labels.forEachIndexed { i, label ->
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                Box(Modifier.fillMaxWidth().height(2.dp)
                    .background(if (i <= step) V4Color.primary else V4Color.line))
                Text(label, color = if (i <= step) V4Color.primary else V4Color.sub,
                    fontSize = 10.sp, maxLines = 1)
            }
        }
    }
}

@Composable
private fun MenuPhotoPrimary(
    label: String, enabled: Boolean = true, tag: String? = null, onClick: () -> Unit,
) {
    Button(onClick = onClick, enabled = enabled,
        modifier = Modifier.fillMaxWidth().height(49.dp).then(
            if (tag == null) Modifier else Modifier.testTag(tag)),
        shape = RoundedCornerShape(8.dp),
        colors = ButtonDefaults.buttonColors(containerColor = V4Color.primary,
            contentColor = V4Color.background,
            disabledContainerColor = Color(0xFF65513C),
            disabledContentColor = V4Color.sub)) {
        Text(label, fontWeight = FontWeight.Bold, fontSize = 13.sp)
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
@Composable
private fun MenuPhotoProcessingIllustration() {
    Canvas(Modifier.size(96.dp)) {
        val w = size.width
        val h = size.height
        val fill = Path().apply {
            moveTo(w * .24f, h * .54f)
            quadraticBezierTo(w * .42f, h * .65f, w * .52f, h * .57f)
            quadraticBezierTo(w * .66f, h * .50f, w * .81f, h * .56f)
            lineTo(w * .77f, h * .83f)
            quadraticBezierTo(w * .75f, h * .89f, w * .66f, h * .89f)
            lineTo(w * .39f, h * .89f)
            quadraticBezierTo(w * .29f, h * .88f, w * .28f, h * .81f)
            close()
        }
        drawPath(fill, V4Color.primary)
        val outline = Path().apply {
            moveTo(w * .18f, h * .19f)
            lineTo(w * .26f, h * .83f)
            quadraticBezierTo(w * .27f, h * .91f, w * .38f, h * .91f)
            lineTo(w * .67f, h * .91f)
            quadraticBezierTo(w * .79f, h * .91f, w * .80f, h * .83f)
            lineTo(w * .88f, h * .19f)
        }
        drawPath(outline, Color(0xFFD0C1B5), style = Stroke(
            width = 5.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
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
            Text(if (photos.isEmpty()) "메뉴판 사진을 올려 주세요" else "메뉴판 사진 선택",
                fontSize = 24.sp, fontWeight = FontWeight.Bold,
                fontFamily = FontFamily.Serif, color = V4Color.text)
            Text(if (photos.isEmpty()) "메뉴를 순서대로 최대 15장까지 올릴 수 있어요."
                else "최대 15장", fontSize = 12.sp, color = V4Color.sub)
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
                        Text("▣", color = V4Color.sub, fontSize = 18.sp)
                        Text("사진 추가", color = V4Color.text, fontSize = 12.sp)
                        Text("${photos.size} / 15", color = V4Color.sub, fontSize = 11.sp)
                    }
                }
            }
            Text("새 메뉴만 추가 · 기존 메뉴와 가격 유지",
                color = V4Color.sub, fontSize = 11.sp)
            Text("JPEG/PNG · 사진당 10MB · 전체 60MB",
                color = V4Color.sub, fontSize = 11.sp)
            error?.let { Text(it, color = Color(0xFFFFB4AB), fontSize = 12.sp,
                modifier = Modifier.testTag("stage7-photo-error")) }
            if (photos.isNotEmpty() && !valid && error == null)
                Text("사진이 손상되었거나 접근 권한이 만료됐어요. 다시 선택해 주세요.",
                    color = Color(0xFFFFB4AB), fontSize = 12.sp)
        }
        Box(Modifier.fillMaxWidth().navigationBarsPadding()
            .padding(start = 18.dp, end = 18.dp, top = 12.dp, bottom = 14.dp)) {
            MenuPhotoPrimary(
                if (busy) "사진을 확인하고 있어요" else "사진 ${photos.size}장 분석 시작",
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
            MenuPhotoSteps(1)
            Text(if (job?.status == MockImportStatus.FAILED) "AI 인식 실패"
                else if (job?.status == MockImportStatus.READY_FOR_REVIEW) "메뉴 확인 준비"
                else "메뉴판 분석 중",
                color = V4Color.text, fontFamily = FontFamily.Serif,
                fontSize = 24.sp, fontWeight = FontWeight.Bold)
            Text(
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
                    Box(Modifier.size(74.dp)
                        .background(V4Color.surface, CircleShape),
                        contentAlignment = Alignment.Center) {
                        Text(when(job?.status) {
                            MockImportStatus.FAILED -> "!"
                            MockImportStatus.READY_FOR_REVIEW -> "✓"
                            MockImportStatus.CANCELED -> "×"
                            else -> "·"
                        }, color = if (job?.status == MockImportStatus.FAILED)
                            Color(0xFFFFADA3) else V4Color.primary,
                            fontSize = 34.sp)
                    }
                }
                Text(when(job?.status) {
                    MockImportStatus.FAILED -> "메뉴판을 읽지 못했어요"
                    MockImportStatus.READY_FOR_REVIEW -> "메뉴 확인을 준비했어요"
                    MockImportStatus.CANCELED -> "작업이 취소됐어요"
                    MockImportStatus.APPLIED -> "이미 게시된 작업이에요"
                    MockImportStatus.PROCESSING, MockImportStatus.UPLOADED ->
                        "메뉴판을 읽고 있어요"
                    else -> "진행 중인 작업이 없어요"
                }, color = V4Color.text, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                Text(when(job?.status) {
                    MockImportStatus.FAILED ->
                        "사진 분석을 완료하지 못했어요. 사진을 확인하고 다시 제출해 주세요."
                    MockImportStatus.PROCESSING, MockImportStatus.UPLOADED ->
                        "사진 ${job.images.size}장을 확인하고 있어요. 분석률은 제공되지 않아요."
                    MockImportStatus.READY_FOR_REVIEW ->
                        "${job.images.size}장의 사진이 작업 ${job.menuImportId}에 연결됐어요."
                    else -> "매장 관리로 돌아갈 수 있어요."
                }, color = V4Color.sub, fontSize = 12.sp, textAlign = TextAlign.Center)
                if (job?.status == MockImportStatus.FAILED)
                    Text(job.failureReason.orEmpty(), color = Color(0xFFFFB4AB),
                        fontSize = 11.sp, textAlign = TextAlign.Center)
                error?.let { Text(it, color = Color(0xFFFFB4AB), fontSize = 12.sp) }
            }
            Spacer(Modifier.weight(2f))
        }
        Column(Modifier.fillMaxWidth().navigationBarsPadding()
            .padding(horizontal = 18.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (job?.status == MockImportStatus.FAILED)
                MenuPhotoPrimary("사진 다시 올리기", tag = "stage7-failed-retry",
                    onClick = onRetryPhotos)
            if (active)
                TextButton(onClick = { cancelConfirmation = true },
                    modifier = Modifier.fillMaxWidth()) {
                    Text("메뉴 등록 작업 취소", color = V4Color.sub, fontSize = 12.sp)
                }
            MenuPhotoSecondary("내 매장으로 돌아가기", onHome)
        }
    }
}
