package com.zerotoone.bottlemap.ui.owner

import android.content.Intent
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import com.zerotoone.bottlemap.data.owner.*
import com.zerotoone.bottlemap.ui.common.*
import com.zerotoone.bottlemap.ui.theme.BottleMapSpacing
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private fun selectedOwnerBar(state: MockOwnerLoadState): Pair<MockOwnerSnapshot, MockBar>? {
    val snapshot = when (state) {
        is MockOwnerLoadState.Ready -> state.snapshot
        is MockOwnerLoadState.Empty -> state.snapshot
        else -> return null
    }
    val bar = snapshot.bars.firstOrNull { it.barId == snapshot.selectedBarId }
        ?: snapshot.bars.firstOrNull() ?: return null
    return snapshot to bar
}

/** Render only the contents of a saved URI, keeping the original reference for full-screen display. */
@Composable
internal fun OwnerStoredPhoto(
    uri: String, modifier: Modifier = Modifier, scale: ContentScale = ContentScale.Crop
) {
    val context = LocalContext.current
    val decoded by produceState<ImageBitmap?>(initialValue = null, uri) {
        value = withContext(Dispatchers.IO) {
            try {
                val resolver = context.contentResolver
                val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                resolver.openInputStream(Uri.parse(uri))?.use { BitmapFactory.decodeStream(it, null, bounds) }
                val width = bounds.outWidth.coerceAtLeast(1)
                val height = bounds.outHeight.coerceAtLeast(1)
                var sample = 1
                while (width / sample > 1200 || height / sample > 1200) sample *= 2
                val options = BitmapFactory.Options().apply { inSampleSize = sample }
                resolver.openInputStream(Uri.parse(uri))?.use {
                    BitmapFactory.decodeStream(it, null, options)?.asImageBitmap()
                }
            } catch (_: Exception) {
                null
            }
        }
    }
    Box(modifier.background(MaterialTheme.colorScheme.surfaceVariant),
        contentAlignment = Alignment.Center) {
        if (decoded != null) {
            Image(bitmap = requireNotNull(decoded), contentDescription = "매장 사진",
                modifier = Modifier.fillMaxSize(), contentScale = scale)
        } else {
            Text("사진을 불러올 수 없어요", style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun OwnerDiscardPrompt(visible: Boolean, onDiscard: () -> Unit, onStay: () -> Unit) {
    if (!visible) return
    AlertDialog(
        onDismissRequest = onStay,
        title = { Text("변경을 취소할까요?") },
        text = { Text("저장하지 않은 변경 사항은 반영되지 않아요.") },
        confirmButton = { TextButton(onClick = onDiscard) { Text("저장하지 않고 나가기") } },
        dismissButton = { TextButton(onClick = onStay) { Text("계속 편집") } },
    )
}

@Composable
private fun OwnerEditorUnavailable(state: MockOwnerLoadState, onRetry: () -> Unit) {
    when (state) {
        is MockOwnerLoadState.Error -> {
            Text(state.message, color = MaterialTheme.colorScheme.error)
            OwnerActionButton("다시 시도", onRetry)
        }
        MockOwnerLoadState.Loading -> OwnerLoading("매장 정보 불러오는 중")
        else -> Text("관리할 매장이 없어요.")
    }
}

/**
 * Owner basic-info editor. This only saves basic fields; photo/tag/hour changes made
 * by a child screen are not overwritten by an old copy of the entire bar.
 */
@Composable
fun OwnerBarInfoEditorScreen(
    state: MockOwnerLoadState,
    viewModel: OwnerMockViewModel,
    onBack: () -> Unit,
    onPhotos: () -> Unit,
    onTags: () -> Unit,
    onHours: () -> Unit,
    onStatus: () -> Unit,
) {
    val selected = selectedOwnerBar(state)
    val bar = selected?.second
    var name by rememberSaveable(bar?.barId) { mutableStateOf(bar?.name.orEmpty()) }
    var intro by rememberSaveable(bar?.barId) { mutableStateOf(bar?.description.orEmpty()) }
    var address by rememberSaveable(bar?.barId) { mutableStateOf(bar?.address.orEmpty()) }
    var phone by rememberSaveable(bar?.barId) { mutableStateOf(bar?.phone.orEmpty()) }
    var pour by rememberSaveable(bar?.barId) {
        mutableStateOf(bar?.defaultPourMl?.toString().orEmpty())
    }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    var showDiscard by rememberSaveable { mutableStateOf(false) }
    val dirty = bar != null && (
        name != bar.name || intro != bar.description.orEmpty() ||
        address != bar.address || phone != bar.phone.orEmpty() ||
        pour != bar.defaultPourMl?.toString().orEmpty()
    )
    fun back() {
        if (dirty) showDiscard = true else onBack()
    }
    BackHandler(enabled = dirty) { back() }
    OwnerDiscardPrompt(showDiscard, { showDiscard = false; onBack() }, { showDiscard = false })
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        OwnerHeader("매장 정보 관리", ::back)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(horizontal = BottleMapSpacing.screenHorizontal),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (bar == null) {
                OwnerEditorUnavailable(state, viewModel::retry)
            } else {
                OwnerTextInput("매장명", name, { name = it; error = null },
                    modifier = Modifier.testTag("owner-info-name"))
                OwnerTextInput("한 줄 소개", intro, { intro = it; error = null },
                    singleLine = false)
                OwnerTextInput("주소", address, { address = it; error = null }, singleLine = false)
                OwnerTextInput("매장 전화번호 (없으면 비워두세요)", phone,
                    { phone = it; error = null })
                OwnerTextInput("기본 잔 용량 (ml, 선택)", pour,
                    { pour = it.filter(Char::isDigit).take(4); error = null })
                Text("매장 사진", style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold)
                if (bar.gallery.isEmpty()) {
                    Text("등록된 사진이 없어요.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        bar.gallery.forEachIndexed { index, photo ->
                            Box(Modifier.size(94.dp).clip(RoundedCornerShape(10.dp))) {
                                OwnerStoredPhoto(photo.uri, Modifier.fillMaxSize())
                                if (index == 0) {
                                    Text("대표", modifier = Modifier.align(Alignment.BottomStart)
                                        .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.85f))
                                        .padding(3.dp), style = MaterialTheme.typography.labelSmall)
                                }
                            }
                        }
                    }
                }
                OwnerActionButton("사진 편집", onPhotos, Modifier.fillMaxWidth(), secondary = true)
                OwnerMenuRow("매장 태그", if (bar.tags.isEmpty()) "선택된 태그 없음"
                    else bar.tags.joinToString(" · "), onTags)
                OwnerMenuRow("정규 영업시간",
                    if (bar.weeklyHours.isEmpty()) "아직 설정하지 않았어요."
                    else "설정된 요일 " + bar.weeklyHours.size + "개", onHours)
                OwnerMenuRow("영업 상태 변경", "오늘 휴무 · 영업시간 변경 · 기간 휴업", onStatus)
                val inputError = barInfoError(name, intro, address, phone, pour)
                if (inputError != null) {
                    Text(inputError, style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error)
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                OwnerActionButton("변경 저장", {
                    try {
                        viewModel.saveBar(withBarInfo(bar, name, intro, address, phone, pour))
                        error = null
                        onBack()
                    } catch (e: Exception) {
                        error = e.message ?: "저장하지 못했어요. 다시 시도해 주세요."
                    }
                }, Modifier.fillMaxWidth().testTag("owner-info-save"), enabled = inputError == null)
                OwnerActionButton("취소", ::back, Modifier.fillMaxWidth(), secondary = true)
                Spacer(Modifier.height(20.dp))
            }
        }
    }
}

