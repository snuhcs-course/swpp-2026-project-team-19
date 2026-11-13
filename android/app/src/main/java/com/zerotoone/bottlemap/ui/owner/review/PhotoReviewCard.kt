package com.zerotoone.bottlemap.ui.owner.review

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.zerotoone.bottlemap.ui.common.BmLineIcon
import com.zerotoone.bottlemap.ui.common.BmLineIconId
import com.zerotoone.bottlemap.ui.common.UxColor
import com.zerotoone.bottlemap.ui.common.quietClick
import com.zerotoone.bottlemap.ui.common.uxText
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewRules.OptionField

/** Focus targets of one card's name editors, created by the screen. */
internal class ReviewFocus(val reviewName: (String) -> FocusRequester, val detailName: (String) -> FocusRequester)

/** One `.review-item` card. [group] is the group the card is drawn in. */
@Composable
internal fun ReviewCard(
    state: PhotoReviewState,
    live: ReviewItem,
    group: ReviewGroup,
    vm: PhotoReviewViewModel,
    focus: ReviewFocus,
) {
    // While a detail field is typed in, the header and issues stay as they were (v18 renders on change).
    val x = state.typingSnapshots[live.id]?.copy(expanded = live.expanded) ?: live
    val issues = PhotoReviewRules.problems(x)
    val showSource = group == ReviewGroup.PENDING && issues.isNotEmpty() && !x.excluded
    val shape = RoundedCornerShape(13.dp)
    Column(
        Modifier.fillMaxWidth().clip(shape)
            .background(UxColor.surface, shape)
            .border(1.dp, if (issues.isNotEmpty()) ReviewColor.pendingBorder else UxColor.line, shape)
            .testTag("review-item-${x.id}"),
    ) {
        if (showSource) {
            Column(Modifier.fillMaxWidth().padding(start = 12.dp, end = 12.dp, top = 9.dp, bottom = 12.dp)) {
                SourceCrop(state, x, vm)
            }
        } else {
            Row(
                Modifier.fillMaxWidth().heightIn(min = 58.dp).padding(start = 5.dp, end = 15.dp, top = 10.dp, bottom = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(5.dp),
            ) {
                Box(
                    Modifier.size(48.dp).quietClick { vm.toggleExpanded(x.id) }
                        .semantics { contentDescription = "${x.name} 상세 ${if (x.expanded) "접기" else "펼치기"}" }
                        .testTag("review-expand-${x.id}"),
                    contentAlignment = Alignment.Center,
                ) {
                    BmLineIcon(if (x.expanded) BmLineIconId.DOWN else BmLineIconId.ARROW, 17.dp, UxColor.sub)
                }
                Column(Modifier.weight(1f)) {
                    Text(x.name.ifBlank { "이름 입력 필요" }, style = uxText(13.5f, 720))
                    PhotoReviewRules.mergedNotice(x)?.let {
                        Text(it, style = uxText(10.5f, 580, ReviewColor.mergeNotice, lineHeight = 1.45f),
                            modifier = Modifier.padding(top = 5.dp))
                    }
                }
                Text(
                    if (x.conflictPrices.isNotEmpty() && x.conflictChoice == null) "-"
                    else won(PhotoReviewRules.itemDisplayPrice(x)),
                    style = uxText(13f, 740, UxColor.gold), maxLines = 1, textAlign = TextAlign.End,
                )
            }
        }
        if (x.excluded) {
            IssueList {
                IssueRow(label = "게시 제외") {
                    ReviewChoice("제외 해제", { vm.unexclude(x.id) }, testTag = "review-unexclude-${x.id}")
                }
            }
        } else if (issues.isNotEmpty()) {
            IssueList { issues.forEach { IssueRowFor(live, it, vm, focus) } }
        }
        if (live.expanded) ReviewDetails(state, live, vm, focus)
    }
}

@Composable
private fun SourceCrop(state: PhotoReviewState, x: ReviewItem, vm: PhotoReviewViewModel) {
    val location = PhotoReviewRules.sourceLocation(state, x)
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(5.dp)) {
        Row(
            Modifier.fillMaxWidth().heightIn(min = 35.dp).padding(horizontal = 1.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(location, style = uxText(11f, 400, UxColor.muted, lineHeight = 1.4f), modifier = Modifier.weight(1f))
            Box(
                Modifier.heightIn(min = 44.dp).quietClick { vm.toggleExpanded(x.id) }
                    .padding(horizontal = 2.dp, vertical = 8.dp)
                    .testTag("review-toggle-${x.id}"),
                contentAlignment = Alignment.Center,
            ) {
                Text(if (x.expanded) "접기" else "펼치기", style = uxText(12f, 750, UxColor.gold))
            }
        }
        SourceVisual(
            raw = x.raw.ifBlank { x.name },
            hasBox = x.hasSourceBox,
            height = if (x.hasSourceBox) 70.dp else 90.dp,
            sourcePhotoUrl = x.sourcePhotoUrl,
            sourceBox = x.sourceBox,
            refreshSourceUrl = { vm.refreshSourcePhotoUrl(x.id) },
            modifier = Modifier.quietClick { vm.openSourcePhoto(x.id) }
                .semantics { contentDescription = "$location 원본 사진 크게 보기" }
                .testTag("review-source-${x.id}"),
        )
        x.mergeSources.forEachIndexed { i, source ->
            Column(Modifier.fillMaxWidth().padding(vertical = 5.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text("${source.photoIndex}번째 장 1번째 줄", style = uxText(11f, 400, UxColor.sub))
                Box(
                    Modifier.fillMaxWidth().heightIn(min = 48.dp)
                        .background(ReviewColor.mergeButtonBg, RoundedCornerShape(8.dp))
                        .border(1.dp, UxColor.outline, RoundedCornerShape(8.dp))
                        .quietClick { vm.openSourcePhoto(x.id, i) }
                        .padding(horizontal = 12.dp, vertical = 10.dp),
                    contentAlignment = Alignment.CenterStart,
                ) {
                    Text(source.raw, style = uxText(11f, 400), maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
        }
        OcrSummary(x)
    }
}

@Composable
private fun OcrSummary(x: ReviewItem) {
    BoxWithConstraints(Modifier.fillMaxWidth().padding(start = 2.dp, end = 2.dp, top = 9.dp, bottom = 2.dp)) {
        val offersMax = maxWidth * 0.56f
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(x.recognizedName.ifBlank { x.name.ifBlank { "이름 미인식" } }, style = uxText(12f, 730))
                PhotoReviewRules.mergedNotice(x)?.let {
                    Text(it, style = uxText(10.5f, 630, ReviewColor.mergeNotice, lineHeight = 1.45f))
                }
            }
            Column(Modifier.widthIn(max = offersMax), horizontalAlignment = Alignment.End,
                verticalArrangement = Arrangement.spacedBy(4.dp)) {
                PhotoReviewRules.recognizedOffers(x).forEach { o ->
                    Row(horizontalArrangement = Arrangement.spacedBy(9.dp), verticalAlignment = Alignment.Bottom) {
                        val volume = PhotoReviewRules.offerVolumeLabel(o)
                        if (volume.isNotEmpty()) Text(volume, style = uxText(11f, 400, UxColor.muted, lineHeight = 1.5f))
                        PhotoReviewRules.offerPriceLabel(x, o)?.let {
                            Text(it, style = uxText(11.5f, 750, lineHeight = 1.5f), maxLines = 1)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun IssueList(content: @Composable () -> Unit) {
    Column(
        Modifier.fillMaxWidth()
            .drawBehind { drawLine(ReviewColor.issueDivider, Offset(0f, 0f), Offset(size.width, 0f), 1.dp.toPx()) }
            .padding(start = 12.dp, end = 12.dp, top = 5.dp, bottom = 12.dp),
        verticalArrangement = Arrangement.spacedBy(7.dp),
    ) { content() }
}

/** `.issue-row` with the label on the left and the controls on the right. */
@Composable
private fun IssueRow(label: String, content: @Composable () -> Unit) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 37.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(label, style = uxText(11f, 680, UxColor.sub), modifier = Modifier.weight(1f).widthIn(min = 70.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
            content()
        }
    }
}

/** Label above a name and two compact buttons (`.menu-confirm-issue`). */
@Composable
private fun MenuConfirmRow(
    label: String,
    name: String,
    first: Pair<String, () -> Unit>,
    second: Pair<String, () -> Unit>,
    tag: String,
) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(9.dp)) {
        Text(label, style = uxText(12f, 680, UxColor.sub, lineHeight = 1.45f))
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(9.dp)) {
            Text(name, style = uxText(12.5f, 700, lineHeight = 1.5f), modifier = Modifier.weight(1f))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                ReviewChoice(first.first, first.second, minHeight = 43.dp, verticalPadding = 9.dp,
                    testTag = "$tag-first")
                ReviewChoice(second.first, second.second, minHeight = 43.dp, verticalPadding = 9.dp,
                    testTag = "$tag-second")
            }
        }
    }
}

@Composable
private fun NameEditorRow(label: String, x: ReviewItem, vm: PhotoReviewViewModel, focus: ReviewFocus) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(label, style = uxText(12f, 680, UxColor.sub, lineHeight = 1.45f))
        val value = x.reviewNameDraft ?: if (x.match == ReviewMatch.NEW) x.newProductName ?: x.name else x.name
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            ReviewField(
                value = value,
                onValueChange = { vm.typeReviewName(x.id, it) },
                modifier = Modifier.weight(1f).testTag("review-name-input-${x.id}"),
                minHeight = 49.dp,
                paddingStart = 13.dp,
                paddingEnd = 42.dp,
                onImeAction = { vm.saveReviewName(x.id) },
                focusRequester = focus.reviewName(x.id),
                trailing = { focused ->
                    Box(
                        Modifier.padding(4.dp).size(width = 40.dp, height = 41.dp)
                            .alpha(if (focused) 1f else 0f)
                            .then(if (focused) Modifier.quietClick { vm.clearReviewName(x.id) } else Modifier)
                            .semantics { contentDescription = "메뉴 이름 모두 지우기" },
                        contentAlignment = Alignment.Center,
                    ) { BmLineIcon(BmLineIconId.CLOSE, 15.dp, UxColor.sub) }
                },
            )
            Box(
                Modifier.widthIn(min = 60.dp).heightIn(min = 48.dp)
                    .background(UxColor.gold, RoundedCornerShape(9.dp))
                    .quietClick { vm.saveReviewName(x.id) }
                    .padding(horizontal = 12.dp, vertical = 8.dp)
                    .testTag("review-name-save-${x.id}"),
                contentAlignment = Alignment.Center,
            ) { Text("저장", style = uxText(11f, 750, UxColor.goldOn)) }
        }
    }
}

/** `.selection-head`: label with a separate "확인" that is enabled only after a choice. */
@Composable
private fun SelectionHead(title: String, enabled: Boolean, onConfirm: () -> Unit, tag: String) {
    Row(Modifier.fillMaxWidth().heightIn(min = 44.dp), verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(title, style = uxText(12f, 680, UxColor.sub), modifier = Modifier.weight(1f))
        val shape = RoundedCornerShape(9.dp)
        Box(
            Modifier.widthIn(min = 75.dp).heightIn(min = 43.dp)
                .alpha(if (enabled) 1f else 0.68f)
                .background(if (enabled) UxColor.gold else UxColor.elevated, shape)
                .border(1.dp, if (enabled) UxColor.gold else UxColor.line, shape)
                .quietClick(enabled = enabled, onClick = onConfirm)
                .padding(horizontal = 14.dp, vertical = 8.dp)
                .testTag(tag),
            contentAlignment = Alignment.Center,
        ) { Text("확인", style = uxText(12f, 760, if (enabled) UxColor.goldOn else UxColor.muted)) }
    }
}

/** `.candidate-secondary-actions`: full-width text rows with a chevron. */
@Composable
private fun SecondaryActions(actions: List<Pair<String, () -> Unit>>) {
    Column(
        Modifier.fillMaxWidth().padding(top = 4.dp)
            .drawBehind { drawLine(UxColor.line, Offset(0f, 0f), Offset(size.width, 0f), 1.dp.toPx()) },
    ) {
        actions.forEach { (label, action) ->
            Row(
                Modifier.fillMaxWidth().heightIn(min = 46.dp)
                    .drawBehind {
                        drawLine(UxColor.line, Offset(0f, size.height - 0.5.dp.toPx()),
                            Offset(size.width, size.height - 0.5.dp.toPx()), 1.dp.toPx())
                    }
                    .quietClick(onClick = action)
                    .padding(horizontal = 5.dp, vertical = 9.dp)
                    .testTag("review-secondary-$label"),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(label, style = uxText(12f, 730, UxColor.gold))
                BmLineIcon(BmLineIconId.ARROW, 14.dp, UxColor.gold)
            }
        }
    }
}

@Composable
private fun SelectableRow(text: String, selected: Boolean, onClick: () -> Unit, minHeight: Int, fontSize: Float,
    radius: Int, padV: Int, tag: String, weight: Int = 700) {
    val shape = RoundedCornerShape(radius.dp)
    Box(
        Modifier.fillMaxWidth().heightIn(min = minHeight.dp)
            .background(if (selected) ReviewColor.selectedBg else UxColor.elevated, shape)
            .border(if (selected) 2.dp else 1.dp, if (selected) UxColor.gold else
                if (fontSize >= 13f) UxColor.outline else UxColor.line, shape)
            .quietClick(onClick = onClick)
            .padding(horizontal = if (fontSize >= 13f) 15.dp else 13.dp, vertical = padV.dp)
            .semantics { contentDescription = text + if (selected) ", 선택됨" else "" }
            .testTag(tag),
        contentAlignment = Alignment.CenterStart,
    ) {
        Text(text, style = uxText(fontSize, weight, if (selected) ReviewColor.selectedText else UxColor.text))
    }
}

@Composable
private fun IssueRowFor(x: ReviewItem, issue: ReviewIssue, vm: PhotoReviewViewModel, focus: ReviewFocus) {
    val id = x.id
    when (issue) {
        ReviewIssue.DETAIL_NAME -> IssueRow("메뉴 이름 수정 중") {
            Text("세부사항에서 저장을 눌러 주세요.", style = uxText(11f, 400, UxColor.gold, lineHeight = 1.6f))
        }
        ReviewIssue.MATCH -> MenuConfirmRow(
            "메뉴를 확인해 주세요", x.candidates.firstOrNull()?.name ?: "추천 상품 없음",
            "맞아요" to { vm.confirmMatch(id) }, "아니에요" to { vm.startCatalogSearch(id) }, "review-match-$id",
        )
        ReviewIssue.NAME -> if (x.nameEditMode) NameEditorRow("메뉴 이름을 수정해 주세요", x, vm, focus)
        else MenuConfirmRow("메뉴를 확인해 주세요", x.name.ifBlank { "이름 입력 필요" },
            "맞아요" to { vm.confirmName(id) }, "아니에요" to { vm.editReviewName(id) }, "review-name-$id")
        ReviewIssue.NEW -> if (x.nameEditMode) NameEditorRow("새로운 메뉴예요", x, vm, focus)
        else MenuConfirmRow("새로운 메뉴예요", (x.newProductName ?: x.name).ifBlank { "이름 입력 필요" },
            "확인" to { vm.confirmNew(id) }, "수정" to { vm.editReviewName(id) }, "review-new-$id")
        ReviewIssue.CANDIDATE -> Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(9.dp)) {
            SelectionHead("위스키를 선택해 주세요", x.selectedCandidateId != null,
                { vm.confirmSelectedCandidate(id) }, "review-candidate-confirm-$id")
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
                    x.candidates.forEach { c ->
                        SelectableRow(c.name, x.selectedCandidateId == c.productId, { vm.chooseCandidate(id, c.productId) },
                            48, 13f, 9, 12, "review-candidate-$id-${c.productId}")
                    }
                }
                SecondaryActions(listOf("다른 위스키 검색" to { vm.startCatalogSearch(id) },
                    "찾는 위스키가 없어요" to { vm.registerAsNew(id) }))
            }
        }
        ReviewIssue.CATALOG_SEARCH -> Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(9.dp)) {
            val canConfirm = x.selectedSearchId != null && x.searchResults?.any { it.productId == x.selectedSearchId } == true
            SelectionHead("위스키를 검색해 주세요", canConfirm, { vm.confirmSelectedSearch(id) }, "review-search-confirm-$id")
            CatalogSearch(x, vm)
        }
        ReviewIssue.PRICE_CHOICE -> Row(Modifier.fillMaxWidth().heightIn(min = 37.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("가격을 선택해 주세요", style = uxText(10.5f, 680, UxColor.sub), maxLines = 1,
                modifier = Modifier.width(106.dp).padding(top = 23.dp))
            Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(PriceChoice.OLD to x.oldPrice, PriceChoice.PHOTO to x.photoPrice).forEach { (choice, price) ->
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        if (choice == PriceChoice.PHOTO) {
                            Box(Modifier.align(Alignment.CenterHorizontally).height(20.dp)
                                .background(UxColor.gold, RoundedCornerShape(7.dp)).padding(horizontal = 9.dp),
                                contentAlignment = Alignment.Center) {
                                Text("New", style = uxText(10f, 800, UxColor.goldOn, lineHeight = 1f))
                            }
                        } else Spacer(Modifier.height(20.dp))
                        ReviewChoice(won(price), { vm.choosePrice(id, choice) }, Modifier.fillMaxWidth(),
                            selected = x.priceChoice == choice, minHeight = 50.dp, horizontalPadding = 5.dp,
                            verticalPadding = 8.dp, testTag = "review-price-${choice.name.lowercase()}-$id")
                    }
                }
            }
        }
        ReviewIssue.PHOTO_CONFLICT -> IssueRow("가격을 선택해 주세요.") {
            x.conflictPrices.forEach { p ->
                ReviewChoice(won(p), { vm.chooseConflictPrice(id, p) }, selected = x.conflictChoice == p,
                    testTag = "review-conflict-$id-${p.toLong()}")
            }
        }
        ReviewIssue.PRICE -> IssueRow("가격을 입력해 주세요") {
            ReviewField(x.draftPriceText, { vm.typeInlinePrice(id, it) },
                Modifier.widthIn(min = 80.dp, max = 126.dp).testTag("review-price-input-$id"),
                placeholder = "예: 15,000", fontSize = 12f, minHeight = 39.dp, radius = 9.dp,
                paddingStart = 9.dp, paddingEnd = 9.dp, keyboardType = KeyboardType.Number,
                onImeAction = { vm.commitInlinePrice(id) })
            SaveButton({ vm.commitInlinePrice(id) }, "review-price-save-$id")
        }
        ReviewIssue.VOLUME -> IssueRow("용량을 입력해 주세요") {
            ReviewField(x.draftVolumeText, { vm.typeInlineVolume(id, it) },
                Modifier.widthIn(min = 80.dp, max = 126.dp).testTag("review-volume-input-$id"),
                placeholder = "ml", fontSize = 12f, minHeight = 39.dp, radius = 9.dp,
                paddingStart = 9.dp, paddingEnd = 9.dp, keyboardType = KeyboardType.Decimal,
                onImeAction = { vm.commitInlineVolume(id) })
            SaveButton({ vm.commitInlineVolume(id) }, "review-volume-save-$id")
        }
        ReviewIssue.OPTION -> IssueRow(
            if (PhotoReviewRules.countOptions(x) > PhotoReviewRules.MAX_OPTIONS)
                "옵션은 최대 3개까지만 게시할 수 있어요. 남길 옵션 3개를 선택해 주세요."
            else "용량 옵션을 확인해 주세요"
        ) {
            ReviewChoice("옵션 수정", { vm.toggleExpanded(id) }, testTag = "review-option-edit-$id")
        }
    }
}

