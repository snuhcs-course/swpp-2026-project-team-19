package com.zerotoone.bottlemap.ui.owner.review

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.zerotoone.bottlemap.ui.common.BmLineIcon
import com.zerotoone.bottlemap.ui.common.BmLineIconId
import com.zerotoone.bottlemap.ui.common.UxColor
import com.zerotoone.bottlemap.ui.common.UxMainButton
import com.zerotoone.bottlemap.ui.common.UxSecondaryButton
import com.zerotoone.bottlemap.ui.common.UxToast
import com.zerotoone.bottlemap.ui.common.quietClick
import com.zerotoone.bottlemap.ui.common.uxText
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private val groupTitles = mapOf(
    ReviewGroup.PENDING to "확인이 필요해요",
    ReviewGroup.READY to "바로 등록할 수 있어요",
    ReviewGroup.OTHER to "그 외 메뉴도 등록돼요",
    ReviewGroup.EXCLUDED to "게시에서 제외했어요",
)

private sealed interface ReviewRow {
    val key: String
    data object AppBar : ReviewRow { override val key = "appbar" }
    data object Head : ReviewRow { override val key = "head" }
    data class Heading(val group: ReviewGroup, val count: Int, val open: Boolean, val bottom: Int, val top: Int) : ReviewRow {
        override val key = "heading-$group"
    }
    data class Card(val itemId: String, val group: ReviewGroup, val bottom: Int) : ReviewRow {
        override val key = "item-$itemId"
    }
    data class AllDone(val bottom: Int) : ReviewRow { override val key = "all-done" }
    data class Empty(val group: ReviewGroup, val bottom: Int) : ReviewRow { override val key = "empty-$group" }
    data object Footer : ReviewRow { override val key = "publish-end" }
}

