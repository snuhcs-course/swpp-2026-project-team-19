package com.zerotoone.bottlemap.ui.owner

import android.net.Uri
import androidx.core.content.FileProvider
import java.io.File
import com.zerotoone.bottlemap.data.owner.MockExtractedLine
import com.zerotoone.bottlemap.data.owner.MockLineKind
import com.zerotoone.bottlemap.data.owner.MockMenuOption
import androidx.activity.compose.BackHandler
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
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.HorizontalDivider
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
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
import androidx.compose.runtime.produceState
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
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zerotoone.bottlemap.data.owner.MockImportStatus
import com.zerotoone.bottlemap.data.owner.importPhotoCount
import com.zerotoone.bottlemap.data.owner.importCompletedPhotoCount
import com.zerotoone.bottlemap.data.owner.MockMenuImport
import com.zerotoone.bottlemap.data.owner.MockOwnerLoadState
import com.zerotoone.bottlemap.data.owner.MockPhoto
import com.zerotoone.bottlemap.data.owner.MockPhotoKind
import com.zerotoone.bottlemap.data.owner.MockPhotoExtractionSource
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.NonCancellable
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference
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

/** Compact line icons for the image-source popup, matching the reference camera/photo composition. */
@Composable private fun MenuPhotoSourceCameraIcon() {
    Canvas(Modifier.size(35.dp)) {
        val u=size.width/32f
        drawRoundRect(V4Color.text,topLeft=Offset(3f*u,3f*u),
            size=androidx.compose.ui.geometry.Size(26f*u,26f*u),
            cornerRadius=androidx.compose.ui.geometry.CornerRadius(4.5f*u),
            style=Stroke(width=2f*u))
        drawCircle(V4Color.text,6f*u,Offset(16f*u,16f*u),
            style=Stroke(width=2f*u))
        drawCircle(V4Color.text,1.7f*u,Offset(24.5f*u,8f*u))
    }
}
@Composable private fun MenuPhotoSourceGalleryIcon() {
    Canvas(Modifier.size(35.dp)) {
        val u=size.width/32f
        val back=Path().apply {
            moveTo(7f*u,12f*u)
            lineTo(5f*u,5f*u)
            lineTo(23f*u,1f*u)
            lineTo(25f*u,10f*u)
        }
        drawPath(back,V4Color.text,style=Stroke(width=2f*u,
            join=StrokeJoin.Round,cap=StrokeCap.Round))
        val frame=Path().apply {
            moveTo(10f*u,12f*u)
            lineTo(29f*u,12f*u)
            lineTo(29f*u,29f*u)
            lineTo(10f*u,29f*u)
            close()
        }
        drawPath(frame,V4Color.text,style=Stroke(width=2f*u,
            join=StrokeJoin.Round,cap=StrokeCap.Round))
        val hills=Path().apply {
            moveTo(12f*u,26f*u)
            lineTo(17f*u,20f*u)
            lineTo(20f*u,23f*u)
            lineTo(23f*u,19f*u)
            lineTo(27f*u,26f*u)
            close()
        }
        drawPath(hills,V4Color.text)
        drawCircle(V4Color.text,1.4f*u,Offset(16f*u,16f*u))
    }
}
@Composable
internal fun MenuPhotoProcessingIllustration(
    diameter: androidx.compose.ui.unit.Dp = 96.dp,
    tag: String = "stage7-processing-glass"
) {
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
    Canvas(Modifier.size(diameter).testTag(tag)) {
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
/** Identical PR96 photo source popup, shared with first registration. */
@Composable internal fun OwnerMenuPhotoSourceDialog(
    onDismiss:()->Unit,onCamera:()->Unit,onGallery:()->Unit
) {
    Dialog(onDismissRequest=onDismiss,
                properties=DialogProperties(usePlatformDefaultWidth=false)) {
                Column(Modifier.fillMaxWidth(0.92f)
                    .background(MaterialTheme.colorScheme.surfaceContainerHigh,
                        RoundedCornerShape(12.dp))
                    .padding(horizontal=15.dp,vertical=14.dp),
                    verticalArrangement=Arrangement.spacedBy(8.dp)) {
                    Text("사진을 어떻게 추가할까요?",
                        style=MaterialTheme.typography.headlineSmall,
                        color=MaterialTheme.colorScheme.onSurface)
                    HorizontalDivider(color=V4Color.line)
                    Row(Modifier.fillMaxWidth().height(97.dp)) {
                        Column(Modifier.weight(1f).fillMaxHeight()
                            .ownerQuietClick {
                                onCamera()
                            }.testTag("stage7-source-camera"),
                            verticalArrangement=Arrangement.Center,
                            horizontalAlignment=Alignment.CenterHorizontally) {
                            MenuPhotoSourceCameraIcon()
                            Spacer(Modifier.height(7.dp))
                            Text("카메라",color=V4Color.primary,fontSize=14.sp)
                        }
                        Column(Modifier.weight(1f).fillMaxHeight()
                            .ownerQuietClick {
                                onGallery()
                            }.testTag("stage7-source-gallery"),
                            verticalArrangement=Arrangement.Center,
                            horizontalAlignment=Alignment.CenterHorizontally) {
                            MenuPhotoSourceGalleryIcon()
                            Spacer(Modifier.height(7.dp))
                            Text("갤러리",color=V4Color.primary,fontSize=14.sp)
                        }
                    }
                }
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
    val storedSnapshot=photoBar(state)
    // First recovered composition knows both SavedState picker entries and all
    // previously imported photo IDs. Prune finalized copies orphaned by a crash.
    LaunchedEffect(store,storedSnapshot != null) {
        storedSnapshot?.let { snapshot ->
            val referenced=photos + snapshot.imports.flatMap { job ->
                job.images.map {image->
                    MockPhoto(image.imageId,image.sourceUri,MockPhotoKind.MENU_CAPTURE)
                }
            }
            withContext(Dispatchers.IO) { store.pruneUnreferencedCopies(referenced) }
        }
    }
    // An interrupted file-copy coroutine must not restore a permanent busy state.
    var busy by remember { mutableStateOf(false) }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    var chooseSource by rememberSaveable { mutableStateOf(false) }
    // TakePicture keeps this path across activity recreation while the camera is open.
    // The app-private temporary JPEG is copied through the SAME validation/store
    // pipeline as Gallery; no CAMERA permission or original-image URL is needed.
    var pendingCapturePath by rememberSaveable { mutableStateOf<String?>(null) }
    var copyingCapturePath by remember { mutableStateOf<String?>(null) }
    // Sweep only this feature's abandoned camera output files. Keep current
    // TakePicture and copy source files until their callbacks finish.
    LaunchedEffect(pendingCapturePath, copyingCapturePath) {
        val protected=setOfNotNull(pendingCapturePath, copyingCapturePath)
        withContext(Dispatchers.IO) {
            synchronized(OwnerMenuCaptureGuard.lock) {
                removeAbandonedOwnerCaptures(
                    File(context.filesDir,"owner-menu-captures"),
                    protected + OwnerMenuCaptureGuard.livePaths)
            }
        }
    }
    fun addImages(sources: List<Uri>, capture: File? = null) {
        if (sources.isEmpty() || busy || active != null) {
            capture?.let { file ->
                synchronized(OwnerMenuCaptureGuard.lock) {
                    file.delete()
                    OwnerMenuCaptureGuard.livePaths.remove(file.absolutePath)
                }
            }
            return
        }
        busy = true
        copyingCapturePath = capture?.absolutePath
        val before=photos
        // withContext(IO) can finish a blocking copy after the composing
        // coroutine was canceled. Coordinate both sides of that handoff.
        val newCopies=AtomicReference<List<MockPhoto>?>(null)
        val cleanupRequested=AtomicBoolean(false)
        scope.launch {
            var saved=false
            try {
                val next = withContext(Dispatchers.IO) {
                    val completed=store.add(before,sources)
                    val added=completed.drop(before.size)
                    newCopies.set(added)
                    if(cleanupRequested.get())added.forEach(store::delete)
                    completed
                }
                entries = next.map { it.photoId + "|" + it.uri }
                saved=true
                error = null
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                error = e.message ?: "사진을 읽을 수 없어요. 다시 선택해 주세요."
            } finally {
                cleanupRequested.set(true)
                withContext(NonCancellable + Dispatchers.IO) {
                    if(!saved)newCopies.get()?.forEach(store::delete)
                    capture?.let { file ->
                        synchronized(OwnerMenuCaptureGuard.lock) {
                            file.delete()
                            OwnerMenuCaptureGuard.livePaths.remove(file.absolutePath)
                        }
                    }
                }
                copyingCapturePath=null
                busy = false
            }
        }
    }
    val picker = rememberLauncherForActivityResult(
        ActivityResultContracts.PickMultipleVisualMedia(OWNER_MENU_MAX_PHOTOS)
    ) { uris -> addImages(uris) }
    val camera = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicture()
    ) { success ->
        val path = pendingCapturePath
        pendingCapturePath = null
        if (path != null) {
            val file = File(path)
            if (success) {
                val uri = runCatching {
                    FileProvider.getUriForFile(context,
                        "${context.packageName}.owner.camera.provider", file)
                }.getOrNull()
                if (uri != null) addImages(listOf(uri),file)
                else {
                    synchronized(OwnerMenuCaptureGuard.lock) {
                        file.delete()
                        OwnerMenuCaptureGuard.livePaths.remove(file.absolutePath)
                    }
                    error = "촬영한 사진을 열 수 없어요. 다시 찍어주세요."
                }
            } else synchronized(OwnerMenuCaptureGuard.lock) {
                file.delete()
                OwnerMenuCaptureGuard.livePaths.remove(file.absolutePath)
            }
        }
    }
    fun takePhoto() {
        if (busy || active != null || photos.size >= OWNER_MENU_MAX_PHOTOS) return
        var newlyCreated: File? = null
        try {
            val directory = File(context.filesDir,"owner-menu-captures").apply { mkdirs() }
            val file = synchronized(OwnerMenuCaptureGuard.lock) {
                File.createTempFile("menu-capture-", ".jpg", directory).also {
                    newlyCreated = it
                    OwnerMenuCaptureGuard.livePaths.add(it.absolutePath)
                }
            }
            val uri = FileProvider.getUriForFile(context,
                "${context.packageName}.owner.camera.provider", file)
            pendingCapturePath = file.absolutePath
            camera.launch(uri)
        } catch (e: Exception) {
            // FileProvider can fail before pendingCapturePath was saved.
            (pendingCapturePath?.let(::File) ?: newlyCreated)?.let { file ->
                synchronized(OwnerMenuCaptureGuard.lock) {
                    file.delete()
                    OwnerMenuCaptureGuard.livePaths.remove(file.absolutePath)
                }
            }
            pendingCapturePath = null
            error = "카메라를 열지 못했어요. 갤러리에서 선택하거나 다시 시도해 주세요."
        }
    }
    fun pick() {
        if (!busy && active == null) chooseSource = true
    }
    fun leavePicker() {
        if(busy)return // Wait for the atomic IO selection to finish.
        val retained=photoBar(state)?.imports.orEmpty().flatMap { job ->
            job.images.map { it.sourceUri }
        }.toSet()
        // Submitted imports (including failed ones) retain their original copies.
        photos.filter {it.uri !in retained}.forEach(store::delete)
        pendingCapturePath?.let { path ->
            synchronized(OwnerMenuCaptureGuard.lock) {
                File(path).delete()
                OwnerMenuCaptureGuard.livePaths.remove(path)
            }
        }
        pendingCapturePath=null
        entries=emptyList()
        onBack()
    }
    BackHandler(enabled=busy || photos.isNotEmpty()) {leavePicker()}
    if(chooseSource) OwnerMenuPhotoSourceDialog(
        onDismiss={chooseSource=false},
        onCamera={chooseSource=false;takePhoto()},
        onGallery={
            chooseSource=false
            picker.launch(PickVisualMediaRequest(
                ActivityResultContracts.PickVisualMedia.ImageOnly))
        }
    )
    val valid = photos.isNotEmpty() && photos.size <= OWNER_MENU_MAX_PHOTOS &&
        photos.all(store::isReadable) &&
        validateMenuPhotoSizes(photos.map(store::size)) == null
    Column(Modifier.fillMaxSize().background(V4Color.background)) {
        V4Toolbar(null, ::leavePicker)
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
                        val picture by produceState<androidx.compose.ui.graphics.ImageBitmap?>(
                            initialValue=null,key1=photo.uri) {
                            value=withContext(Dispatchers.IO) {
                                runCatching {store.preview(photo)?.asImageBitmap()}.getOrNull()
                            }
                        }
                        if (picture != null)
                            Image(requireNotNull(picture), "메뉴판 사진 ${index+1}",
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
                    scope.launch {
                        try {
                            // Wait for server 202 before advancing to the processing screen.
                            viewModel.submitPhotoImportLive(bar.barId, photos)
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
    // A failed repository read is not an OCR extraction failure. Keep Stage 7's
    // existing layout, but do not manufacture a processing job while data loads.
    if(state is MockOwnerLoadState.Loading ||
        state is MockOwnerLoadState.Error || job == null) {
        val loading = state is MockOwnerLoadState.Loading
        val failedToRead = state is MockOwnerLoadState.Error
        Column(Modifier.fillMaxSize().background(V4Color.background)
            .testTag("stage7-job-state")) {
            V4Toolbar(null, onHome)
            Column(Modifier.weight(1f).padding(horizontal = 18.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp)) {
                MenuPhotoSteps(1)
                Text(when {
                    loading -> "메뉴판 작업 불러오는 중"
                    failedToRead -> "메뉴판 작업을 불러오지 못했어요"
                    else -> "진행 중인 메뉴판 작업이 없어요"
                }, color = V4Color.text, fontFamily = FontFamily.Serif,
                    fontSize = 24.sp, fontWeight = FontWeight.Bold)
                Text(when(state) {
                    is MockOwnerLoadState.Error -> state.message
                    MockOwnerLoadState.Loading -> "저장된 메뉴판 작업을 확인하고 있어요."
                    else -> "새 메뉴판 사진을 선택하거나 매장 관리로 돌아가 주세요."
                }, color = V4Color.sub, fontSize = 14.sp)
            }
            Column(Modifier.fillMaxWidth().navigationBarsPadding()
                .padding(horizontal = 18.dp, vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)) {
                when {
                    failedToRead -> MenuPhotoPrimary("다시 시도",
                        tag="stage7-job-repository-retry",onClick=viewModel::retry)
                    !loading -> MenuPhotoPrimary("새 메뉴판 사진 올리기",
                        tag="stage7-job-new-photos",onClick=onRetryPhotos)
                }
                MenuPhotoSecondary("내 매장으로 돌아가기", onHome)
            }
        }
        return
    }
    val active = activeImport(job)
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    // Poll server imports until ready. Only direct Mock tests use extraction fixtures.
    LaunchedEffect(job?.menuImportId, job?.status) {
        if(job != null && job.status in listOf(
                MockImportStatus.UPLOADED, MockImportStatus.PROCESSING)) {
            if(viewModel.usesProductionOwnerApi()) {
                try {
                    var waiting = true
                    var attempts = 0
                    while(waiting && attempts++ < 180) {
                        delay(2_000)
                        val current = viewModel.pollPhotoImportLive(job.menuImportId)
                        waiting = current in listOf(
                            MockImportStatus.UPLOADED, MockImportStatus.PROCESSING)
                    }
                    if(waiting) error="분석 시간이 길어지고 있어요. 나갔다가 다시 확인해 주세요."
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (e: Exception) {
                    error=e.message ?: "메뉴판 분석 상태를 불러오지 못했어요."
                }
            } else {
                delay(900)
                runCatching { viewModel.finishPhotoImport(job.menuImportId, fixture) }
                    .onFailure { error = it.message }
            }
        }
    }
    // READY_FOR_REVIEW goes straight into Stage 8. There is no intermediary
    // "menu ready" or "canceled" user page.
    LaunchedEffect(job?.menuImportId,job?.status) {
        if(job?.status==MockImportStatus.READY_FOR_REVIEW) onReview()
    }
    // Do not draw an intermediary ready/canceled page even for one frame while
    // Navigation handles the transition to the actual review screen.
    if(job?.status==MockImportStatus.READY_FOR_REVIEW ||
       job?.status==MockImportStatus.CANCELED) {
        Box(Modifier.fillMaxSize().background(V4Color.background))
        return
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
                        } else if (job?.status == MockImportStatus.READY_FOR_REVIEW) {
                            V4StrokeCheck(Modifier.size(30.dp),V4Color.primary)
                        } else {
                            Text(if(job?.status==MockImportStatus.CANCELED)"×" else "·",
                                color = V4Color.primary, fontSize = 30.sp)
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
                    textAlign = TextAlign.Center)
                Text(when(job?.status) {
                    MockImportStatus.FAILED ->
                        "사진 분석을 완료하지 못했어요.\n메뉴판을 화면에 꽉 채우고, 흔들리지 않게 다시 찍어주세요."
                    MockImportStatus.PROCESSING, MockImportStatus.UPLOADED ->
                        "사진 ${importPhotoCount(job)}장 중 ${importCompletedPhotoCount(job)}장을 읽었어요"
                    MockImportStatus.READY_FOR_REVIEW ->
                        "${importPhotoCount(job)}장의 사진이 작업 ${job.menuImportId}에 연결됐어요."
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
            if (job?.status == MockImportStatus.FAILED) {
                TextButton(onClick = onHome, modifier = Modifier.fillMaxWidth().height(48.dp)) {
                    Text("내 매장으로 돌아가기", color = V4Color.sub, fontSize = 14.sp)
                }
            } else MenuPhotoSecondary("내 매장으로 돌아가기", onHome)
        }
    }
}