@Composable
private fun SaveButton(onClick: () -> Unit, tag: String) {
    Box(
        Modifier.heightIn(min = 48.dp).background(UxColor.gold, RoundedCornerShape(9.dp))
            .quietClick(onClick = onClick).padding(horizontal = 11.dp, vertical = 8.dp).testTag(tag),
        contentAlignment = Alignment.Center,
    ) { Text("저장", style = uxText(11f, 750, UxColor.goldOn)) }
}

@Composable
private fun CatalogSearch(x: ReviewItem, vm: PhotoReviewViewModel) {
    val id = x.id
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Column(Modifier.fillMaxWidth()) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                ReviewField(x.searchDraft, { vm.typeCatalogQuery(id, it) },
                    Modifier.weight(1f).testTag("review-search-input-$id"), placeholder = "위스키 이름 검색",
                    onImeAction = { vm.searchCatalog(id) },
                    imeAction = androidx.compose.ui.text.input.ImeAction.Search)
                Box(
                    Modifier.size(width = 49.dp, height = 48.dp).background(UxColor.gold, RoundedCornerShape(10.dp))
                        .quietClick { vm.searchCatalog(id) }
                        .semantics { contentDescription = "위스키 검색" }
                        .testTag("review-search-button-$id"),
                    contentAlignment = Alignment.Center,
                ) { BmLineIcon(BmLineIconId.SEARCH, 19.dp, UxColor.goldOn) }
            }
            val results = x.searchResults
            if (results != null) {
                Column(Modifier.fillMaxWidth().padding(top = 7.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                    if (results.isNotEmpty()) {
                        results.forEach { p ->
                            SelectableRow(p.name, x.selectedSearchId == p.productId,
                                { vm.selectSearchResult(id, p.productId) }, 50, 12f, 9, 10,
                                "review-search-result-$id-${p.productId}", weight = 400)
                        }
                    } else {
                        Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(horizontal = 2.dp, vertical = 3.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                            Text("검색된 위스키가 없어요.", style = uxText(12f, 400, UxColor.muted),
                                modifier = Modifier.weight(1f))
                            Box(Modifier.heightIn(min = 44.dp).quietClick { vm.registerAsNew(id) }
                                .padding(start = 7.dp, end = 1.dp, top = 5.dp, bottom = 5.dp)
                                .testTag("review-register-new-$id"),
                                contentAlignment = Alignment.Center) {
                                Text("새로 등록하기", style = uxText(12f, 750, UxColor.gold))
                            }
                        }
                    }
                }
            }
        }
        if (x.searchResults?.isNotEmpty() == true) {
            SecondaryActions(listOf("찾는 위스키가 없어요" to { vm.registerAsNew(id) }))
        }
    }
}