/**
 * One-page photo-menu review (BottleMap_Minimal_UX_v18.html, flow 02). The bottom tabs are
 * hidden for this flow by the navigation host. [onLeave] returns to the existing
 * menu-management screen ("나중에 하기", back, and after publishing).
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun PhotoReviewScreen(
    vm: PhotoReviewViewModel,
    onLeave: () -> Unit,
    initialFocusItemId: String? = null,
) {
    val load by vm.load.collectAsStateWithLifecycle()
    var toast by remember { mutableStateOf<Pair<Long, String>?>(null) }
    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()
    val reviewNameFocus = remember { mutableStateMapOf<String, FocusRequester>() }
    val detailNameFocus = remember { mutableStateMapOf<String, FocusRequester>() }
    val focus = remember {
        ReviewFocus(
            reviewName = { id -> reviewNameFocus.getOrPut(id) { FocusRequester() } },
            detailName = { id -> detailNameFocus.getOrPut(id) { FocusRequester() } },
        )
    }
    val state = (load as? PhotoReviewLoad.Ready)?.review
    val rows = remember(state) { state?.let(::buildRows).orEmpty() }

    LaunchedEffect(vm) {
        vm.events.collect { event ->
            when (event) {
                is PhotoReviewEvent.Toast -> toast = System.nanoTime() to event.message
                PhotoReviewEvent.Leave -> onLeave()
                PhotoReviewEvent.ScrollToPublish -> listState.animateScrollToItem(
                    (listState.layoutInfo.totalItemsCount - 1).coerceAtLeast(0))
                is PhotoReviewEvent.FocusReviewName -> {
                    delay(50)
                    runCatching { focus.reviewName(event.itemId).requestFocus() }
                }
                is PhotoReviewEvent.FocusDetailName -> {
                    delay(50)
                    runCatching { focus.detailName(event.itemId).requestFocus() }
                }
            }
        }
    }
    LaunchedEffect(toast) {
        if (toast != null) {
            delay(2500)
            toast = null
        }
    }
    // Developer scenarios open scrolled to the card under test, as the prototype does.
    var scrolledToFocus by remember { mutableStateOf(false) }
    LaunchedEffect(rows.isNotEmpty()) {
        if (rows.isEmpty() || scrolledToFocus || initialFocusItemId == null) return@LaunchedEffect
        scrolledToFocus = true
        val index = rows.indexOfFirst { it.key == "item-$initialFocusItemId" }
        if (index >= 0) listState.scrollToItem(index)
    }

    BackHandler {
        if (state?.modal != null) vm.dismissModal() else vm.leave()
    }

    Box(Modifier.fillMaxSize().background(UxColor.bg).testTag("photo-review-screen")) {
        when (val current = load) {
            PhotoReviewLoad.Loading -> Column(Modifier.fillMaxSize()) {
                ReviewAppBar(vm::leave)
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = UxColor.gold)
                }
            }
            is PhotoReviewLoad.Error -> Column(Modifier.fillMaxSize()) {
                ReviewAppBar(vm::leave)
                Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterVertically),
                    horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(current.message, style = uxText(13f, 400, UxColor.sub), textAlign = TextAlign.Center)
                    UxMainButton("다시 시도", vm::reload)
                }
            }
            is PhotoReviewLoad.Ready -> {
                val s = current.review
                val stats = PhotoReviewRules.stats(s)
                LazyColumn(Modifier.fillMaxSize().testTag("photo-review-list"), state = listState) {
                    rows.forEach { row ->
                        when (row) {
                            ReviewRow.AppBar -> item(row.key) { ReviewAppBar(vm::leave) }
                            ReviewRow.Head -> stickyHeader(row.key) { ReviewHead(s, stats, vm) }
                            is ReviewRow.Heading -> item(row.key) {
                                Box(Modifier.padding(start = 20.dp, end = 20.dp, top = row.top.dp, bottom = row.bottom.dp)) {
                                    GroupHeading(row.group, row.count, row.open) { vm.toggleGroup(row.group) }
                                }
                            }
                            is ReviewRow.Card -> item(row.key) {
                                val x = s.items.firstOrNull { it.id == row.itemId }
                                if (x != null) Box(Modifier.padding(start = 20.dp, end = 20.dp, bottom = row.bottom.dp)) {
                                    ReviewCard(s, x, row.group, vm, focus)
                                }
                            }
                            is ReviewRow.AllDone -> item(row.key) {
                                Box(Modifier.padding(start = 20.dp, end = 20.dp, bottom = row.bottom.dp)) {
                                    AllDoneRow { vm.jumpToPublish() }
                                }
                            }
                            is ReviewRow.Empty -> item(row.key) {
                                Text("항목이 없어요.", style = uxText(12f, 400, UxColor.muted),
                                    modifier = Modifier.padding(start = 20.dp, end = 20.dp, bottom = row.bottom.dp)
                                        .padding(horizontal = 12.dp, vertical = 8.dp))
                            }
                            ReviewRow.Footer -> item(row.key) { PublishFooter(stats, vm) }
                        }
                    }
                }
                ReviewModalLayer(s, vm)
            }
        }
        toast?.let { (_, message) ->
            UxToast(message, Modifier.align(Alignment.BottomCenter))
        }
    }
}

private fun buildRows(s: PhotoReviewState): List<ReviewRow> {
    val stats = PhotoReviewRules.stats(s)
    val groups = listOf(
        ReviewGroup.PENDING to stats.pending,
        ReviewGroup.READY to stats.ready,
        ReviewGroup.OTHER to stats.other,
        ReviewGroup.EXCLUDED to stats.excluded,
    )
    val rows = mutableListOf<ReviewRow>(ReviewRow.AppBar, ReviewRow.Head)
    groups.forEachIndexed { gi, (group, items) ->
        // .review-list-group margin-bottom 25; the last one meets the footer's margin-top 26.
        val after = if (gi == groups.lastIndex) 26 else 25
        val top = if (gi == 0) 18 else 0
        val open = s.show[group]
        if (!open) {
            rows += ReviewRow.Heading(group, items.size, false, after, top)
            return@forEachIndexed
        }
        rows += ReviewRow.Heading(group, items.size, true, 0, top)
        when {
            group == ReviewGroup.PENDING && items.isEmpty() -> rows += ReviewRow.AllDone(after)
            items.isEmpty() -> rows += ReviewRow.Empty(group, after)
            else -> items.forEachIndexed { i, x ->
                rows += ReviewRow.Card(x.id, group, if (i == items.lastIndex) after else 7)
            }
        }
    }
    rows += ReviewRow.Footer
    return rows
}

@Composable
private fun ReviewAppBar(onBack: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().height(59.dp).background(UxColor.bg).padding(horizontal = 20.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(9.dp),
    ) {
        Box(
            Modifier.size(48.dp).quietClick(onClick = onBack).semantics { contentDescription = "뒤로" }
                .testTag("review-back"),
            contentAlignment = Alignment.Center,
        ) { BmLineIcon(BmLineIconId.BACK, 19.dp, UxColor.sub) }
        Text("메뉴 검수", style = uxText(17f, 750, letterSpacing = (-0.45).sp))
    }
}

@Composable
private fun ReviewHead(s: PhotoReviewState, stats: ReviewStats, vm: PhotoReviewViewModel) {
    Column(
        Modifier.fillMaxWidth().background(UxColor.bg)
            .drawBehind {
                drawLine(UxColor.line, Offset(0f, size.height - 0.5.dp.toPx()), Offset(size.width, size.height - 0.5.dp.toPx()),
                    1.dp.toPx())
            }
            .padding(start = 20.dp, end = 20.dp, top = 5.dp, bottom = 13.dp),
    ) {
        Row(Modifier.fillMaxWidth().heightIn(min = 39.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween) {
            Text("사진으로 메뉴 추가", style = uxText(17f, 700, letterSpacing = (-0.3).sp))
            Box(Modifier.heightIn(min = 48.dp).quietClick(onClick = vm::leave).padding(8.dp).testTag("review-later"),
                contentAlignment = Alignment.Center) {
                Text("나중에 하기", style = uxText(12f, 750, UxColor.gold))
            }
        }
        if (stats.noDefault) DefaultPourPanel(s, vm)
        Row(Modifier.fillMaxWidth().padding(top = 8.dp, bottom = 7.dp)) {
            listOf("게시 가능" to stats.ready.size + stats.other.size, "확인 필요" to stats.pending.size,
                "게시 제외" to stats.excluded.size).forEachIndexed { i, (label, count) ->
                Column(
                    Modifier.weight(1f).drawBehind {
                        if (i < 2) drawLine(UxColor.line, Offset(size.width - 0.5.dp.toPx(), 0f),
                            Offset(size.width - 0.5.dp.toPx(), size.height), 1.dp.toPx())
                    }.testTag("review-count-$i"),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(2.dp),
                ) {
                    Text(label, style = uxText(10f, 400, UxColor.muted))
                    Text(count.toString(), style = uxText(20f, 750))
                }
            }
        }
    }
}

@Composable
private fun DefaultPourPanel(s: PhotoReviewState, vm: PhotoReviewViewModel) {
    Row(
        Modifier.fillMaxWidth().padding(top = 9.dp, bottom = 11.dp)
            .background(ReviewColor.pourPanelBg, RoundedCornerShape(12.dp))
            .border(1.dp, ReviewColor.pourPanelBorder, RoundedCornerShape(12.dp))
            .padding(horizontal = 13.dp, vertical = 12.dp)
            .testTag("review-default-pour-panel"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("기본 잔 용량", style = uxText(13f, 750), modifier = Modifier.weight(1f))
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(7.dp)) {
            ReviewField(s.draftDefaultPourText, vm::typeDefaultPour,
                Modifier.width(85.dp).testTag("review-default-pour-input"), placeholder = "예: 30", fontSize = 14f,
                minHeight = 44.dp, radius = 9.dp, paddingStart = 10.dp, paddingEnd = 10.dp,
                keyboardType = KeyboardType.Number, onImeAction = { vm.saveDefaultPour(s.draftDefaultPourText) })
            Text("ml", style = uxText(12f, 400, UxColor.sub))
            Box(Modifier.heightIn(min = 44.dp).background(UxColor.gold, RoundedCornerShape(9.dp))
                .quietClick { vm.saveDefaultPour(s.draftDefaultPourText) }
                .padding(horizontal = 14.dp, vertical = 8.dp).testTag("review-default-pour-save"),
                contentAlignment = Alignment.Center) {
                Text("저장", style = uxText(12f, 750, UxColor.goldOn))
            }
        }
    }
}

@Composable
private fun GroupHeading(group: ReviewGroup, count: Int, open: Boolean, onToggle: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 48.dp).quietClick(onClick = onToggle)
            .padding(top = 7.dp, bottom = 12.dp)
            .semantics { contentDescription = "${groupTitles.getValue(group)} $count, ${if (open) "펼쳐짐" else "접힘"}" }
            .testTag("review-group-${group.name.lowercase()}"),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(7.dp),
    ) {
        Box(Modifier.size(width = 30.dp, height = 43.dp), contentAlignment = Alignment.Center) {
            BmLineIcon(if (open) BmLineIconId.DOWN else BmLineIconId.ARROW, 17.dp, UxColor.sub)
        }
        Text(groupTitles.getValue(group), style = uxText(15f, 750))
        Box(Modifier.background(UxColor.elevated, RoundedCornerShape(20.dp)).padding(horizontal = 8.dp, vertical = 1.dp)) {
            Text(count.toString(), style = uxText(11f, 400, UxColor.sub))
        }
    }
}

@Composable
private fun AllDoneRow(onJump: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 55.dp).padding(start = 9.dp, end = 2.dp, top = 4.dp, bottom = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(9.dp),
    ) {
        Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            BmLineIcon(BmLineIconId.CHECK_CIRCLE, 17.dp, UxColor.success)
            Text("모두 확인했어요.", style = uxText(12f, 400, UxColor.sub), maxLines = 1)
        }
        Row(Modifier.heightIn(min = 48.dp).quietClick(onClick = onJump).padding(vertical = 4.dp).testTag("review-jump-publish"),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
            Text("게시하기로 이동", style = uxText(12f, 700, UxColor.gold), maxLines = 1)
            BmLineIcon(BmLineIconId.DOWN, 16.dp, UxColor.gold)
        }
    }
}

@Composable
private fun PublishFooter(stats: ReviewStats, vm: PhotoReviewViewModel) {
    Column(
        Modifier.fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 43.dp)
            .drawBehind { drawLine(UxColor.line, Offset(0f, 0f), Offset(size.width, 0f), 1.dp.toPx()) }
            .padding(top = 18.dp)
            .testTag("review-publish-end"),
    ) {
        Text("게시하기", style = uxText(15f, 700), modifier = Modifier.padding(bottom = 9.dp))
        Text("위스키 ${stats.ready.size} · 그 외 메뉴 ${stats.other.size} · 제외 ${stats.excluded.size}",
            style = uxText(11f, 400, UxColor.muted))
        // CSS margins collapse: micro 9 / publish 18 -> 18; publish 14 / blocker 6 or 9 -> 14.
        val shape = RoundedCornerShape(12.dp)
        BoxWithConstraints(
            Modifier.fillMaxWidth().padding(top = 18.dp, bottom = 14.dp).height(56.dp).clip(shape)
                .background(if (stats.canPublish) UxColor.gold else ReviewColor.publishBg, shape)
                .border(1.dp, if (stats.canPublish) UxColor.gold else ReviewColor.publishBorder, shape)
                .quietClick(enabled = stats.canPublish, onClick = vm::requestPublish)
                .semantics { contentDescription = if (stats.canPublish) "게시하기" else "검수 ${stats.done}/${stats.total} 완료" }
                .testTag("review-publish"),
            contentAlignment = Alignment.Center,
        ) {
            Box(Modifier.align(Alignment.CenterStart).fillMaxHeight()
                .width(maxWidth * (stats.percent / 100f))
                .background(if (stats.canPublish) UxColor.gold else ReviewColor.publishProgress))
            Text(if (stats.canPublish) "게시하기" else "검수 ${stats.done}/${stats.total} 완료",
                style = uxText(15f, 750, if (stats.canPublish) UxColor.goldOn else UxColor.text))
        }
        when {
            stats.noDefault -> Text("매장 기본 잔 용량을 입력해주세요.", style = uxText(12f, 400, UxColor.error, lineHeight = 1.65f),
                modifier = Modifier.padding(horizontal = 1.dp, vertical = 4.dp).testTag("review-publish-blocker"))
            stats.pending.isNotEmpty() -> Text("확인이 필요한 메뉴 ${stats.pending.size}개를 먼저 검수해 주세요.",
                style = uxText(11f, 400, UxColor.muted), modifier = Modifier.testTag("review-publish-blocker"))
        }
    }
}

// ---- Modals ----

@Composable
private fun ReviewModalLayer(s: PhotoReviewState, vm: PhotoReviewViewModel) {
    val modal = s.modal ?: return
    when (modal.type) {
        ReviewModalType.SOURCE_PHOTO -> SourcePhotoModal(s, modal, vm)
        ReviewModalType.PUBLISH -> {
            val stats = PhotoReviewRules.stats(s)
            val summary = PhotoReviewRules.publishSummary(s)
            val lines = buildList {
                add("위스키 ${stats.ready.size} · 그 외 메뉴 ${stats.other.size} · 제외 ${stats.excluded.size}")
                if (summary.changedPrices > 0) add("기존 가격 변경 ${summary.changedPrices}건")
                if (summary.unlinkedNew > 0) add("연결 없이 등록할 메뉴 ${summary.unlinkedNew}건")
                if (summary.merged > 0) add("여러 줄을 합친 위스키 ${summary.merged}건")
                if (summary.operatorChecks > 0) add("게시 후 운영자 확인 ${summary.operatorChecks}건")
            }
            BottomSheetLayer("이대로 게시할까요?", lines.joinToString("\n"), "게시하기", vm::dismissModal, vm::confirmPublish,
                "review-publish-sheet")
        }
        ReviewModalType.EXCLUDE -> BottomSheetLayer("이번 게시에서 제외할까요?", "기존에 등록된 메뉴는 삭제하지 않아요.", "제외",
            vm::dismissModal, { modal.itemId?.let(vm::confirmExclude) }, "review-exclude-sheet")
    }
}

@Composable
private fun BottomSheetLayer(title: String, body: String, confirm: String, onCancel: () -> Unit, onConfirm: () -> Unit, tag: String) {
    Box(Modifier.fillMaxSize().background(ReviewColor.sheetScrim).quietClick(onClick = {}), contentAlignment = Alignment.BottomCenter) {
        Column(
            Modifier.fillMaxWidth().wrapContentHeight()
                .background(UxColor.surface, RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp))
                .border(1.dp, UxColor.outline, RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp))
                .padding(start = 20.dp, end = 20.dp, top = 16.dp, bottom = 30.dp)
                .verticalScroll(rememberScrollState())
                .testTag(tag),
        ) {
            Box(Modifier.align(Alignment.CenterHorizontally).padding(bottom = 19.dp).size(width = 41.dp, height = 4.dp)
                .background(UxColor.outline, RoundedCornerShape(10.dp)))
            Text(title, style = uxText(21f, 700, serif = true), modifier = Modifier.padding(vertical = 10.dp))
            Text(body, style = uxText(13f, 400, UxColor.sub, lineHeight = 1.65f), modifier = Modifier.padding(bottom = 16.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                UxSecondaryButton("취소", onCancel, Modifier.weight(1f).testTag("$tag-cancel"))
                UxMainButton(confirm, onConfirm, Modifier.weight(1f).testTag("$tag-confirm"))
            }
        }
    }
}

@Composable
private fun SourcePhotoModal(s: PhotoReviewState, modal: ReviewModal, vm: PhotoReviewViewModel) {
    val original = s.items.firstOrNull { it.id == modal.itemId } ?: return
    val merged = modal.mergeIndex?.let { original.mergeSources.getOrNull(it) }
    val photo = merged?.photoIndex ?: original.photoIndex
    val hasBox = merged != null || original.hasSourceBox
    val line = if (merged != null) 1 else PhotoReviewRules.photoLine(s, original)
    val raw = merged?.raw ?: original.raw
    BoxWithConstraints(Modifier.fillMaxSize().testTag("review-photo-modal"), contentAlignment = Alignment.Center) {
        val maxDialogHeight = maxHeight - 18.dp - 30.dp
        val photoHeight = (maxHeight * 0.48f).coerceAtMost(310.dp).coerceAtLeast(195.dp)
        Box(Modifier.fillMaxSize().background(ReviewColor.photoBackdrop).quietClick(onClick = vm::dismissModal)
            .testTag("review-photo-backdrop"))
        Column(
            Modifier.padding(15.dp).widthIn(max = 410.dp).fillMaxWidth().heightIn(max = maxDialogHeight)
                .background(UxColor.surface, RoundedCornerShape(17.dp))
                .border(1.dp, UxColor.outline, RoundedCornerShape(17.dp))
                .quietClick(onClick = {})
                .verticalScroll(rememberScrollState())
                .padding(start = 15.dp, end = 15.dp, top = 13.dp, bottom = 16.dp),
        ) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(if (hasBox) "${photo}번째 장 ${line}번째 줄" else "${photo}번째 장", style = uxText(16f, 760),
                    modifier = Modifier.weight(1f))
                Box(Modifier.size(44.dp).quietClick(onClick = vm::dismissModal)
                    .semantics { contentDescription = "닫기" }.testTag("review-photo-close"),
                    contentAlignment = Alignment.Center) {
                    BmLineIcon(BmLineIconId.CLOSE, 22.dp, UxColor.text)
                }
            }
            Spacer(Modifier.height(12.dp))
            SourceVisual(raw, hasBox = false, height = photoHeight, large = true)
            if (!hasBox) Text("사진에서 메뉴 위치를 특정하지 못했어요.", style = uxText(11f, 400, UxColor.sub),
                modifier = Modifier.padding(top = 10.dp))
        }
    }
}
