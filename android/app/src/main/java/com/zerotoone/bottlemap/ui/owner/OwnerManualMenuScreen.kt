package com.zerotoone.bottlemap.ui.owner

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.rememberCoroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.CancellationException
import androidx.compose.ui.platform.LocalContext
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zerotoone.bottlemap.network.menuWriteErrorText
import com.zerotoone.bottlemap.data.owner.*
import com.zerotoone.bottlemap.ui.common.BmIcon
import com.zerotoone.bottlemap.ui.common.BmIconId
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.util.UUID

/** No press flash and dismiss IME on non-input taps. Focused BasicTextField still reopens the keyboard. */
@Composable
private fun Modifier.manualTap(onClick: () -> Unit): Modifier {
    val focus = LocalFocusManager.current
    val keyboard = LocalSoftwareKeyboardController.current
    val interaction = remember { MutableInteractionSource() }
    return this.clickable(interactionSource = interaction, indication = null) {
        focus.clearFocus()
        keyboard?.hide()
        onClick()
    }
}

private val ownerManualZone = ZoneId.of("Asia/Seoul")
private fun manualId(prefix: String) = prefix + UUID.randomUUID().toString()

/** Serializable as a single String through rememberSaveable; never sent to Backend. */
private data class DraftOption(
    val id: String, val bottle: Boolean = false, val ml: String = "",
    val price: String = "", val sale: String = "", val start: String = "", val end: String = "",
    val originalStartMs: String = "", val originalEndMs: String = ""
) {
    fun serialize() = listOf(id, if (bottle) "1" else "0", ml, price, sale, start, end,
        originalStartMs, originalEndMs)
        .joinToString("\u001f")
}
private fun freshOption() = DraftOption(manualId("local-serving-"))
private fun decodedOptions(value: String): List<DraftOption> =
    if (value.isBlank()) emptyList() else value.split("\u001e").mapNotNull { row ->
        val p = row.split("\u001f")
        if (p.size != 7 && p.size != 9) null else DraftOption(p[0], p[1] == "1",
            p[2], p[3], p[4], p[5], p[6],
            p.getOrElse(7) { "" }, p.getOrElse(8) { "" })
    }
private fun encodedOptions(v: List<DraftOption>): String =
    v.joinToString("\u001e") { it.serialize() }
