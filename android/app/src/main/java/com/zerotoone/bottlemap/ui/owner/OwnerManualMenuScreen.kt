package com.zerotoone.bottlemap.ui.owner

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zerotoone.bottlemap.data.owner.*
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.util.UUID

private val ownerManualZone = ZoneId.of("Asia/Seoul")
private fun manualId(prefix: String) = prefix + UUID.randomUUID().toString()

/** Serializable as a single String through rememberSaveable; never sent to Backend. */
private data class DraftOption(
    val id: String, val bottle: Boolean = false, val ml: String = "",
    val price: String = "", val sale: String = "", val start: String = "", val end: String = ""
) {
    fun serialize() = listOf(id, if (bottle) "1" else "0", ml, price, sale, start, end)
        .joinToString("\u001f")
}
private fun freshOption() = DraftOption(manualId("local-serving-"))
private fun decodedOptions(value: String): List<DraftOption> =
    if (value.isBlank()) emptyList() else value.split("\u001e").mapNotNull { row ->
        val p = row.split("\u001f")
        if (p.size != 7) null else DraftOption(p[0], p[1] == "1", p[2], p[3], p[4], p[5], p[6])
    }
private fun encodedOptions(v: List<DraftOption>): String =
    v.joinToString("\u001e") { it.serialize() }
private fun fromSaved(o: MockMenuOption) = DraftOption(
    o.optionId, o.label == "Bottle", o.pourMl?.toString().orEmpty(), o.priceKrw.toString(),
    o.discount?.discountedPriceKrw?.toString().orEmpty(),
    o.discount?.startAtEpochMs?.let {
        Instant.ofEpochMilli(it).atZone(ownerManualZone).toLocalDate().toString()
    }.orEmpty(),
    o.discount?.endAtEpochMs?.let {
        Instant.ofEpochMilli(it).atZone(ownerManualZone).toLocalDate().minusDays(1).toString()
    }.orEmpty()
)
private fun toOption(d: DraftOption, whisky: Boolean): MockMenuOption {
    val price = d.price.toIntOrNull() ?: throw IllegalArgumentException("가격을 숫자로 입력해 주세요.")
    require(price > 0) { "가격은 1원 이상이어야 해요." }
    val ml = if (whisky && !d.bottle) d.ml.toIntOrNull() else null
    if (whisky && !d.bottle) require(ml != null && ml > 0) {
        "용량을 입력하거나 Bottle 판매를 선택해 주세요."
    }
    val discount = if (d.sale.isEmpty()) null else {
        val salePrice = d.sale.toIntOrNull() ?: throw IllegalArgumentException("할인 가격 오류")
        require(salePrice in 1..price) { "할인 가격은 원래 가격 이하여야 해요." }
        val start = runCatching { LocalDate.parse(d.start) }.getOrNull()
            ?: throw IllegalArgumentException("시작일은 YYYY-MM-DD 형식이에요.")
        val end = runCatching { LocalDate.parse(d.end) }.getOrNull()
            ?: throw IllegalArgumentException("종료일은 YYYY-MM-DD 형식이에요.")
        require(!end.isBefore(start)) { "할인 종료일을 확인해 주세요." }
        MockDiscount(salePrice,
            start.atStartOfDay(ownerManualZone).toInstant().toEpochMilli(),
            end.plusDays(1).atStartOfDay(ownerManualZone).toInstant().toEpochMilli())
    }
    return MockMenuOption(d.id, if (whisky && d.bottle) "Bottle" else null, ml, price, discount)
}

private val htmlCatalog = listOf(
    MockCatalogProduct("mock-lagavulin-10", "mock-brand-lagavulin", "라가불린 10년",
        ageYears = 10),
    MockCatalogProduct("mock-lagavulin-16", "mock-brand-lagavulin", "라가불린 16년",
        ageYears = 16)
)
private val htmlBrands = listOf(MockBrand("mock-brand-lagavulin", "라가불린"))