private const val PHOTO_SEPARATOR = "\u001f"
private fun encodePhoto(photo: MockPhoto): String = photo.photoId + PHOTO_SEPARATOR + photo.uri
private fun decodePhoto(value: String): MockPhoto {
    val parts = value.split(PHOTO_SEPARATOR, limit = 2)
    return MockPhoto(parts[0], parts.getOrElse(1) { "" }, MockPhotoKind.BAR_GALLERY)
}

@Composable
fun OwnerBarPhotoEditorScreen(
    state: MockOwnerLoadState, viewModel: OwnerMockViewModel, onBack: () -> Unit
) {
    val bar = selectedOwnerBar(state)?.second
    var draft by rememberSaveable(bar?.barId) {
        mutableStateOf(bar?.gallery?.map(::encodePhoto).orEmpty())
    }
    val photos = draft.map(::decodePhoto)
    var expandedId by rememberSaveable { mutableStateOf<String?>(null) }
    var deleteId by rememberSaveable { mutableStateOf<String?>(null) }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    var discard by rememberSaveable { mutableStateOf(false) }
    val dirty = bar != null && photos != bar.gallery
    fun back() {
        if (dirty) discard = true else onBack()
    }
    BackHandler(enabled = dirty) { back() }
    OwnerDiscardPrompt(discard, { discard = false; onBack() }, { discard = false })
    val context = LocalContext.current
    val picker = rememberLauncherForActivityResult(
        ActivityResultContracts.PickMultipleVisualMedia(15)
    ) { selectedUris ->
        val existing = photos.map { it.uri }.toSet()
        val added = selectedUris.filter { it.toString() !in existing }.map { uri ->
            try {
                context.contentResolver.takePersistableUriPermission(
                    uri, Intent.FLAG_GRANT_READ_URI_PERMISSION
                )
            } catch (_: SecurityException) {
                // Some picker providers provide a transient URI. Save remains local-only.
            }
            MockPhoto(UUID.randomUUID().toString(), uri.toString(), MockPhotoKind.BAR_GALLERY)
        }
        draft = (photos + added).take(15).map(::encodePhoto)
    }
    if (deleteId != null) {
        AlertDialog(
            onDismissRequest = { deleteId = null },
            title = { Text("사진을 삭제할까요?") },
            text = { Text("저장하면 고객 미리보기에서도 사진이 제거돼요.") },
            confirmButton = {
                TextButton(onClick = {
                    draft = photos.filterNot { it.photoId == deleteId }.map(::encodePhoto)
                    deleteId = null
                }) { Text("삭제") }
            },
            dismissButton = { TextButton(onClick = { deleteId = null }) { Text("취소") } }
        )
    }
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        OwnerHeader("매장 사진 편집", ::back)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(horizontal = BottleMapSpacing.screenHorizontal),
            verticalArrangement = Arrangement.spacedBy(14.dp)) {
            if (bar == null) OwnerEditorUnavailable(state, viewModel::retry) else {
                Text("첫 번째 사진이 고객 화면의 대표 사진이에요.",
                    style = MaterialTheme.typography.bodySmall)
                if (photos.isEmpty()) Text("매장 사진이 없어요. 사진을 추가해 주세요.")
                Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    photos.forEachIndexed { index, photo ->
                        Surface(shape = RoundedCornerShape(12.dp),
                            color = MaterialTheme.colorScheme.surface) {
                            Column(Modifier.width(184.dp).padding(8.dp),
                                verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Box(Modifier.fillMaxWidth().height(146.dp)
                                    .clip(RoundedCornerShape(9.dp))) {
                                    OwnerStoredPhoto(photo.uri,
                                        Modifier.fillMaxSize().clickable { expandedId = photo.photoId })
                                }
                                Text(if (index == 0) "대표 사진" else "사진 " + (index + 1),
                                    style = MaterialTheme.typography.labelLarge)
                                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.SpaceBetween) {
                                    TextButton(
                                        enabled = index > 0,
                                        onClick = { draft = moveBarPhoto(photos, index, -1).map(::encodePhoto) }
                                    ) { Text("←", style = MaterialTheme.typography.titleLarge) }
                                    Box {
                                        TextButton(onClick = { expandedId = photo.photoId }) { Text("⋯") }
                                        DropdownMenu(
                                            expanded = expandedId == photo.photoId,
                                            onDismissRequest = { expandedId = null }
                                        ) {
                                            DropdownMenuItem(text = { Text("대표 사진 등록") },
                                                onClick = {
                                                    draft = makeCoverPhoto(photos, index).map(::encodePhoto)
                                                    expandedId = null
                                                })
                                            DropdownMenuItem(text = { Text("삭제") },
                                                onClick = { expandedId = null; deleteId = photo.photoId })
                                        }
                                    }
                                    TextButton(enabled = index < photos.lastIndex,
                                        onClick = {
                                            draft = moveBarPhoto(photos, index, 1).map(::encodePhoto)
                                        }) { Text("→", style = MaterialTheme.typography.titleLarge) }
                                }
                            }
                        }
                    }
                }
                OwnerActionButton("갤러리에서 사진 추가", {
                    picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                }, Modifier.fillMaxWidth(), enabled = photos.size < 15)
                if (photos.size >= 15) {
                    Text("사진은 최대 15장까지 등록할 수 있어요.",
                        style = MaterialTheme.typography.labelSmall)
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                OwnerActionButton("사진 저장", {
                    try {
                        viewModel.saveBar(bar.copy(gallery = photos))
                        error = null
                        onBack()
                    } catch (e: Exception) {
                        error = e.message ?: "사진을 저장하지 못했어요."
                    }
                }, Modifier.fillMaxWidth().testTag("owner-photo-save"))
                OwnerActionButton("취소", ::back, Modifier.fillMaxWidth(), secondary = true)
            }
        }
    }
}