// ---- Details (`.details`) ----

@Composable
private fun ReviewDetails(state: PhotoReviewState, x: ReviewItem, vm: PhotoReviewViewModel, focus: ReviewFocus) {
    val other = x.type == ReviewItemType.OTHER
    Column(
        Modifier.fillMaxWidth().background(ReviewColor.detailsBg)
            .drawBehind { drawLine(UxColor.line, Offset(0f, 0f), Offset(size.width, 0f), 1.dp.toPx()) }
            .padding(start = 14.dp, end = 14.dp, top = 13.dp, bottom = 14.dp)
            .testTag("review-details-${x.id}"),
        verticalArrangement = Arrangement.spacedBy(13.dp),
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("메뉴 이름", style = uxText(11f, 400, UxColor.muted))
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (x.detailNameEditing) {
                    ReviewField(x.detailNameDraft ?: x.name, { vm.typeDetailName(x.id, it) },
                        Modifier.weight(1f).testTag("review-detail-name-input-${x.id}"), minHeight = 48.dp,
                        radius = 9.dp, border = UxColor.line, paddingStart = 10.dp, paddingEnd = 10.dp,
                        onImeAction = { vm.saveDetailName(x.id) }, focusRequester = focus.detailName(x.id))
                } else {
                    Box(Modifier.weight(1f).heightIn(min = 48.dp)
                        .background(ReviewColor.detailNameBg, RoundedCornerShape(9.dp))
                        .border(1.dp, UxColor.line, RoundedCornerShape(9.dp))
                        .padding(horizontal = 12.dp, vertical = 11.dp), contentAlignment = Alignment.CenterStart) {
                        Text(x.name.ifBlank { "이름 없음" }, style = uxText(13f, 400))
                    }
                }
                val saving = x.detailNameEditing
                Box(
                    Modifier.width(62.dp).heightIn(min = 48.dp)
                        .background(if (saving) UxColor.gold else UxColor.elevated, RoundedCornerShape(9.dp))
                        .border(1.dp, if (saving) UxColor.gold else UxColor.outline, RoundedCornerShape(9.dp))
                        .quietClick { if (saving) vm.saveDetailName(x.id) else vm.editDetailName(x.id) }
                        .testTag("review-detail-name-action-${x.id}"),
                    contentAlignment = Alignment.Center,
                ) { Text(if (saving) "저장" else "수정", style = uxText(12f, 750, if (saving) UxColor.goldOn else UxColor.gold)) }
            }
            if (x.detailNameEditing) Text("수정한 이름은 저장해야 적용돼요.", style = uxText(11f, 400, UxColor.gold))
        }
        if (other) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("가격 (원)", style = uxText(11f, 400, UxColor.muted))
                ReviewField(PhotoReviewRules.optionFieldText(x, OptionField.PRICE, null),
                    { vm.typeOptionField(x.id, OptionField.PRICE, null, it) },
                    Modifier.fillMaxWidth().testTag("review-other-price-${x.id}"), placeholder = "가격", minHeight = 43.dp,
                    radius = 9.dp, border = UxColor.line, paddingStart = 10.dp, paddingEnd = 10.dp,
                    keyboardType = KeyboardType.Number, onFocusLost = vm::commitOptionField,
                    onImeAction = vm::commitOptionField)
            }
        } else {
            OptionEditor(state, x, vm)
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DetailAction(if (other) "위스키로 분류" else "그 외 메뉴로 분류", BmLineIconId.RETRY,
                Modifier.weight(1f), UxColor.elevated, ReviewColor.categoryBorder, UxColor.text,
                "review-reclassify-${x.id}") { vm.reclassify(x.id) }
            DetailAction("이번 게시에서 제외", BmLineIconId.CLOSE, Modifier.weight(1f), ReviewColor.excludeBg,
                ReviewColor.excludeBorder, ReviewColor.excludeText, "review-exclude-${x.id}") { vm.requestExclude(x.id) }
        }
    }
}