@Composable
internal fun OwnerManualMenuScreen(
    state: MockOwnerLoadState,
    viewModel: OwnerMockViewModel,
    onBack: () -> Unit,
    onNewPhoto: () -> Unit,
    onExistingJob: (MockImportStatus) -> Unit
) {
    val snapshot = when (state) {
        is MockOwnerLoadState.Ready -> state.snapshot
        is MockOwnerLoadState.Empty -> state.snapshot
        else -> null
    }
    val bar = snapshot?.bars?.firstOrNull { it.barId == snapshot.selectedBarId }
        ?: snapshot?.bars?.firstOrNull()
    val items = snapshot?.menuItems?.filter { it.barId == bar?.barId }.orEmpty()
    val products = snapshot?.products.orEmpty()
    val brands = (snapshot?.brands.orEmpty() + htmlBrands).distinctBy { it.brandId }
    val candidates = (products.filter { it.catalogMatched } + htmlCatalog)
        .distinctBy { it.productId }

    var screen by rememberSaveable(bar?.barId) { mutableStateOf("list") }
    var query by rememberSaveable(bar?.barId) { mutableStateOf("") }
    var openCategories by rememberSaveable(bar?.barId) { mutableStateOf(listOf("위스키")) }
    var selectedId by rememberSaveable(bar?.barId) { mutableStateOf<String?>(null) }
    var editId by rememberSaveable(bar?.barId) { mutableStateOf<String?>(null) }
    var linkedId by rememberSaveable(bar?.barId) { mutableStateOf<String?>(null) }
    var rejectedId by rememberSaveable(bar?.barId) { mutableStateOf<String?>(null) }
    var itemName by rememberSaveable(bar?.barId) { mutableStateOf("") }
    var brandName by rememberSaveable(bar?.barId) { mutableStateOf("") }
    var category by rememberSaveable(bar?.barId) { mutableStateOf("위스키") }
    var alcoholKind by rememberSaveable(bar?.barId) { mutableStateOf("") }
    var optionText by rememberSaveable(bar?.barId) {
        mutableStateOf(encodedOptions(listOf(freshOption())))
    }
    var saleOption by rememberSaveable(bar?.barId) { mutableStateOf(0) }
    var confirm by rememberSaveable { mutableStateOf<String?>(null) }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    val draftOptions = decodedOptions(optionText)
    fun setOptions(v: List<DraftOption>) { optionText = encodedOptions(v) }
    fun changeOption(index: Int, transform: (DraftOption) -> DraftOption) {
        setOptions(draftOptions.mapIndexed { i, d -> if (i == index) transform(d) else d })
    }
    fun edit(item: MockBarMenuItem?) {
        editId = item?.barMenuItemId
        val p = products.firstOrNull { it.productId == item?.productId }
        linkedId = p?.productId?.takeIf { p.catalogMatched }
        rejectedId = null
        itemName = p?.displayName.orEmpty()
        brandName = brands.firstOrNull { it.brandId == p?.brandId }?.name.orEmpty()
        category = p?.let { manualMenuCategoryLabel(it.category) } ?: "위스키"
        alcoholKind = p?.otherAlcoholKind.orEmpty()
        setOptions(item?.options?.map(::fromSaved) ?: listOf(freshOption()))
        error = null
        screen = "item"
    }
    fun back() {
        when (screen) {
            "promo" -> { error = null; screen = "item" }
            "item" -> { error = null; screen = "list"; selectedId = null }
            else -> onBack()
        }
    }
    BackHandler(screen != "list") { back() }

    fun save() {
        if (bar == null) return
        try {
            val name = itemName.trim()
            require(name.isNotEmpty() && name.length <= 80) { "메뉴 이름을 확인해 주세요." }
            if (category == "기타 주류") require(alcoholKind.trim().isNotEmpty()) {
                "주류 종류를 입력해 주세요."
            }
            val whisky = category == "위스키"
            val options = (if (whisky) draftOptions else draftOptions.take(1))
                .map { toOption(it, whisky) }
            manualMenuOptionError(options, manualMenuCategoryCode(category))?.let {
                throw IllegalArgumentException(it)
            }
            val old = items.firstOrNull { it.barMenuItemId == editId }
            val persisted = products.firstOrNull { it.productId == old?.productId }
            if (old != null && persisted != null) {
                require(persisted.displayName == name &&
                    manualMenuCategoryLabel(persisted.category) == category) {
                    "다른 상품은 새 메뉴로 추가해 주세요."
                }
            }
            val linked = if (old != null) persisted
                else candidates.firstOrNull { it.productId == linkedId }
            val p = linked ?: MockCatalogProduct(
                manualId("local-unverified-"), manualId("local-brand-"), name,
                category = manualMenuCategoryCode(category), catalogMatched = false,
                otherAlcoholKind = alcoholKind.trim().takeIf { category == "기타 주류" }
            )
            val duplicate = existingBarProductMenu(items, bar.barId, p.productId)
            require(duplicate == null || duplicate.barMenuItemId == editId) {
                "이미 등록한 상품이에요. 기존 메뉴에서 용량·가격을 수정해 주세요."
            }
            val brand = if (linked != null) brands.firstOrNull { it.brandId == p.brandId }
                else MockBrand(p.brandId, brandName.trim().ifEmpty {
                    if (whisky) "기타 브랜드" else category
                })
            viewModel.saveManualMenuItem(
                MockBarMenuItem(old?.barMenuItemId ?: manualId("local-menu-"),
                    bar.barId, p.productId, options, soldOut = old?.soldOut ?: false),
                if (products.none { it.productId == p.productId }) p else null,
                brand
            )
            screen = "list"; selectedId = null; editId = null; error = null
        } catch (e: Exception) { error = e.message ?: "저장하지 못했어요." }
    }

    if (confirm != null) {
        val action = requireNotNull(confirm)
        val target = items.firstOrNull { it.barMenuItemId == action.removePrefix("stock:") }
        AlertDialog(onDismissRequest = { confirm = null },
            title = { Text(when(action) {
                "delete" -> "메뉴를 삭제할까요?"
                "reset" -> "전체 메뉴를 초기화할까요?"
                else -> if (target?.soldOut == true) "판매를 재개할까요?" else "품절 처리할까요?"
            }) },
            text = { Text(when(action) {
                "delete" -> "삭제하면 고객 메뉴에서도 바로 사라집니다."
                "reset" -> "모든 메뉴와 용량·가격 정보가 삭제됩니다."
                else -> "품절 메뉴는 고객에게 숨겨지며 판매 재개 시 다시 공개됩니다."
            }) },
            confirmButton = { TextButton(onClick = {
                try {
                    when(action) {
                        "delete" -> editId?.let { viewModel.deleteMenuItem(it) }
                        "reset" -> bar?.barId?.let { viewModel.clearMenuForBar(it) }
                        else -> target?.let { viewModel.setSoldOut(it.barMenuItemId, !it.soldOut) }
                    }
                    confirm = null; error = null; selectedId = null; screen = "list"
                } catch (e: Exception) { confirm = null; error = e.message }
            }) { Text(when(action) {
                "delete" -> "삭제하기"; "reset" -> "초기화"; else -> "상태 변경"
            }) } },
            dismissButton = { TextButton(onClick = { confirm = null }) { Text("취소") } }
        )
    }
    Column(Modifier.fillMaxSize().background(V4Color.background)) {
        V4Toolbar(null, ::back)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp), verticalArrangement = Arrangement.spacedBy(13.dp)) {
            when {
                state == MockOwnerLoadState.Loading ->
                    Text("메뉴 정보 불러오는 중", color = V4Color.sub)
                state is MockOwnerLoadState.Error -> {
                    Text(state.message, color = V4Color.text)
                    ManualButton("다시 시도", viewModel::retry)
                }
                bar == null -> Text("관리할 매장이 없어요.", color = V4Color.sub)
                screen == "list" -> {
                    Text("메뉴 관리", color = V4Color.text, fontWeight = FontWeight.Bold,
                        fontSize = 24.sp)
                    Text("최근 갱신 " + ownerDisplayDate(bar.lastMenuPublishedAtEpochMs),
                        color = V4Color.sub, fontSize = 12.sp)
                    Text("사진으로 메뉴 추가", color = V4Color.text, fontWeight = FontWeight.Bold)
                    val job = snapshot?.imports?.lastOrNull { it.barId == bar.barId }
                    ManualButton(when(job?.status) {
                        MockImportStatus.PROCESSING -> "AI 분석 중 · 작업 확인"
                        MockImportStatus.READY_FOR_REVIEW -> "추가할 메뉴 확인하기"
                        MockImportStatus.FAILED -> "메뉴판 분석 실패 · 작업 확인"
                        else -> "메뉴판 사진으로 추가하기"
                    }, {
                        val status = job?.status
                        if (status == MockImportStatus.PROCESSING ||
                            status == MockImportStatus.READY_FOR_REVIEW ||
                            status == MockImportStatus.FAILED)
                            onExistingJob(status) else onNewPhoto()
                    }, secondary = true)
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically) {
                        Text("현재 게시 메뉴", color = V4Color.text, fontWeight = FontWeight.Bold)
                        Text("+ 직접 추가", Modifier.clickable { edit(null) }
                            .testTag("manual-menu-add"), color = V4Color.primary)
                    }
                    V4SearchField(query, { query = it }, "manual-menu-search", "메뉴명·브랜드 검색")
                    val entries = items.map { item ->
                        val p = products.firstOrNull { it.productId == item.productId }
                        Triple(item, p, brands.firstOrNull { it.brandId == p?.brandId }?.name.orEmpty())
                    }
                    val visible = entries.filter { (item, p, brand) ->
                        manualMenuMatches(item, p, brand, query)
                    }
                    Text(if (query.isEmpty()) "전체 " + items.size + "개" else
                        visible.size.toString() + "개 검색됨",
                        color = V4Color.sub, fontSize = 11.sp)
                    if (visible.isEmpty()) Text(if (query.isEmpty()) "등록된 메뉴가 없어요."
                        else "검색 결과가 없어요.", color = V4Color.sub)
                    MANUAL_MENU_CATEGORIES.forEach { cat ->
                        val rows = visible.filter { (_, p, _) ->
                            p != null && manualMenuCategoryLabel(p.category) == cat
                        }
                        if (rows.isNotEmpty()) {
                            val open = query.isNotBlank() || cat in openCategories
                            Column(Modifier.fillMaxWidth().border(1.dp, V4Color.line,
                                RoundedCornerShape(11.dp))
                                .background(Color(0xFF292522), RoundedCornerShape(11.dp))) {
                                Row(Modifier.fillMaxWidth().background(V4Color.elevated)
                                    .clickable {
                                        openCategories = if (open) openCategories - cat
                                            else openCategories + cat
                                    }.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                                    Text(cat, Modifier.weight(1f), color = V4Color.text,
                                        fontSize = 14.sp, fontWeight = FontWeight.Bold)
                                    Text(if (open) "⌃" else "⌄", color = V4Color.primary)
                                }
                                if (open) {
                                    val groups = if (cat == "위스키") rows.groupBy { it.third }
                                        else mapOf("" to rows)
                                    groups.forEach { (brand, grouped) ->
                                        if (cat == "위스키")
                                            Text(brand.ifBlank { "기타 브랜드" },
                                                Modifier.padding(start = 11.dp, top = 12.dp, bottom = 5.dp),
                                                color = V4Color.primary,
                                                fontSize = 14.sp, fontWeight = FontWeight.Bold)
                                        grouped.forEach { (item, product, brandLabel) ->
                                            OwnerManualMenuRow(item, requireNotNull(product), brandLabel,
                                                selectedId == item.barMenuItemId,
                                                onSelect = { selectedId = if (selectedId == item.barMenuItemId)
                                                    null else item.barMenuItemId },
                                                onEdit = { edit(item) },
                                                onStock = { confirm = "stock:" + item.barMenuItemId })
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Text("⚠ 전체 메뉴 초기화", Modifier.clickable { confirm = "reset" }
                        .testTag("manual-menu-reset").padding(vertical = 10.dp),
                        color = Color(0xFFFFB4AB), fontSize = 12.sp)
                }
                screen == "item" -> {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(if (editId == null) "메뉴 직접 추가" else "메뉴 수정",
                            color = V4Color.text, fontSize = 24.sp, fontWeight = FontWeight.Bold)
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Text("할인", Modifier.clickable { saleOption = 0; error = null; screen = "promo" },
                                color = V4Color.primary)
                            if (editId != null) Text("삭제", Modifier.clickable {
                                confirm = "delete"
                            }, color = Color(0xFFFFB4AB))
                        }
                    }
                    V4FormField("메뉴 이름", itemName, {
                        itemName = it.take(80)
                        if (editId == null) { linkedId = null; rejectedId = null }
                    }, placeholder = "예: 라가불린 10년", testTag = "manual-menu-name")
                    if (editId == null) {
                        val suggested = candidates.firstOrNull { p ->
                            itemName.any(Char::isDigit) && itemName.isNotBlank() &&
                                p.displayName.replace(" ", "").contains(
                                    itemName.trim().replace(" ", ""), ignoreCase = true) &&
                                p.productId != rejectedId &&
                                manualMenuCategoryLabel(p.category) == category
                        }
                        if (suggested != null && linkedId != suggested.productId) {
                            Text("“" + suggested.displayName + "”이 맞나요?", color = V4Color.text)
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                ManualButton("맞아요", {
                                    linkedId = suggested.productId
                                    itemName = suggested.displayName
                                    brandName = brands.firstOrNull {
                                        it.brandId == suggested.brandId }?.name.orEmpty()
                                }, modifier = Modifier.weight(1f))
                                ManualButton("아니에요", { rejectedId = suggested.productId },
                                    modifier = Modifier.weight(1f), secondary = true)
                            }
                        }
                        if (linkedId != null) {
                            val old = existingBarProductMenu(items, bar.barId, requireNotNull(linkedId))
                            if (old != null) ManualButton("기존 메뉴에서 용량·가격 수정", {
                                edit(old)
                            }, secondary = true) else Text(
                                "카탈로그 상품 ID: " + linkedId, color = V4Color.primary, fontSize = 11.sp)
                        } else Text("카탈로그 미확인 · 수동 등록", color = V4Color.sub,
                            fontSize = 11.sp)
                    }
                    if (editId == null && linkedId == null)
                        V4FormField("브랜드", brandName, { brandName = it },
                            placeholder = "브랜드 이름")
                    Text("종류", color = V4Color.text)
                    MANUAL_MENU_CATEGORIES.forEach { cat ->
                        Row(Modifier.fillMaxWidth().clickable {
                            if (cat != category) {
                                category = cat; linkedId = null; rejectedId = null
                                if (cat != "위스키") setOptions(draftOptions.take(1))
                            }
                        }.padding(vertical = 4.dp)) {
                            Text(if (cat == category) "◉  " else "○  ", color = V4Color.primary)
                            Text(cat, color = V4Color.text)
                        }
                    }
                    if (category == "기타 주류")
                        V4FormField("주류 종류", alcoholKind, { alcoholKind = it.take(60) },
                            placeholder = "예: 하이볼, 맥주")
                    Text(if (category == "위스키") "용량별 가격" else "판매 가격 (원)",
                        color = V4Color.text, fontWeight = FontWeight.Bold)
                    (if (category == "위스키") draftOptions else draftOptions.take(1))
                        .forEachIndexed { i, d ->
                            Column(Modifier.fillMaxWidth().background(V4Color.elevated,
                                RoundedCornerShape(9.dp))
                                .border(1.dp, V4Color.line, RoundedCornerShape(9.dp))
                                .padding(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                if (category == "위스키") {
                                    Row(Modifier.fillMaxWidth(), horizontalArrangement =
                                        Arrangement.SpaceBetween) {
                                        Text((i+1).toString() + "번 옵션", color = V4Color.sub)
                                        if (draftOptions.size > 1) Text("제거",
                                            Modifier.clickable {
                                                setOptions(draftOptions.filterIndexed { j, _ -> j != i })
                                            }, color = V4Color.primary)
                                    }
                                    V4CompactCheck("Bottle 판매", d.bottle) { checked ->
                                        changeOption(i) { it.copy(bottle = checked) }
                                    }
                                    if (!d.bottle) V4FormField("용량 (ml)", d.ml, { v ->
                                        changeOption(i) { it.copy(ml = v.filter(Char::isDigit)) }
                                    }, keyboardType = KeyboardType.Number)
                                }
                                V4FormField("가격 (원)", d.price, { v ->
                                    changeOption(i) { it.copy(price = v.filter(Char::isDigit)) }
                                }, keyboardType = KeyboardType.Number,
                                    testTag = "manual-menu-price-" + i)
                                if (d.sale.isNotBlank())
                                    Text("할인 · " + d.sale + "원", color = V4Color.primary)
                            }
                        }
                    if (category == "위스키" && draftOptions.size < MANUAL_MENU_MAX_OPTIONS)
                        Text("＋ 용량 옵션 추가", Modifier.clickable {
                            setOptions(draftOptions + freshOption())
                        }.padding(vertical = 8.dp), color = V4Color.primary)
                    error?.let { Text(it, color = Color(0xFFFFB4AB)) }
                    ManualButton(if (editId == null) "메뉴 추가" else "저장하기",
                        ::save, modifier = Modifier.testTag("manual-menu-save"))
                }
                screen == "promo" -> {
                    Text("할인 설정", color = V4Color.text, fontSize = 24.sp,
                        fontWeight = FontWeight.Bold)
                    Text("할인 기간과 가격을 설정해 주세요.", color = V4Color.sub)
                    if (category == "위스키") draftOptions.forEachIndexed { i, d ->
                        Row(Modifier.fillMaxWidth().clickable { saleOption = i }
                            .padding(8.dp)) {
                            Text(if (saleOption == i) "◉ " else "○ ", color = V4Color.primary)
                            Text((if (d.bottle) "Bottle" else d.ml + "ml") +
                                " · " + d.price + "원", color = V4Color.text)
                        }
                    }
                    val d = draftOptions.getOrNull(saleOption)
                    if (d != null) {
                        V4FormField("할인 가격 (원)", d.sale, { v ->
                            changeOption(saleOption) { it.copy(sale = v.filter(Char::isDigit)) }
                        }, keyboardType = KeyboardType.Number)
                        V4FormField("시작일", d.start, { v ->
                            changeOption(saleOption) { it.copy(start = v) }
                        }, placeholder = "YYYY-MM-DD")
                        V4FormField("종료일", d.end, { v ->
                            changeOption(saleOption) { it.copy(end = v) }
                        }, placeholder = "YYYY-MM-DD")
                        error?.let { Text(it, color = Color(0xFFFFB4AB)) }
                        ManualButton("할인 적용", {
                            try {
                                val latest = decodedOptions(optionText)[saleOption]
                                require(latest.sale.isNotBlank()) { "할인 가격을 입력해 주세요." }
                                toOption(latest, category == "위스키")
                                screen = "item"; error = null
                            } catch (e: Exception) { error = e.message }
                        }, modifier = Modifier.testTag("manual-menu-promo-apply"))
                        if (d.sale.isNotEmpty()) ManualButton("할인 제거", {
                            changeOption(saleOption) { it.copy(sale = "", start = "", end = "") }
                            screen = "item"; error = null
                        }, secondary = true)
                    }
                }
            }
            Spacer(Modifier.height(18.dp))
        }
    }
}

@Composable
private fun ManualButton(
    label: String, onClick: () -> Unit, modifier: Modifier = Modifier,
    secondary: Boolean = false
) {
    Box(modifier.fillMaxWidth().background(
        if (secondary) V4Color.elevated else V4Color.primary, RoundedCornerShape(9.dp))
        .border(1.dp, if (secondary) V4Color.line else V4Color.primary,
            RoundedCornerShape(9.dp)).clickable(onClick = onClick).padding(12.dp),
        contentAlignment = Alignment.Center) {
        Text(label, color = if (secondary) V4Color.text else V4Color.background,
            fontSize = 13.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun OwnerManualMenuRow(
    item: MockBarMenuItem, product: MockCatalogProduct, brand: String, selected: Boolean,
    onSelect: () -> Unit, onEdit: () -> Unit, onStock: () -> Unit
) {
    Box(Modifier.fillMaxWidth().padding(horizontal = 7.dp, vertical = 3.dp)
        .background(V4Color.surface, RoundedCornerShape(9.dp))
        .border(1.dp, V4Color.line, RoundedCornerShape(9.dp))
        .height(80.dp).testTag("manual-menu-row-" + item.barMenuItemId)) {
        Row(Modifier.fillMaxSize().clickable(onClick = onSelect).padding(horizontal = 7.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(7.dp)) {
            Box(Modifier.size(width = 42.dp, height = 54.dp)
                .background(Color(0xFF40352C), RoundedCornerShape(6.dp)),
                contentAlignment = Alignment.Center) {
                Canvas(Modifier.size(width = 27.dp, height = 40.dp)) {
                    val u = size.width / 27f
                    drawRect(Color(0xFF967F58), Offset(10*u, 0f), Size(7*u, 7*u))
                    drawRoundRect(Color(0xFF658C7A), Offset(4*u, 7*u), Size(19*u, 31*u),
                        cornerRadius = androidx.compose.ui.geometry.CornerRadius(3*u))
                    drawRect(Color(0xFFE1D2B5), Offset(6*u, 18*u), Size(15*u, 12*u))
                }
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(manualMenuShortName(product, brand), color = V4Color.text,
                    fontSize = 12.sp, fontWeight = FontWeight.Bold, maxLines = 2)
                Text(if (item.soldOut) "품절" else "판매 중", fontSize = 10.sp,
                    color = if (item.soldOut) Color(0xFFFFB4AB) else V4Color.positive)
                if (!product.catalogMatched)
                    Text("카탈로그 미확인", color = V4Color.sub, fontSize = 9.sp)
            }
            Column(Modifier.widthIn(min = 96.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                item.options.take(3).forEach { option ->
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        val discount = option.discount
                        val active = discount != null &&
                            System.currentTimeMillis() >= discount.startAtEpochMs &&
                            System.currentTimeMillis() < discount.endAtEpochMs
                        if (active) Text("할인", color = V4Color.primary, fontSize = 9.sp,
                            modifier = Modifier.border(1.dp, V4Color.primary,
                                RoundedCornerShape(4.dp)).padding(horizontal = 3.dp))
                        Text(option.pourMl?.toString()?.plus("ml") ?: option.label.orEmpty(),
                            color = V4Color.text, fontSize = 10.sp)
                        Text("%,d원".format(option.displayPrice(System.currentTimeMillis())),
                            color = V4Color.sub, fontSize = 10.sp)
                    }
                }
            }
        }
        if (selected) Row(Modifier.align(Alignment.CenterEnd)
            .background(V4Color.elevated, RoundedCornerShape(8.dp))
            .padding(6.dp), horizontalArrangement = Arrangement.spacedBy(5.dp)) {
            Text("수정", Modifier.background(V4Color.background, RoundedCornerShape(6.dp))
                .border(1.dp, V4Color.primary, RoundedCornerShape(6.dp))
                .clickable(onClick = onEdit).padding(8.dp)
                .testTag("manual-menu-row-edit"), color = V4Color.primary, fontSize = 12.sp)
            Text(if (item.soldOut) "재개" else "품절",
                Modifier.background(V4Color.background, RoundedCornerShape(6.dp))
                    .border(1.dp, V4Color.line, RoundedCornerShape(6.dp))
                    .clickable(onClick = onStock).padding(8.dp)
                    .testTag("manual-menu-row-stock"), color = V4Color.text, fontSize = 12.sp)
        }
    }
}