@Composable
fun OwnerBarTagsEditorScreen(
    state: MockOwnerLoadState, viewModel: OwnerMockViewModel, onBack: () -> Unit
) {
    val selected = selectedOwnerBar(state)
    val bar = selected?.second
    var tags by rememberSaveable(bar?.barId) { mutableStateOf(bar?.tags.orEmpty()) }
    var query by rememberSaveable { mutableStateOf("") }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    var discard by rememberSaveable { mutableStateOf(false) }
    val dirty = bar != null && tags != bar.tags
    fun back() { if (dirty) discard = true else onBack() }
    BackHandler(enabled = dirty) { back() }
    OwnerDiscardPrompt(discard, { discard = false; onBack() }, { discard = false })
    val existing = (selected?.first?.bars.orEmpty().flatMap { it.tags } + tags)
        .distinctBy(String::lowercase)
    val matches = existing.filter { it.contains(query.trim(), ignoreCase = true) }
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        OwnerHeader("매장 태그", ::back)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(horizontal = BottleMapSpacing.screenHorizontal),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (bar == null) OwnerEditorUnavailable(state, viewModel::retry) else {
                Text("최대 5개 선택 · " + tags.size + "/5",
                    style = MaterialTheme.typography.titleSmall)
                OwnerTextInput("태그 검색", query, { query = it.take(24); error = null },
                    modifier = Modifier.testTag("owner-tag-search"))
                if (tags.isNotEmpty()) {
                    Text("선택한 태그", style = MaterialTheme.typography.labelLarge)
                    tags.forEach { tag ->
                        OwnerMenuRow(tag, "선택 취소 · 삭제", onClick = {
                            tags = tags.filterNot { it == tag }; error = null
                        }, trailing = "×")
                    }
                }
                if (matches.isNotEmpty()) {
                    Text("기존 태그", style = MaterialTheme.typography.labelLarge)
                    matches.forEach { tag ->
                        OwnerMenuRow(tag, if (tags.any { it.equals(tag, true) }) "선택됨" else "선택",
                            onClick = {
                                val changed = toggleBarTag(tags, tag)
                                if (changed == null) error = "태그는 최대 5개까지 선택할 수 있어요."
                                else { tags = changed; error = null }
                            }, trailing = if (tags.any { it.equals(tag, true) }) "✓" else "+")
                    }
                } else if (query.isNotBlank()) {
                    Text("검색 결과가 없어요.", style = MaterialTheme.typography.bodySmall)
                }
                if (query.isNotBlank() && existing.none { it.equals(query.trim(), true) }) {
                    OwnerActionButton("새 태그 만들기: " + query.trim(), {
                        val changed = toggleBarTag(tags, query)
                        if (changed == null) error = "태그는 최대 5개, 각 24자까지 등록할 수 있어요."
                        else { tags = changed; query = ""; error = null }
                    }, Modifier.fillMaxWidth(), enabled = tags.size < 5)
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                OwnerActionButton("태그 저장", {
                    try {
                        viewModel.saveBar(bar.copy(tags = tags))
                        error = null
                        onBack()
                    } catch (e: Exception) {
                        error = e.message ?: "태그를 저장하지 못했어요."
                    }
                }, Modifier.fillMaxWidth().testTag("owner-tag-save"))
                OwnerActionButton("취소", ::back, Modifier.fillMaxWidth(), secondary = true)
            }
        }
    }
}