@Composable
private fun DetailAction(label: String, icon: BmLineIconId, modifier: Modifier, bg: androidx.compose.ui.graphics.Color,
    border: androidx.compose.ui.graphics.Color, color: androidx.compose.ui.graphics.Color, tag: String, onClick: () -> Unit) {
    Row(
        modifier.heightIn(min = 50.dp).background(bg, RoundedCornerShape(10.dp))
            .border(1.dp, border, RoundedCornerShape(10.dp)).quietClick(onClick = onClick)
            .padding(horizontal = 8.dp, vertical = 11.dp).testTag(tag),
        horizontalArrangement = Arrangement.spacedBy(7.dp, Alignment.CenterHorizontally),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        BmLineIcon(icon, 16.dp, color)
        Text(label, style = uxText(11f, 700, color), textAlign = TextAlign.Center)
    }
}

@Composable
private fun OptionEditor(state: PhotoReviewState, x: ReviewItem, vm: PhotoReviewViewModel) {
    val options = PhotoReviewRules.optionSummary(x)
    Column(Modifier.fillMaxWidth().padding(top = 2.dp, bottom = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.fillMaxWidth().padding(bottom = 4.dp), horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically) {
            Text("용량별 가격", style = uxText(13f, 750))
            Text("${options.size}/${PhotoReviewRules.MAX_OPTIONS}", style = uxText(11f, 400, UxColor.sub))
        }
        if (x.primaryHasOption) OptionCard(x, null, 1, vm)
        x.options.forEachIndexed { i, _ -> OptionCard(x, i, if (x.primaryHasOption) i + 2 else i + 1, vm) }
        if (options.isEmpty()) {
            Text("인식된 옵션이 없어요. 가격을 입력하거나 아래에서 추가할 수 있어요.",
                style = uxText(11f, 400, UxColor.muted), modifier = Modifier.padding(vertical = 9.dp))
        }
        if (options.size < PhotoReviewRules.MAX_OPTIONS) {
            Box(
                Modifier.fillMaxWidth().heightIn(min = 49.dp)
                    .background(UxColor.elevated, RoundedCornerShape(10.dp))
                    .border(1.dp, UxColor.line, RoundedCornerShape(10.dp))
                    .quietClick { vm.addOption(x.id) }.padding(10.dp).testTag("review-add-option-${x.id}"),
                contentAlignment = Alignment.Center,
            ) { Text("＋ 용량 옵션 추가", style = uxText(11f, 680)) }
        }
        if (x.volumeSource == VolumeSource.DEFAULT && !x.bottle) {
            Text("매장 기본 용량 ${numberText(if (x.volume > 0) x.volume else 0.0).ifEmpty { "0" }}ml 적용",
                style = uxText(11f, 400, UxColor.muted))
        }
    }
}