private fun localDiscountEndDay(endAtEpochMs: Long): LocalDate {
    val local = Instant.ofEpochMilli(endAtEpochMs).atZone(ownerManualZone)
    return if (local.toLocalTime() == java.time.LocalTime.MIDNIGHT)
        local.toLocalDate().minusDays(1) else local.toLocalDate()
}
private fun fromSaved(o: MockMenuOption) = DraftOption(
    o.optionId, o.pourMl == null && o.label?.trim()?.lowercase() in listOf("bottle", "병"),
    o.pourMl?.toString().orEmpty(), o.priceKrw.toString(),
    o.discount?.discountedPriceKrw?.toString().orEmpty(),
    o.discount?.startAtEpochMs?.let {
        Instant.ofEpochMilli(it).atZone(ownerManualZone).toLocalDate().toString()
    }.orEmpty(),
    o.discount?.endAtEpochMs?.let { localDiscountEndDay(it).toString() }.orEmpty(),
    o.discount?.startAtEpochMs?.toString().orEmpty(),
    o.discount?.endAtEpochMs?.toString().orEmpty()
)
private fun toOption(d: DraftOption, whisky: Boolean,
    original: MockMenuOption? = null, preserveOriginalServing: Boolean = true): MockMenuOption {
    val price = d.price.toIntOrNull() ?: throw IllegalArgumentException("가격을 숫자로 입력해 주세요.")
    require(price in 1..MAX_OWNER_MENU_PRICE_KRW || original?.priceKrw == price) {
        "가격은 1원 이상, 1억 원 미만이어야 해요."
    }
    val ml = if (whisky && !d.bottle) d.ml.toIntOrNull() else null
    val unchangedLegacyNullPour = preserveOriginalServing && original != null &&
        original.pourMl == null && d.ml.isBlank() &&
        original.label?.trim()?.lowercase() !in listOf("bottle", "병")
    if (whisky && !d.bottle && !unchangedLegacyNullPour)
        require(ml != null && ml in 1..32767) {
        "용량을 입력하거나 Bottle 판매를 선택해 주세요."
    }
    val discount = if (d.sale.isEmpty()) null else {
        val salePrice = d.sale.toIntOrNull() ?: throw IllegalArgumentException("할인 가격 오류")
        require(salePrice in 1..price &&
            (salePrice <= MAX_OWNER_MENU_PRICE_KRW || original?.discount?.discountedPriceKrw == salePrice)) {
            "할인 가격은 1원 이상, 원래 가격 이하여야 해요."
        }
        val start = runCatching { LocalDate.parse(d.start) }.getOrNull()
            ?: throw IllegalArgumentException("시작일은 YYYY-MM-DD 형식이에요.")
        val end = runCatching { LocalDate.parse(d.end) }.getOrNull()
            ?: throw IllegalArgumentException("종료일은 YYYY-MM-DD 형식이에요.")
        require(!end.isBefore(start)) { "할인 종료일을 확인해 주세요." }
        // Existing imported discounts may start/end mid-day. Preserve their exact
        // instants when only the menu name or price was edited.
        val originalStart = d.originalStartMs.toLongOrNull()
        val originalEnd = d.originalEndMs.toLongOrNull()
        val unchangedDays = originalStart != null && originalEnd != null &&
            start == Instant.ofEpochMilli(originalStart).atZone(ownerManualZone).toLocalDate() &&
            end == localDiscountEndDay(originalEnd)
        if (unchangedDays) MockDiscount(salePrice, originalStart!!, originalEnd!!)
        else MockDiscount(salePrice,
            start.atStartOfDay(ownerManualZone).toInstant().toEpochMilli(),
            end.plusDays(1).atStartOfDay(ownerManualZone).toInstant().toEpochMilli())
    }
    val keepOriginal = preserveOriginalServing &&
        original != null && original.optionId == d.id &&
        (if (whisky) {
            if (d.bottle) original.pourMl == null &&
                original.label?.trim()?.lowercase() in listOf("bottle", "병")
            else original.pourMl?.toString().orEmpty() == d.ml
        } else true)
    return MockMenuOption(d.id,
        if (keepOriginal) original!!.label else if (whisky && d.bottle) "Bottle" else null,
        if (keepOriginal) original!!.pourMl else ml, price, discount)
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
    onExistingJob: (MockImportStatus) -> Unit,
    nowEpochMs: Long = rememberOwnerNow(),
    onNotice: (String) -> Unit = {},
) {
    val snapshot = when (state) {
        is MockOwnerLoadState.Ready -> state.snapshot
        is MockOwnerLoadState.Empty -> state.snapshot
        else -> null
    }
    val bar = snapshot?.bars?.firstOrNull { it.barId == snapshot.selectedBarId }
        ?: snapshot?.bars?.firstOrNull()
    val items = snapshot?.menuItems?.filter { it.barId == bar?.barId }.orEmpty()
    // Only the latest import may be resumed/cancelled. An earlier FAILED attempt
    // remains archival and must not resurrect after a later APPLIED import.
    val latestPhotoJob = snapshot?.imports?.lastOrNull { it.barId==bar?.barId }
    val activeJob = latestPhotoJob?.takeIf { it.status in listOf(
        MockImportStatus.UPLOADED,MockImportStatus.PROCESSING,
        MockImportStatus.READY_FOR_REVIEW,MockImportStatus.FAILED) }
    // A failed import is terminal: direct editing becomes available immediately.
    val activePhotoImport = activeJob?.status in listOf(
        MockImportStatus.UPLOADED,MockImportStatus.PROCESSING,
        MockImportStatus.READY_FOR_REVIEW)
    val products = snapshot?.products.orEmpty()
    val brands = (snapshot?.brands.orEmpty() +
        if(viewModel.usesProductionOwnerApi()) emptyList() else htmlBrands).distinctBy { it.brandId }
    // A deleted local product retains its ID; offer it again only for this bar,
    // via the same explicit "맞아요" confirmation as canonical catalog entries.
    val deletedLocalCandidates = products.filter { product ->
        !product.catalogMatched && bar != null &&
            snapshot?.menuItemIdHistory?.containsKey("${bar.barId}|${product.productId}") == true &&
            items.none { it.productId == product.productId }
    }
    // Existing unverified rows must also be offered for explicit ID confirmation.
    // Otherwise entering the same name creates a second local product ID.
    val activeLocalCandidates = products.filter { product ->
        !product.catalogMatched && items.any { it.productId == product.productId }
    }
    val candidates = (products.filter { it.catalogMatched } +
        (if(viewModel.usesProductionOwnerApi()) emptyList() else htmlCatalog) +
        deletedLocalCandidates + activeLocalCandidates).distinctBy { it.productId }

    val photoContext=LocalContext.current
    val photoStore=remember(photoContext) { OwnerMenuPhotoStore(photoContext) }
    val outsideFocus = LocalFocusManager.current
    val outsideKeyboard = LocalSoftwareKeyboardController.current
    var screen by rememberSaveable(bar?.barId) { mutableStateOf("list") }
    var cancelPhotoConfirm by rememberSaveable(bar?.barId) { mutableStateOf(false) }
    var query by rememberSaveable(bar?.barId) { mutableStateOf("") }
    var openCategories by rememberSaveable(bar?.barId) { mutableStateOf(listOf("위스키")) }
    var selectedId by rememberSaveable(bar?.barId) { mutableStateOf<String?>(null) }
    var editId by rememberSaveable(bar?.barId) { mutableStateOf<String?>(null) }
    var linkedId by rememberSaveable(bar?.barId) { mutableStateOf<String?>(null) }
    var rejectedId by rememberSaveable(bar?.barId) { mutableStateOf<String?>(null) }
    var itemName by rememberSaveable(bar?.barId) { mutableStateOf("") }
    LaunchedEffect(screen, itemName) {
        if(screen=="item" && itemName.trim().length>=2 && viewModel.usesProductionOwnerApi()) {
            kotlinx.coroutines.delay(300)
            runCatching { viewModel.searchCatalogLive(itemName) }
        }
    }
    var brandName by rememberSaveable(bar?.barId) { mutableStateOf("") }
    var confirmedBrandId by rememberSaveable(bar?.barId) { mutableStateOf<String?>(null) }
    var rejectedBrandId by rememberSaveable(bar?.barId) { mutableStateOf<String?>(null) }
    LaunchedEffect(screen,itemName,editId,linkedId) {
        if(screen=="item" && editId==null && linkedId==null &&
            viewModel.usesProductionOwnerApi()) {
            // The name itself identifies the brand; never ask for a second
            // manual brand field. Search canonical names and aliases.
            val lookup=manualBrandSearchQuery(itemName,"")
            if(lookup.length>=2) {
                kotlinx.coroutines.delay(300)
                runCatching { viewModel.searchCatalogBrandsLive(lookup) }
            }
        }
    }
    var category by rememberSaveable(bar?.barId) { mutableStateOf("위스키") }
    var alcoholKind by rememberSaveable(bar?.barId) { mutableStateOf("") }
    var categoryMenuExpanded by rememberSaveable(bar?.barId) { mutableStateOf(false) }
    var optionText by rememberSaveable(bar?.barId) {
        mutableStateOf(encodedOptions(listOf(freshOption())))
    }
    var saleOption by rememberSaveable(bar?.barId) { mutableStateOf(0) }
    var beforePromoOptions by rememberSaveable(bar?.barId) { mutableStateOf<String?>(null) }
    var confirm by rememberSaveable { mutableStateOf<String?>(null) }
    var calendarTarget by rememberSaveable { mutableStateOf<String?>(null) }
    var promoOptionExpanded by rememberSaveable { mutableStateOf(false) }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    var saving by rememberSaveable(bar?.barId) { mutableStateOf(false) }
    val saveScope = rememberCoroutineScope()
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
        itemName = item?.displayNameOverride ?: p?.displayName.orEmpty()
        brandName = brands.firstOrNull { it.brandId == p?.brandId }?.name.orEmpty()
        confirmedBrandId = if(item!=null) p?.brandId else null
        rejectedBrandId = null
        category = p?.let(::manualEditorCategory) ?: "위스키"
        alcoholKind = p?.let(::manualEditorAlcoholKind).orEmpty()
        // Photo-imported listings may contain more than three options. Allow editing
        // the first three without silently dropping any additional persisted ones.
        val editableLimit = if (category == "위스키") MANUAL_MENU_MAX_OPTIONS else 1
        setOptions(item?.options?.take(editableLimit)?.map(::fromSaved)
            ?: listOf(freshOption()))
        beforePromoOptions = null
        error = null
        screen = "item"
    }
    fun back() {
        when (screen) {
            "promo" -> {
                beforePromoOptions?.let { optionText = it }
                beforePromoOptions = null
                calendarTarget = null
                error = null
                screen = "item"
            }
            "item" -> { error = null; screen = "list"; selectedId = null }
            else -> onBack()
        }
    }
    BackHandler(screen != "list") { back() }

    fun save() {
        if (bar == null || saving) return
        try {
            if(editId == null) {
                require(inactiveOwnerCatalogMatch(candidates, itemName) == null) {
                    "운영이 중지된 카탈로그 상품이에요. 운영자에게 문의해 주세요."
                }
            }
            require(!activePhotoImport) { "ACTIVE_IMPORT_EXISTS" }
            val name = itemName.trim()
            val old = items.firstOrNull { it.barMenuItemId == editId }
            val persisted = products.firstOrNull { it.productId == old?.productId }
            val linked = if (old != null) persisted
                else candidates.firstOrNull { it.productId == linkedId }
            // Product/brand matching is inferred from the typed menu name.
            // A brand match is never gated on a second manual text field.
            val savedName = old?.displayNameOverride ?: persisted?.displayName
            val confirmedExistingName = old == null && candidates.any {
                it.productId == linkedId && it.displayName == name &&
                    manualEditorCategory(it) == category
            }
            require(name.isNotEmpty() && (name.length <= 80 ||
                (name.length <= 200 && (name == savedName || confirmedExistingName)))) {
                "메뉴 이름을 확인해 주세요."
            }
            val sameCategory = linked?.let { manualEditorCategory(it) } == category
            val sharedLocal = linked?.takeIf { !it.catalogMatched }?.let { product ->
                snapshot?.menuItems.orEmpty().any {
                    it.barId != bar.barId && it.productId == product.productId
                }
            } == true
            require(!sharedLocal || (sameCategory &&
                alcoholKind.trim().takeIf { category == "기타 주류" && it.isNotEmpty() } ==
                    linked?.let(::manualEditorAlcoholKind)?.takeIf { it.isNotBlank() })) {
                "다른 매장에서도 사용하는 상품의 종류는 변경할 수 없어요."
            }
            // Check the immutable catalog subtype for both new links and edits.
            val linkedCatalog = linked?.takeIf { it.catalogMatched }
            if (linkedCatalog != null && category == "기타 주류") {
                require(alcoholKind.trim().takeIf { it.isNotBlank() } ==
                    manualEditorAlcoholKind(linkedCatalog).trim().takeIf { it.isNotBlank() }) {
                    "카탈로그 상품의 주류 종류는 변경할 수 없어요."
                }
            }
            if (category == "기타 주류" && alcoholKind.isBlank()) {
                // Existing catalog/photo entries may have no Mock-only subtype.
                // Do not require one unless the owner is adding or changing the type.
                require((linked != null && sameCategory && linked.otherAlcoholKind.isNullOrBlank()) ||
                    (linkedCatalog != null && linkedCatalog.otherAlcoholKind.isNullOrBlank())) {
                    "주류 종류를 입력해 주세요."
                }
            }
            val whisky = category == "위스키"
            // A custom other-alcohol kind IS the category on the menu board:
            // entering "맥주" produces a "맥주" group instead of "기타 주류".
            // A linked canonical product's category remains immutable.
            val effectiveCategoryCode = when {
                category == "기타 주류" && linked?.catalogMatched == true ->
                    requireNotNull(linked).category
                category == "기타 주류" ->
                    alcoholKind.trim().ifEmpty { "otherAlcohol" }
                category in MANUAL_MENU_CATEGORIES -> manualMenuCategoryCode(category)
                else -> {
                    require(sameCategory && persisted != null) { "지원하지 않는 종류로 변경할 수 없어요." }
                    persisted.category
                }
            }
            require(old == null || sameCategory || old.options.size <= 1) {
                "기존 용량 옵션을 삭제하지 않고 종류를 바꿀 수 없어요."
            }
            val editedOptions = (if (whisky) draftOptions else draftOptions.take(1))
                .mapIndexed { index, draft ->
                    val parsed = toOption(draft, whisky,
                        old?.options?.firstOrNull { it.optionId == draft.id },
                        preserveOriginalServing = sameCategory)
                    // Preserve imported serving labels/identity when editing a
                    // single-price category without switching its category.
                    if (!whisky && sameCategory) {
                        old?.options?.getOrNull(index)?.let { original ->
                            parsed.copy(label = original.label, pourMl = original.pourMl)
                        } ?: parsed
                    } else parsed
                }
            manualMenuOptionError(editedOptions, effectiveCategoryCode, old?.options.orEmpty())?.let {
                throw IllegalArgumentException(it)
            }
            val editableLimit = if (whisky) MANUAL_MENU_MAX_OPTIONS else 1
            val legacyTail = if (old != null && old.options.size > editableLimit) {
                require(persisted?.let(::manualEditorCategory) == category) {
                    "기존 추가 옵션을 보존하려면 원래 종류로 수정해 주세요."
                }
                old.options.drop(editableLimit)
            } else emptyList()
            val options = editedOptions + legacyTail
            if (old != null && persisted?.catalogMatched == true) {
                require(manualEditorCategory(persisted) == category) {
                    "제품 종류를 변경하려면 새 메뉴를 추가해 주세요."
                }
            }
            // Distinguish an explicit "아니에요" from an accidental second row.
            // Never infer or assign a canonical ID solely from matching text.
            if (old == null && linked == null) {
                val existingLocal = products.firstOrNull { product ->
                    !product.catalogMatched && product.productId != rejectedId &&
                        manualEditorCategory(product) == category &&
                        existingBarProductMenu(items, bar.barId, product.productId)?.let { row ->
                            listOfNotNull(product.displayName, row.displayNameOverride).any {
                                it.replace(" ", "").equals(
                                    name.replace(" ", ""), ignoreCase = true)
                            }
                        } == true
                }
                require(existingLocal == null) {
                    "이미 등록한 상품이에요. 기존 메뉴에서 용량·가격을 수정해 주세요."
                }
            }
            val p = when {
                linked != null && !linked.catalogMatched -> if (sharedLocal) linked else linked.copy(
                    displayName = name, category = effectiveCategoryCode,
                    otherAlcoholKind = alcoholKind.trim().takeIf {
                        category == "기타 주류" && it.isNotEmpty() })
                linked != null -> linked
                else -> {
                    val brandFromName = manualBrandProposal(brands,name,"",null)
                    val fallbackBrand = brandFromName?.name
                        ?: if (whisky) "기타 브랜드"
                           else alcoholKind.trim().ifEmpty { category }
                    val reusedBrandId = confirmedBrandId?.takeIf { id ->
                        brands.any { it.brandId==id }
                    } ?: brandFromName?.brandId ?: brands.firstOrNull {
                        normalizeOwnerCatalogName(it.name)==
                            normalizeOwnerCatalogName(fallbackBrand)
                    }?.brandId ?: manualId("local-brand-")
                    MockCatalogProduct(
                        manualId("local-unverified-"), reusedBrandId, name,
                        category = effectiveCategoryCode, catalogMatched = false,
                        otherAlcoholKind = alcoholKind.trim().takeIf {
                        category == "기타 주류" && it.isNotEmpty() })
                }
            }
            val duplicate = existingBarProductMenu(items, bar.barId, p.productId)
            require(duplicate == null || duplicate.barMenuItemId == editId) {
                "이미 등록한 상품이에요. 기존 메뉴에서 용량·가격을 수정해 주세요."
            }
            val brand = brands.firstOrNull { it.brandId == p.brandId }
                ?: MockBrand(p.brandId, manualBrandProposal(brands,name,"",null)?.name
                    ?: if (whisky) "기타 브랜드" else alcoholKind.trim().ifEmpty { category })
            val stagedItem = MockBarMenuItem(old?.barMenuItemId ?: manualId("local-menu-"),
                bar.barId, p.productId, options, soldOut = old?.soldOut ?: false,
                displayNameOverride = if ((p.catalogMatched || sharedLocal) &&
                    name != p.displayName) name else null)
            val stagedProduct = if (products.none { it.productId == p.productId } ||
                (linked != null && !linked.catalogMatched && !sharedLocal)) p else null
            // The current API's newProduct path writes directly to the global
            // catalog. Keep the draft onscreen instead of accidentally submitting
            // a beer or unapproved whisky as a shared canonical product.
            // Per-bar pending entries are tracked separately in issue #152.
            if (viewModel.usesProductionOwnerApi() && old == null && stagedProduct != null) {
                error = "새 상품은 관리자 승인 후 등록할 수 있어요. " +
                    "현재는 기존 카탈로그 상품만 매장 메뉴에 추가할 수 있어요."
                return
            }
            if(viewModel.usesProductionOwnerApi()) {
                saving = true
                saveScope.launch {
                    try {
                        if (old == null && linkedId == null && name.length >= 2) {
                            // Await a fresh server lookup before creating any product.
                            // A deleted menu is NOT a deleted catalog product: offer
                            // the original product again with "맞아요 / 아니에요".
                            val fresh = viewModel.searchCatalogLive(name)
                            val exact = fresh.firstOrNull {
                                it.isActive && it.productId != rejectedId &&
                                    (manualMenuCategoryLabel(it.category).takeIf { label ->
                                        label in MANUAL_MENU_CATEGORIES
                                    } ?: "기타 주류") == category &&
                                    (normalizeOwnerCatalogName(it.displayName) ==
                                        normalizeOwnerCatalogName(name) ||
                                     normalizeOwnerCatalogName(it.matchedAlias.orEmpty()) ==
                                        normalizeOwnerCatalogName(name))
                            }
                            if (exact != null) {
                                error = "“${exact.displayName}”이 맞나요? 맞아요 또는 아니에요를 선택해 주세요."
                                return@launch
                            }
                        }
                        viewModel.saveManualMenuItemLive(stagedItem, stagedProduct, brand)
                        screen = "list"; selectedId = null; editId = null; error = null
                    } catch(cancelled: CancellationException) {
                        throw cancelled
                    } catch(e: Exception) {
                        error = menuWriteErrorText(e)
                    } finally { saving = false }
                }
            } else {
                viewModel.saveManualMenuItem(stagedItem, stagedProduct, brand)
                screen = "list"; selectedId = null; editId = null; error = null
            }
        } catch (e: Exception) { error = e.message ?: "저장하지 못했어요." }
    }

    if(cancelPhotoConfirm && activeJob!=null) {
        AlertDialog(
            onDismissRequest={cancelPhotoConfirm=false},
            title={Text("메뉴판 사진 등록을 취소할까요?")},
            text={Text("선택한 사진과 검수한 내용이 모두 삭제돼요.")},
            confirmButton={TextButton(onClick={
                // Never erase a photo still referenced by any published job.
                val removedIds=unpublishedRetryChainIds(
                    requireNotNull(snapshot),activeJob.menuImportId)
                val removed=snapshot.imports.filter {it.menuImportId in removedIds}
                val retainedUris=snapshot?.imports.orEmpty().filterNot {
                    it in removed
                }.flatMap{it.images.map {image->image.sourceUri}}.toSet()
                val photoCopies=removed.flatMap{it.images}.distinctBy{it.sourceUri}
                    .filter {it.sourceUri !in retainedUris}
                    .map {MockPhoto(it.imageId,it.sourceUri,MockPhotoKind.MENU_CAPTURE)}
                if(!saving) {
                    saving=true
                    saveScope.launch {
                        try {
                            viewModel.cancelPhotoImportLive(activeJob.menuImportId)
                            cancelPhotoConfirm=false
                            error=null
                            screen="list"
                            // Only delete local photos after server confirmed the cancellation.
                            photoCopies.forEach(photoStore::delete)
                        } catch(cancelled: CancellationException) {
                            throw cancelled
                        } catch(e: Exception) {
                            error=e.message ?: "사진 등록 작업을 취소하지 못했어요."
                        } finally { saving=false }
                    }
                }
            }){Text("작업 취소하기",color=Color(0xFFFFB4AB))}},
            dismissButton={TextButton(onClick={cancelPhotoConfirm=false}){Text("돌아가기")}}
        )
    }
    if (confirm != null) {
        val action = requireNotNull(confirm)
        val target = items.firstOrNull { it.barMenuItemId == action.removePrefix("stock:") }
        AlertDialog(onDismissRequest = { confirm = null; error = null },
            title = { Text(when(action) {
                "delete" -> "메뉴를 삭제할까요?"
                "reset" -> "전체 메뉴를 초기화할까요?"
                else -> if (target?.soldOut == true) "판매를 재개할까요?" else "품절 처리할까요?"
            }) },
            text = { Column { Text(when(action) {
                "delete" -> "삭제하면 고객 메뉴에서도 바로 사라집니다."
                "reset" -> "모든 메뉴와 용량·가격 정보가 삭제됩니다."
                else -> "품절 메뉴는 고객에게 숨겨지며 판매 재개 시 다시 공개됩니다."
            }); error?.let { Text(it, color = Color(0xFFFFB4AB)) } } },
            confirmButton = { TextButton(onClick = {
                if(!saving) {
                    saving=true
                    saveScope.launch {
                        try {
                            when(action) {
                                "delete" -> editId?.let { viewModel.deleteMenuItemLive(it) }
                                "reset" -> bar?.barId?.let { viewModel.clearMenuForBarLive(it) }
                                else -> target?.let {
                                    viewModel.setSoldOutLive(it.barMenuItemId, !it.soldOut)
                                }
                            }
                            confirm=null
                            error=null
                            selectedId=null
                            screen="list"
                        } catch(cancelled: CancellationException) {
                            throw cancelled
                        } catch(e: Exception) {
                            error=e.message ?: "서버 변경에 실패했어요."
                        } finally { saving=false }
                    }
                }
            }, enabled = !saving) { Text(when(action) {
                "delete" -> "삭제하기"; "reset" -> "초기화"; else -> "상태 변경"
            }) } },
            dismissButton = { TextButton(onClick = { confirm = null; error = null }) { Text("취소") } }
        )
    }
    Column(Modifier.fillMaxSize().background(V4Color.background)
        .pointerInput(Unit) {
            detectTapGestures(onTap = {
                outsideFocus.clearFocus()
                outsideKeyboard?.hide()
            })
        }) {
        V4Toolbar(null, ::back)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            when {
                state == MockOwnerLoadState.Loading ->
                    Text("메뉴 정보 불러오는 중", color = V4Color.sub)
                state is MockOwnerLoadState.Error -> {
                    Text(state.message, color = V4Color.text)
                    ManualButton("다시 시도", viewModel::retry)
                }
                bar == null -> Text("관리할 매장이 없어요.", color = V4Color.sub)
                screen == "list" -> {
                    Text("메뉴 관리", color=V4Color.text,fontWeight=FontWeight.Bold,
                        fontFamily=FontFamily.Serif,fontSize=24.sp)
                    Text("사진으로 메뉴 추가",color=V4Color.text,
                        fontWeight=FontWeight.Bold,fontSize=16.sp)
                    Row(Modifier.fillMaxWidth().background(V4Color.surface,
                        RoundedCornerShape(11.dp)).manualTap {
                            val status=activeJob?.status
                            if(status!=null) onExistingJob(status) else onNewPhoto()
                        }.padding(horizontal=12.dp,vertical=12.dp),
                        verticalAlignment=Alignment.CenterVertically,
                        horizontalArrangement=Arrangement.spacedBy(9.dp)) {
                        BmIcon(BmIconId.REVIEW,null,Modifier.size(24.dp),tint=V4Color.primary)
                        Text(when(activeJob?.status) {
                            MockImportStatus.PROCESSING,MockImportStatus.UPLOADED ->
                                "메뉴판 분석 중 · 작업 확인하기"
                            MockImportStatus.READY_FOR_REVIEW ->
                                "메뉴 검수 이어서 하기"
                            MockImportStatus.FAILED -> "메뉴판 분석 실패 · 다시 확인하기"
                            else -> "메뉴판 사진으로 추가하기"
                        },color=V4Color.text,
                            fontWeight=FontWeight.Bold,fontSize=13.sp,
                            modifier=Modifier.weight(1f))
                        if(activeJob!=null) {
                            Box(Modifier
                                .background(Color(0xFF693630),RoundedCornerShape(7.dp))
                                .border(1.dp,Color(0xFF7B453E),RoundedCornerShape(7.dp))
                                .manualTap { cancelPhotoConfirm=true }
                                .padding(horizontal=11.dp,vertical=5.dp)) {
                                Text("취소하기",color=Color(0xFFFFE8E5),fontSize=11.sp,
                                    fontWeight=FontWeight.SemiBold)
                            }
                        }
                        Text("›",color=V4Color.sub,fontSize=20.sp)
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically) {
                        Text("현재 게시 메뉴", color = V4Color.text, fontWeight = FontWeight.Bold,
                            fontSize = 16.sp)
                        Text("+ 직접 추가", Modifier.manualTap {
                            if (activePhotoImport) onNotice("사진으로 메뉴 등록 작업 중에는 메뉴를 수정할 수 없어요.")
                            else edit(null)
                        }
                            .testTag("manual-menu-add"), color = V4Color.primary, fontSize = 12.sp)
                    }
                    error?.let { Text(it, color = Color(0xFFFFB4AB), fontSize = 12.sp) }
                    V4SearchField(query, { query = it }, "manual-menu-search", "메뉴명·브랜드 검색")
                    val entries = items.map { item ->
                        val p = products.firstOrNull { it.productId == item.productId }
                        Triple(item, p, brands.firstOrNull { it.brandId == p?.brandId }?.name.orEmpty())
                    }
                    val visible = entries.filter { (item, p, brand) ->
                        manualMenuMatches(item, p, brand, query)
                    }
                    Row(Modifier.fillMaxWidth(),
                        horizontalArrangement=Arrangement.SpaceBetween,
                        verticalAlignment=Alignment.CenterVertically) {
                        Row(horizontalArrangement=Arrangement.spacedBy(9.dp),
                            verticalAlignment=Alignment.CenterVertically) {
                            Text(if(query.isEmpty()) "전체 " + items.size + "개" else
                                visible.size.toString() + "개 검색됨",
                                color=V4Color.sub,fontSize=11.sp)
                            Text("최근 갱신 "+ownerDisplayDate(bar.lastMenuPublishedAtEpochMs),
                                color=V4Color.primary,fontSize=11.sp)
                        }
                        Text("메뉴를 선택해서 편집하세요",color=V4Color.sub,fontSize=11.sp)
                    }
                    if (visible.isEmpty()) Text(if (query.isEmpty()) "등록된 메뉴가 없어요."
                        else "검색 결과가 없어요.", color = V4Color.sub)
                    val shownCategories = MANUAL_MENU_CATEGORIES + visible.mapNotNull { (_, p, _) ->
                        p?.let(::ownerV4Category)
                    }.distinct().filterNot { it in MANUAL_MENU_CATEGORIES }
                    shownCategories.forEach { cat ->
                        val rows = visible.filter { (_, p, _) ->
                            p != null && ownerV4Category(p) == cat
                        }
                        if (rows.isNotEmpty()) {
                            val open = query.isNotBlank() || cat in openCategories
                            Column(Modifier.fillMaxWidth()) {
                                // Only the category header is a rounded surface; no outer rounded
                                // container means no square corners behind the collapsed header.
                                Row(Modifier.fillMaxWidth()
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(V4Color.surface)
                                    .manualTap {
                                        openCategories = if (open) openCategories - cat
                                            else openCategories + cat
                                    }.padding(horizontal = 12.dp, vertical = 10.dp),
                                    verticalAlignment = Alignment.CenterVertically) {
                                    Text(cat, Modifier.weight(1f), color = V4Color.text,
                                        fontSize = 14.sp, fontWeight = FontWeight.Bold)
                                    Text(if (open) "⌃" else "⌄", color = V4Color.sub)
                                }
                                if (open) {
                                    val groups = if (cat == "위스키") rows.groupBy { it.third }
                                        else mapOf("" to rows)
                                    groups.entries.forEachIndexed { groupIndex, entry ->
                                        if (cat == "위스키") {
                                            Text(entry.key.ifBlank { "기타 브랜드" },
                                                Modifier.padding(start = 4.dp, top = 18.dp, bottom = 8.dp),
                                                color = V4Color.primary, fontSize = 13.sp,
                                                fontWeight = FontWeight.Bold)
                                        } else Spacer(Modifier.height(8.dp))
                                        entry.value.forEachIndexed { index, (item, product, brandLabel) ->
                                            OwnerManualMenuRow(item, requireNotNull(product), brandLabel,
                                                nowEpochMs, selectedId == item.barMenuItemId,
                                                onSelect = { selectedId = if (selectedId == item.barMenuItemId)
                                                    null else item.barMenuItemId },
                                                onEdit = {
                                                     if (activePhotoImport)
                                                         onNotice("사진으로 메뉴 등록 작업 중에는 메뉴를 수정할 수 없어요.")
                                                     else edit(item)
                                                 },
                                                onStock = {
                                                     if (activePhotoImport)
                                                         onNotice("사진으로 메뉴 등록 작업 중에는 메뉴를 수정할 수 없어요.")
                                                     else confirm = "stock:" + item.barMenuItemId
                                                 })
                                            if (index < entry.value.lastIndex)
                                                HorizontalDivider(color = V4Color.line, thickness = 1.dp)
                                        }
                                        if (groupIndex < groups.size - 1) {
                                            Spacer(Modifier.height(8.dp))
                                            HorizontalDivider(color = V4Color.line, thickness = 2.dp)
                                        }
                                    }
                                }
                            }
                            Spacer(Modifier.height(8.dp))
                        }
                    }
                    HorizontalDivider(color = V4Color.line, thickness = 1.dp)
                    Box(Modifier.fillMaxWidth().height(43.dp)
                        .background(Color(0xFF693630),RoundedCornerShape(7.dp))
                        .border(1.dp, Color(0xFF7B453E), RoundedCornerShape(7.dp))
                        .manualTap {
                            if (activePhotoImport) onNotice("사진으로 메뉴 등록 작업 중에는 메뉴를 수정할 수 없어요.")
                            else confirm = "reset"
                        }
                        .testTag("manual-menu-reset"), contentAlignment = Alignment.Center) {
                        Row(horizontalArrangement = Arrangement.spacedBy(9.dp),
                            verticalAlignment = Alignment.CenterVertically) {
                            BmIcon(BmIconId.ERROR, null, Modifier.size(17.dp),
                                tint = Color(0xFFFFE8E5))
                            Text("전체 메뉴 초기화", color = Color(0xFFFFE8E5),
                                fontSize = 12.sp,fontWeight=FontWeight.SemiBold)
                        }
                    }
                }
                screen == "item" -> {
                    Row(Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically) {
                        Text(if (editId == null) "메뉴 직접 추가" else "메뉴 수정",
                            color = V4Color.text, fontFamily = FontFamily.Serif,
                            fontSize = 24.sp, fontWeight = FontWeight.Bold)
                        Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                            ManualTopButton("할인", false) {
                                beforePromoOptions = optionText
                                saleOption = 0; error = null; screen = "promo"
                            }
                            if (editId != null) ManualTopButton("삭제", true) {
                                if (activePhotoImport)
                                    onNotice("사진으로 메뉴 등록 작업 중에는 메뉴를 수정할 수 없어요.")
                                else confirm = "delete"
                            }
                        }
                    }
                    V4FormField("메뉴 이름", itemName, {
                        itemName = it.take(80)
                        // Keep an explicitly confirmed product link when its per-bar
                        // display name is customized. Category changes still clear it.
                        if (editId == null) rejectedId = null
                    }, placeholder = "예: 라가불린 10년", testTag = "manual-menu-name")
                    if (editId == null) {
                        val matchedBrandId = confirmedBrandId
                            ?: manualBrandProposal(brands,itemName,"",null)?.brandId
                        val suggested=manualProductProposal(
                            candidates,itemName,category,matchedBrandId,rejectedId)
                        val inactiveMatch = inactiveOwnerCatalogMatch(candidates, itemName)
                        if(inactiveMatch != null) {
                            Text("“" + inactiveMatch.displayName +
                                "”은 현재 비활성 상품이에요. 선택하거나 새로 만들 수 없어요. 운영자에게 문의해 주세요.",
                                color=V4Color.sub, fontSize=13.sp)
                        }
                        if (suggested != null && inactiveMatch==null &&
                            linkedId != suggested.productId) {
                            Text("“" + suggested.displayName + "”이 맞나요?", color = V4Color.text)
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                ManualButton("맞아요", {
                                    linkedId = suggested.productId
                                    confirmedBrandId = suggested.brandId
                                    itemName = suggested.displayName
                                    brandName = brands.firstOrNull {
                                        it.brandId == suggested.brandId }?.name.orEmpty()
                                    if (category == "기타 주류")
                                        alcoholKind = manualEditorAlcoholKind(suggested)
                                }, modifier = Modifier.weight(1f))
                                ManualButton("아니에요", { rejectedId = suggested.productId },
                                    modifier = Modifier.weight(1f), secondary = true)
                            }
                        }
                        if (linkedId != null) {
                            val old = existingBarProductMenu(items, bar.barId, requireNotNull(linkedId))
                            if (old != null) ManualButton("기존 메뉴에서 용량·가격 수정", {
                                edit(old)
                            }, secondary = false)
                        }
                    }
                    Text("종류", color = V4Color.text, fontSize = 13.sp)
                    Box(Modifier.fillMaxWidth()) {
                        Row(Modifier.fillMaxWidth().height(43.dp)
                            .background(V4Color.elevated, RoundedCornerShape(9.dp))
                            .border(1.dp, V4Color.line, RoundedCornerShape(9.dp))
                            .manualTap { categoryMenuExpanded = true }
                            .padding(horizontal = 12.dp),
                            verticalAlignment = Alignment.CenterVertically) {
                            Text(category, color = V4Color.text, modifier = Modifier.weight(1f),
                                fontSize = 14.sp)
                            Text("⌄", color = V4Color.primary, fontSize = 16.sp)
                        }
                        DropdownMenu(expanded = categoryMenuExpanded,
                            onDismissRequest = { categoryMenuExpanded = false },
                            modifier = Modifier.background(V4Color.elevated)) {
                            MANUAL_MENU_CATEGORIES.forEach { cat ->
                                Text(cat, modifier = Modifier.fillMaxWidth()
                                    .background(if (cat == category) V4Color.surface
                                        else V4Color.elevated)
                                    .manualTap {
                                        categoryMenuExpanded = false
                                        if (cat != category) {
                                            category = cat; linkedId = null; rejectedId = null
                                            // Preserve provisional drafts across category toggles.
                                        }
                                    }.padding(horizontal = 16.dp, vertical = 12.dp),
                                    color = V4Color.text, fontSize = 13.sp)
                            }
                        }
                    }
                    if (category == "기타 주류")
                        V4FormField("주류 종류", alcoholKind, { alcoholKind = it.take(30) },
                            placeholder = "예: 하이볼, 맥주",
                            testTag = "manual-menu-alcohol-kind")
                    HorizontalDivider(color = V4Color.line, thickness = 1.dp)
                    if (category == "위스키") {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement =
                            Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                            Text("용량별 가격", color = V4Color.text, fontSize = 15.sp,
                                fontWeight = FontWeight.Bold)
                            Text(draftOptions.size.toString() + "/3", color = V4Color.sub,
                                fontSize = 11.sp)
                        }
                    }
                    (if (category == "위스키") draftOptions else draftOptions.take(1))
                        .forEachIndexed { i, d ->
                            Column(Modifier.fillMaxWidth().background(V4Color.surface,
                                RoundedCornerShape(9.dp))
                                .border(1.dp, V4Color.line, RoundedCornerShape(9.dp))
                                .padding(11.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                if (category == "위스키") {
                                    Row(Modifier.fillMaxWidth(), horizontalArrangement =
                                        Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                                        Row(verticalAlignment = Alignment.CenterVertically,
                                            horizontalArrangement = Arrangement.spacedBy(7.dp),
                                            modifier = Modifier.weight(1f)) {
                                            Text((i+1).toString() + "번 옵션",
                                                color = V4Color.sub, fontSize = 11.sp)
                                            if (d.sale.isNotBlank()) {
                                                Text("할인 · " + d.sale + "원",
                                                    color = Color(0xFFF7DFBF),
                                                    fontSize = 10.sp, lineHeight = 10.sp,
                                                    modifier = Modifier
                                                        .background(Color(0xFF4B3826),
                                                            RoundedCornerShape(4.dp))
                                                        .border(1.dp, Color(0xFF9C7A52),
                                                            RoundedCornerShape(4.dp))
                                                        .padding(all = 4.dp))
                                            }
                                        }
                                        if (draftOptions.size > 1) Text("제거",
                                            Modifier.manualTap {
                                                setOptions(draftOptions.filterIndexed { j, _ -> j != i })
                                            }, color = V4Color.primary, fontSize = 11.sp)
                                    }
                                    V4CompactCheck("Bottle 판매", d.bottle) { checked ->
                                        changeOption(i) { it.copy(bottle = checked) }
                                    }
                                    Row(Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                                        verticalAlignment = Alignment.Bottom) {
                                        if (d.bottle) Column(Modifier.weight(1f),
                                            verticalArrangement = Arrangement.spacedBy(5.dp)) {
                                            Text("용량", color = V4Color.text,
                                                fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                                            Box(Modifier.fillMaxWidth().height(43.dp)
                                                .border(1.dp, V4Color.line, RoundedCornerShape(9.dp))
                                                .background(V4Color.elevated, RoundedCornerShape(9.dp))
                                                .padding(horizontal = 12.dp),
                                                contentAlignment = Alignment.CenterStart) {
                                                Text("Bottle", color = V4Color.text, fontSize = 14.sp)
                                            }
                                        } else V4FormField("용량 (ml)", d.ml, { v ->
                                            changeOption(i) { it.copy(ml = v.filter(Char::isDigit)) }
                                        }, modifier = Modifier.weight(1f),
                                            keyboardType = KeyboardType.Number,
                                            testTag = "manual-menu-ml-" + i)
                                        V4FormField("가격 (원)", d.price, { v ->
                                            changeOption(i) { it.copy(price = ownerPriceInput(it.price, v)) }
                                        }, modifier = Modifier.weight(1f),
                                            keyboardType = KeyboardType.Number,
                                            testTag = "manual-menu-price-" + i)
                                    }
                                } else {
                                    V4FormField("판매 가격 (원)", d.price, { v ->
                                        changeOption(i) { it.copy(price = ownerPriceInput(it.price, v)) }
                                    }, keyboardType = KeyboardType.Number,
                                        testTag = "manual-menu-price-" + i)
                                }

                            }
                        }
                    if (category == "위스키") {
                        if (draftOptions.size < MANUAL_MENU_MAX_OPTIONS)
                            Box(Modifier.fillMaxWidth().height(40.dp)
                                .background(V4Color.elevated, RoundedCornerShape(8.dp))
                                .border(1.dp, V4Color.line, RoundedCornerShape(8.dp))
                                .manualTap { setOptions(draftOptions + freshOption()) }
                                .testTag("manual-menu-option-add"),
                                contentAlignment = Alignment.Center) {
                                Text("+ 용량 옵션 추가", color = V4Color.text, fontSize = 12.sp)
                            }
                        else Text("가격 옵션은 최대 3개까지 등록할 수 있어요.",
                            color = V4Color.sub, fontSize = 11.sp)
                    }
                    HorizontalDivider(color = V4Color.line, thickness = 1.dp)
                    error?.let { Text(it, color = Color(0xFFFFB4AB)) }
                    ManualButton(if(saving) "저장 중..." else if (editId == null) "메뉴 추가"
                        else "저장하기", ::save, modifier = Modifier.testTag("manual-menu-save"))
                }
                screen == "promo" -> {
                    Text("할인 설정", color = V4Color.text, fontFamily = FontFamily.Serif,
                        fontSize = 24.sp, fontWeight = FontWeight.Bold)
                    Text("할인 기간과 가격을 설정해 주세요.", color = V4Color.sub,
                        fontSize = 12.sp)
                    if (category == "위스키") {
                        Text("적용 용량", color = V4Color.text, fontSize = 13.sp,
                            fontWeight = FontWeight.SemiBold)
                        Box(Modifier.fillMaxWidth()) {
                            Row(Modifier.fillMaxWidth().height(43.dp)
                                .background(V4Color.elevated, RoundedCornerShape(9.dp))
                                .border(1.dp, V4Color.line, RoundedCornerShape(9.dp))
                                .manualTap { promoOptionExpanded = true }
                                .padding(horizontal = 12.dp),
                                verticalAlignment = Alignment.CenterVertically) {
                                val selected = draftOptions.getOrNull(saleOption)
                                Text(selected?.let {
                                    (if (it.bottle) "Bottle" else it.ml + "ml") +
                                        " · " + it.price + "원"
                                }.orEmpty(), modifier = Modifier.weight(1f),
                                    color = V4Color.text, fontSize = 14.sp)
                                Text("⌄", color = V4Color.text)
                            }
                            DropdownMenu(expanded = promoOptionExpanded,
                                onDismissRequest = { promoOptionExpanded = false },
                                modifier = Modifier.background(V4Color.elevated)) {
                                draftOptions.forEachIndexed { i, d ->
                                    Text((if (d.bottle) "Bottle" else d.ml + "ml") +
                                        " · " + d.price + "원",
                                        modifier = Modifier.fillMaxWidth()
                                            .manualTap {
                                                if (i != saleOption) {
                                                    // Discard this option's un-applied promotion edits;
                                                    // other options retain their original draft values.
                                                    val previous = beforePromoOptions
                                                        ?.let(::decodedOptions)
                                                        ?.getOrNull(saleOption)
                                                    if (previous != null)
                                                        changeOption(saleOption) { previous }
                                                    saleOption = i
                                                    calendarTarget = null
                                                    error = null
                                                }
                                                promoOptionExpanded = false
                                            }
                                            .padding(horizontal = 16.dp, vertical = 12.dp),
                                        color = V4Color.text, fontSize = 13.sp)
                                }
                            }
                        }
                    }
                    val d = draftOptions.getOrNull(saleOption)
                    if (d != null) {
                        V4FormField("할인 가격 (원)", d.sale, { v ->
                            changeOption(saleOption) { it.copy(sale = ownerPriceInput(it.sale, v)) }
                        }, keyboardType = KeyboardType.Number,
                            testTag = "manual-menu-discount-price")
                        ManualDateField("시작일", d.start) {
                            calendarTarget = if (calendarTarget == "start") null else "start"
                        }
                        ManualDateField("종료일", d.end) {
                            calendarTarget = if (calendarTarget == "end") null else "end"
                        }
                        if (calendarTarget != null) {
                            val startEpoch = runCatching {
                                LocalDate.parse(d.start).toEpochDay()
                            }.getOrDefault(Long.MIN_VALUE)
                            val endEpoch = runCatching {
                                LocalDate.parse(d.end).toEpochDay()
                            }.getOrDefault(Long.MIN_VALUE)
                            // Exactly the same calendar and range transition as
                            // Owner's temporary business-closure period UI.
                            androidx.compose.runtime.key(saleOption) {
                                OwnerVacationCalendar(
                                    today = LocalDate.now(ownerManualZone).toEpochDay(),
                                    startDay = startEpoch, endDay = endEpoch,
                                    selectedTarget = requireNotNull(calendarTarget),
                                    onSelectTarget = { calendarTarget = it },
                                    onPick = { picked ->
                                        val chosenTarget = requireNotNull(calendarTarget)
                                        val updated = updateQuickVacationDates(
                                            startEpoch, endEpoch, picked, chosenTarget)
                                        if (updated == null) {
                                            error = "종료일은 시작일 이후여야 해요."
                                        } else {
                                            changeOption(saleOption) {
                                                it.copy(
                                                    start = updated.first.takeUnless { day ->
                                                        day == Long.MIN_VALUE
                                                    }?.let(LocalDate::ofEpochDay)?.toString().orEmpty(),
                                                    end = updated.second.takeUnless { day ->
                                                        day == Long.MIN_VALUE
                                                    }?.let(LocalDate::ofEpochDay)?.toString().orEmpty(),
                                                )
                                            }
                                            calendarTarget = if (chosenTarget == "start") "end" else "start"
                                            error = null
                                        }
                                    }
                                )
                            }
                        }
                        HorizontalDivider(color = V4Color.line, thickness = 1.dp)
                        error?.let { Text(it, color = Color(0xFFFFB4AB)) }
                        ManualButton("할인 적용", {
                            try {
                                val latest = decodedOptions(optionText)[saleOption]
                                require(latest.sale.isNotBlank()) { "할인 가격을 입력해 주세요." }
                                toOption(latest, category == "위스키",
                                    items.firstOrNull { it.barMenuItemId == editId }?.options
                                        ?.firstOrNull { it.optionId == latest.id })
                                beforePromoOptions = null
                                calendarTarget = null
                                screen = "item"; error = null
                            } catch (e: Exception) { error = e.message }
                        }, modifier = Modifier.testTag("manual-menu-promo-apply"))
                        if (d.sale.isNotEmpty()) ManualButton("할인 제거", {
                            changeOption(saleOption) {
                                it.copy(sale = "", start = "", end = "",
                                    originalStartMs = "", originalEndMs = "")
                            }
                            beforePromoOptions = null
                            calendarTarget = null
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
private fun ManualSmallButton(label: String, onClick: () -> Unit) {
    Box(Modifier.border(1.dp, V4Color.line, RoundedCornerShape(7.dp))
        .background(V4Color.elevated, RoundedCornerShape(7.dp))
        .manualTap(onClick).padding(horizontal = 10.dp, vertical = 7.dp)) {
        Text(label, color = V4Color.text, fontSize = 11.sp,
            fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun ManualTopButton(label: String, danger: Boolean, onClick: () -> Unit) {
    Box(Modifier.height(31.dp)
        .background(if (danger) Color(0xFF693630) else V4Color.elevated,
            RoundedCornerShape(7.dp))
        .border(1.dp, if (danger) Color(0xFF7B453E) else V4Color.line,
            RoundedCornerShape(7.dp))
        .manualTap(onClick).padding(horizontal = 11.dp),
        contentAlignment = Alignment.Center) {
        Text(label, color = if (danger) Color(0xFFFFE8E5) else V4Color.text,
            fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun ManualDateField(label: String, isoDate: String, onClick: () -> Unit) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(5.dp)) {
        Text(label, color = V4Color.text, fontSize = 13.sp,
            fontWeight = FontWeight.SemiBold)
        Row(Modifier.fillMaxWidth().height(43.dp)
            .background(V4Color.elevated, RoundedCornerShape(9.dp))
            .border(1.dp, V4Color.line, RoundedCornerShape(9.dp))
            .manualTap(onClick)
            .testTag(if (label == "시작일") "manual-menu-start-date"
                else "manual-menu-end-date")
            .padding(horizontal = 12.dp),
            verticalAlignment = Alignment.CenterVertically) {
            val display = runCatching {
                LocalDate.parse(isoDate).format(
                    java.time.format.DateTimeFormatter.ofPattern("MM/dd/yyyy"))
            }.getOrDefault("날짜 선택")
            Text(display, modifier = Modifier.weight(1f), color = V4Color.text,
                fontSize = 13.sp)
            Canvas(Modifier.size(17.dp)) {
                drawRoundRect(V4Color.text, topLeft = Offset(2.dp.toPx(), 3.dp.toPx()),
                    size = Size(13.dp.toPx(), 12.dp.toPx()),
                    cornerRadius = androidx.compose.ui.geometry.CornerRadius(1.dp.toPx()),
                    style = Stroke(1.5.dp.toPx()))
                drawLine(V4Color.text, Offset(2.dp.toPx(), 7.dp.toPx()),
                    Offset(15.dp.toPx(), 7.dp.toPx()), strokeWidth = 1.5.dp.toPx())
                drawLine(V4Color.text, Offset(6.dp.toPx(), 1.dp.toPx()),
                    Offset(6.dp.toPx(), 5.dp.toPx()), strokeWidth = 1.5.dp.toPx())
                drawLine(V4Color.text, Offset(11.dp.toPx(), 1.dp.toPx()),
                    Offset(11.dp.toPx(), 5.dp.toPx()), strokeWidth = 1.5.dp.toPx())
            }
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
            RoundedCornerShape(9.dp)).manualTap(onClick).padding(12.dp),
        contentAlignment = Alignment.Center) {
        Text(label, color = if (secondary) V4Color.text else V4Color.background,
            fontSize = 13.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun OwnerManualMenuRow(
    item: MockBarMenuItem, product: MockCatalogProduct, brand: String,
    nowEpochMs: Long, selected: Boolean,
    onSelect: () -> Unit, onEdit: () -> Unit, onStock: () -> Unit
) {
    OwnerMenuFlatRow(
        item = item, product = product, brandName = brand,
        nowEpochMs = nowEpochMs, showStatus = true,
        selected = selected, onSelect = onSelect, onEdit = onEdit, onStock = onStock
    )
}