private fun encodeHours(hour: MockWeeklyHours): String =
    listOf(hour.isoDayOfWeek, hour.closed, hour.openMinutes ?: -1,
        hour.closeMinutes ?: -1, hour.closesNextDay).joinToString(",")

private fun decodeHours(raw: String): MockWeeklyHours? = try {
    val pieces = raw.split(",")
    MockWeeklyHours(pieces[0].toInt(), pieces[1].toBoolean(),
        pieces[2].toInt().takeIf { it >= 0 }, pieces[3].toInt().takeIf { it >= 0 },
        pieces[4].toBoolean())
} catch (_: Exception) { null }

private fun formatMinute(value: Int?): String =
    if (value == null) "시간 선택" else "%02d:%02d".format(value / 60, value % 60)

@Composable
fun OwnerBarHoursEditorScreen(
    state: MockOwnerLoadState, viewModel: OwnerMockViewModel, onBack: () -> Unit
) {
    val bar = selectedOwnerBar(state)?.second
    var encoded by rememberSaveable(bar?.barId) {
        mutableStateOf(bar?.weeklyHours?.map(::encodeHours).orEmpty())
    }
    val hours = encoded.mapNotNull(::decodeHours)
    fun updateDay(day: Int, value: MockWeeklyHours?) {
        encoded = (hours.filterNot { it.isoDayOfWeek == day } + listOfNotNull(value))
            .sortedBy { it.isoDayOfWeek }.map(::encodeHours)
    }
    var wheelTarget by rememberSaveable { mutableStateOf("") }
    var copyingDay by rememberSaveable { mutableIntStateOf(0) }
    var copyDays by rememberSaveable { mutableStateOf<List<Int>>(emptyList()) }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    var discard by rememberSaveable { mutableStateOf(false) }
    val dirty = bar != null && hours != bar.weeklyHours
    fun back() { if (dirty) discard = true else onBack() }
    BackHandler(enabled = dirty) { back() }
    OwnerDiscardPrompt(discard, { discard = false; onBack() }, { discard = false })
    val weekdays = listOf("월", "화", "수", "목", "금", "토", "일")
    if (copyingDay != 0) {
        val copySource = hours.firstOrNull { it.isoDayOfWeek == copyingDay }
        AlertDialog(
            onDismissRequest = { copyingDay = 0 },
            title = { Text("다른 요일에 영업시간 복사") },
            text = {
                Column {
                    weekdays.forEachIndexed { index, label ->
                        val day = index + 1
                        if (day != copyingDay) {
                            Row(Modifier.fillMaxWidth().clickable {
                                copyDays = if (day in copyDays) copyDays - day else copyDays + day
                            }, verticalAlignment = Alignment.CenterVertically) {
                                Checkbox(checked = day in copyDays, onCheckedChange = {
                                    copyDays = if (it) copyDays + day else copyDays - day
                                })
                                Text(label + "요일")
                            }
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    if (copySource != null) {
                        val copied = copyDays.map { copySource.copy(isoDayOfWeek = it) }
                        encoded = (hours.filterNot { it.isoDayOfWeek in copyDays } + copied)
                            .sortedBy { it.isoDayOfWeek }.map(::encodeHours)
                    }
                    copyingDay = 0
                    copyDays = emptyList()
                }, enabled = copyDays.isNotEmpty()) { Text("복사") }
            },
            dismissButton = { TextButton(onClick = { copyingDay = 0 }) { Text("취소") } }
        )
    }
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        OwnerHeader("정규 영업시간", ::back)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(horizontal = BottleMapSpacing.screenHorizontal),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (bar == null) OwnerEditorUnavailable(state, viewModel::retry) else {
                Text("미설정 · 정기 휴무 · 영업을 구분해 설정하세요.",
                    style = MaterialTheme.typography.bodySmall)
                weekdays.forEachIndexed { index, label ->
                    val day = index + 1
                    val setting = hours.firstOrNull { it.isoDayOfWeek == day }
                    Surface(color = MaterialTheme.colorScheme.surface,
                        shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(label + "요일", style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.Bold)
                            Row(Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                                listOf("미설정", "휴무", "영업").forEachIndexed { mode, caption ->
                                    val active = when (mode) {
                                        0 -> setting == null
                                        1 -> setting?.closed == true
                                        else -> setting != null && !setting.closed
                                    }
                                    TextButton(
                                        modifier = Modifier.weight(1f),
                                        onClick = {
                                            updateDay(day, when (mode) {
                                                0 -> null
                                                1 -> MockWeeklyHours(day, closed = true)
                                                else -> MockWeeklyHours(day, closed = false,
                                                    openMinutes = 18 * 60, closeMinutes = 23 * 60)
                                            })
                                            error = null
                                        }
                                    ) { Text(caption, color = if (active)
                                        MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant) }
                                }
                            }
                            if (setting != null && !setting.closed) {
                                listOf("open" to "영업 시작", "close" to "영업 종료").forEach { (part, caption) ->
                                    val value = if (part == "open") setting.openMinutes else setting.closeMinutes
                                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                                        horizontalArrangement = Arrangement.SpaceBetween) {
                                        Text(caption)
                                        OutlinedButton(onClick = {
                                            wheelTarget = if (wheelTarget == "$day-$part") "" else "$day-$part"
                                        }) {
                                            Text(formatMinute(value))
                                            Spacer(Modifier.width(6.dp))
                                            OwnerClockIcon()
                                        }
                                    }
                                    if (wheelTarget == "$day-$part") {
                                        val minute = value ?: 18 * 60
                                        key(wheelTarget) {
                                            OwnerQuickTimeWheel(minute / 60, minute % 60) { h, m ->
                                                val newMinute = h * 60 + m
                                                val open = if (part == "open") newMinute else setting.openMinutes
                                                val close = if (part == "close") newMinute else setting.closeMinutes
                                                updateDay(day, setting.copy(
                                                    openMinutes = open, closeMinutes = close,
                                                    closesNextDay = open != null && close != null && close < open
                                                ))
                                                wheelTarget = ""
                                            }
                                        }
                                    }
                                }
                                TextButton(onClick = {
                                    copyingDay = day
                                    copyDays = emptyList()
                                }) { Text("다른 요일에 복사") }
                                if (setting.closesNextDay) {
                                    Text("다음 날 마감", style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.primary)
                                }
                            }
                        }
                    }
                }
                val validation = weeklyHoursError(hours)
                validation?.let {
                    Text(it, color = MaterialTheme.colorScheme.error)
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                OwnerActionButton("영업시간 저장", {
                    try {
                        viewModel.saveBar(withWeeklyHours(bar, hours))
                        error = null
                        onBack()
                    } catch (e: Exception) {
                        error = e.message ?: "영업시간을 저장하지 못했어요."
                    }
                }, Modifier.fillMaxWidth().testTag("owner-hours-save"), enabled = validation == null)
                OwnerActionButton("취소", ::back, Modifier.fillMaxWidth(), secondary = true)
                Spacer(Modifier.height(20.dp))
            }
        }
    }
}