@Composable
private fun OptionCard(x: ReviewItem, index: Int?, seq: Int, vm: PhotoReviewViewModel) {
    val bottle = if (index == null) x.bottle else x.options[index].bottle
    val volumeText = if (bottle) "" else PhotoReviewRules.optionFieldText(x, OptionField.VOLUME, index)
    val priceText = PhotoReviewRules.optionFieldText(x, OptionField.PRICE, index)
    val volumeInvalid = !bottle && volumeText.isNotEmpty() && !validVolume(readNumeric(volumeText))
    val priceInvalid = priceText.isNotEmpty() && !validPrice(priceValue(priceText))
    Column(
        Modifier.fillMaxWidth().background(UxColor.surface, RoundedCornerShape(10.dp))
            .border(1.dp, UxColor.line, RoundedCornerShape(10.dp)).padding(12.dp)
            .testTag("review-option-${x.id}-${index ?: "main"}"),
        verticalArrangement = Arrangement.spacedBy(9.dp),
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically) {
            Text("${seq}번 옵션", style = uxText(11f, 400, UxColor.sub))
            Box(Modifier.widthIn(min = 45.dp).heightIn(min = 40.dp).quietClick { vm.removeOption(x.id, index) }
                .testTag("review-option-remove-${x.id}-${index ?: "main"}"),
                contentAlignment = Alignment.CenterEnd) {
                Text("제거", style = uxText(12f, 400, UxColor.gold))
            }
        }
        Row(
            Modifier.heightIn(min = 38.dp).quietClick(role = androidx.compose.ui.semantics.Role.Checkbox) {
                vm.toggleBottle(x.id, index)
            }.testTag("review-bottle-${x.id}-${index ?: "main"}"),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            ReviewCheckbox(bottle)
            Text("Bottle 판매", style = uxText(12f, 400))
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            if (!bottle) {
                OptionInput("용량 (ml)", volumeText, "30", volumeInvalid, "1 ~ 999 사이의 숫자를 입력해주세요.",
                    Modifier.weight(1f), "review-volume-${x.id}-${index ?: "main"}", vm::commitOptionField) {
                    vm.typeOptionField(x.id, OptionField.VOLUME, index, it)
                }
            }
            OptionInput("가격 (원)", priceText, "17000", priceInvalid, "가격을 확인해 주세요.",
                Modifier.weight(if (bottle) 1f else 1.15f), "review-price-${x.id}-${index ?: "main"}",
                vm::commitOptionField) {
                vm.typeOptionField(x.id, OptionField.PRICE, index, it)
            }
        }
    }
}

@Composable
private fun OptionInput(label: String, value: String, placeholder: String, invalid: Boolean, message: String,
    modifier: Modifier, tag: String, onCommit: () -> Unit, onChange: (String) -> Unit) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, style = uxText(12f, 650, UxColor.sub))
        ReviewField(value, onChange, Modifier.fillMaxWidth().testTag(tag), placeholder = placeholder,
            fontWeight = 650, minHeight = 47.dp, radius = 9.dp, border = UxColor.line, invalid = invalid, paddingStart = 11.dp,
            paddingEnd = 11.dp, keyboardType = KeyboardType.Number,
            onFocusLost = onCommit, onImeAction = onCommit)
        if (invalid) Text(message, style = uxText(10f, 400, UxColor.muted, lineHeight = 1.45f))
    }
}