@Composable
fun OwnerBarCustomerPreviewScreen(
    state: MockOwnerLoadState, viewModel: OwnerMockViewModel, onBack: () -> Unit
) {
    val bar = selectedOwnerBar(state)?.second
    var fullPhoto by rememberSaveable { mutableStateOf<String?>(null) }
    if (fullPhoto != null) {
        Dialog(onDismissRequest = { fullPhoto = null }) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Box(Modifier.fillMaxWidth().height(400.dp).clip(RoundedCornerShape(12.dp))) {
                    OwnerStoredPhoto(requireNotNull(fullPhoto), Modifier.fillMaxSize(), ContentScale.Fit)
                }
                TextButton(onClick = { fullPhoto = null }) { Text("닫기") }
            }
        }
    }
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        OwnerHeader("고객 화면 미리보기", onBack)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(horizontal = BottleMapSpacing.screenHorizontal),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (bar == null) OwnerEditorUnavailable(state, viewModel::retry) else {
                if (bar.gallery.isEmpty()) Text("등록된 사진이 없어요.") else {
                    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        bar.gallery.forEach { photo ->
                            Box(Modifier.size(width = 240.dp, height = 180.dp)
                                .clip(RoundedCornerShape(10.dp))
                                .clickable { fullPhoto = photo.uri }) {
                                OwnerStoredPhoto(photo.uri, Modifier.fillMaxSize())
                            }
                        }
                    }
                }
                Text(bar.name, style = MaterialTheme.typography.headlineSmall)
                bar.description?.let { Text(it, style = MaterialTheme.typography.bodyLarge) }
                Text(bar.address)
                bar.phone?.let { Text(it) }
                bar.defaultPourMl?.let { Text("기본 잔 용량 " + it + "ml") }
                if (bar.tags.isNotEmpty()) Text(bar.tags.joinToString("  ·  "))
                val preview = viewModel.preview(bar.barId, System.currentTimeMillis())
                Text("고객에게 표시되는 메뉴 " + (preview?.visibleMenu?.size ?: 0) + "개",
                    style = MaterialTheme.typography.titleSmall)
                val today = ownerToday(System.currentTimeMillis()).dayOfWeek.value
                val regular = bar.weeklyHours.firstOrNull { it.isoDayOfWeek == today }
                val status = homeOperatingException(bar, System.currentTimeMillis())
                Text(status?.let(::homeExceptionHeading) ?: when {
                    regular == null -> "정규 영업시간 미설정"
                    regular.closed -> "정기 휴무"
                    else -> "영업 " + formatMinute(regular.openMinutes) + " ~ " +
                        (if (regular.closesNextDay) "다음 날 " else "") + formatMinute(regular.closeMinutes)
                })
                status?.note?.let { Text("고객 안내: " + it) }
            }
        }
    }
}
