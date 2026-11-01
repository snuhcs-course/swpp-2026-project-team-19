package com.zerotoone.bottlemap.data.owner

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Persistence boundary. Production API adapter must be implemented only after contract agreement. */
interface MockOwnerStateStore {
    fun read(): MockOwnerSnapshot?
    fun write(snapshot: MockOwnerSnapshot)
}
class InMemoryMockOwnerStateStore(initial: MockOwnerSnapshot? = null) : MockOwnerStateStore {
    var stored: MockOwnerSnapshot? = initial
        private set
    override fun read() = stored
    override fun write(snapshot: MockOwnerSnapshot) { stored = snapshot }
}

/**
 * Local-only Mock business operations: never call Retrofit. Both Owner and mock Customer
 * preview observe this same StateFlow. A successful mutation is persisted BEFORE publication.
 */
interface OwnerMockRepository {
    val state: StateFlow<MockOwnerLoadState>
    fun retryLoad()
    fun registerApplication(application: MockOwnerApplication)
    fun saveRegistrationDraft(draft: MockRegistrationDraft?)
    fun seedExistingCandidateForFixture(bar: MockBar)
    fun submitRegistrationDraftForFixture(): String
    fun approveForFixture(applicationId: String, bar: MockBar)
    fun closeApplicationForFixture(applicationId: String, status: MockApplicationStatus)
    fun dismissRejectedForFixture(applicationId: String)
    fun saveBar(bar: MockBar)
    fun confirmMenuInformation(barId: String, confirmedAtEpochMs: Long)
    fun applyOperatingException(barId: String, exception: MockOperatingException)
    fun cancelOperatingException(barId: String, exceptionId: String)
    fun selectBar(barId: String)
    fun saveBrand(brand: MockBrand)
    fun saveCatalogProduct(product: MockCatalogProduct)
    fun saveMenuItem(item: MockBarMenuItem)
    /** Atomic, app-local direct menu edit. Not an agreed backend contract. */
    fun saveManualMenuItem(
        item: MockBarMenuItem, newProduct: MockCatalogProduct? = null,
        newBrand: MockBrand? = null,
    )
    fun setSoldOut(barMenuItemId: String, value: Boolean)
    fun deleteMenuItem(barMenuItemId: String)
    fun clearMenuForBar(barId: String)
    fun startPhotoImport(barId: String, selectedUris: List<String>, fixture: MockPhotoExtractionSource): String
    fun decideLine(importId: String, extractedItemId: String, expectedVersion: Int, decision: MockReviewDecision)
    fun publishAddOnly(importId: String, expectedVersion: Int): Int
    fun preview(barId: String, nowEpochMs: Long): MockPreview?
}

/** Local-only serving option invariants shared by direct entry, review, and publish. */
internal fun validMockMenuOption(option: MockMenuOption): Boolean =
    option.priceKrw > 0 &&
        (option.pourMl == null || option.pourMl in 1..32767) &&
        (option.discount == null ||
            (option.discount.discountedPriceKrw in 1..option.priceKrw &&
                option.discount.startAtEpochMs < option.discount.endAtEpochMs))

/** Local-only hours invariant; CUSTOM_HOURS must have valid start and end minutes. */
internal fun validMockOperatingException(exception: MockOperatingException): Boolean =
    exception.fromEpochDay <= exception.toEpochDay &&
        (exception.kind != MockExceptionKind.CUSTOM_HOURS ||
            (exception.openMinutes != null && exception.openMinutes in 0..1439 &&
                exception.closeMinutes != null && exception.closeMinutes in 0..1439 &&
                if (exception.closesNextDay)
                    exception.closeMinutes <= exception.openMinutes
                else exception.closeMinutes > exception.openMinutes))

class LocalOwnerMockRepository(private val store: MockOwnerStateStore) : OwnerMockRepository {
    private val lock = Any()
    private val current = MutableStateFlow<MockOwnerLoadState>(MockOwnerLoadState.Loading)
    override val state: StateFlow<MockOwnerLoadState> = current.asStateFlow()
    init { retryLoad() }

    override fun retryLoad() = synchronized(lock) {
        current.value = MockOwnerLoadState.Loading
        current.value = try {
            (store.read() ?: MockOwnerSnapshot()).asLoadState()
        } catch (e: Exception) {
            MockOwnerLoadState.Error(e.message ?: "Mock 저장소를 읽지 못했습니다.")
        }
    }

    private fun snapshot(): MockOwnerSnapshot = when (val value = current.value) {
        is MockOwnerLoadState.Ready -> value.snapshot
        is MockOwnerLoadState.Empty -> value.snapshot
        is MockOwnerLoadState.Error -> error("Mock 저장소 오류: ${value.message}. retryLoad 먼저 호출")
        MockOwnerLoadState.Loading -> error("Mock 저장소 로딩 중")
    }

    private fun <R> change(transform: (MockOwnerSnapshot) -> Pair<MockOwnerSnapshot, R>): R =
        synchronized(lock) {
            val (next, result) = transform(snapshot())
            store.write(next) // If this throws, don't display unpersisted state.
            current.value = next.asLoadState()
            result
        }

    /** Debug/demo only; public bar search API has not been connected. */
    override fun seedExistingCandidateForFixture(bar: MockBar) {
        require(bar.barId.isNotBlank() && bar.name.isNotBlank() && bar.address.isNotBlank())
        change { s ->
            require(s.bars.none { it.barId == bar.barId })
            s.copy(existingBarCandidates = s.existingBarCandidates.filterNot { it.barId == bar.barId } + bar) to Unit
        }
    }

    override fun saveRegistrationDraft(draft: MockRegistrationDraft?) {
        change { s -> s.copy(registrationDraft = draft) to Unit }
    }

    /** Simulates submission only; no business validation or real operator approval. */
    override fun submitRegistrationDraftForFixture(): String = change { s ->
        val draft = requireNotNull(s.registrationDraft) { "No registration draft" }
        val existingBar = if (draft.kind == MockApplicationKind.EXISTING_BAR) {
            requireNotNull((s.bars + s.existingBarCandidates).firstOrNull { it.barId == draft.existingBarId }) {
                "Existing bar must be selected for a claim"
            }
        } else {
            require(draft.proposedBarName.isNotBlank()) { "New bar name is required" }
            require(draft.proposedBarAddress.isNotBlank()) { "New bar address is required" }
            val addressLength=listOf(draft.proposedBarAddress,draft.proposedBarAddressDetail)
                .filter{it.isNotBlank()}.joinToString(" ").trim().length
            require(addressLength in 1..500) { "New bar address must have 1..500 characters" }
            null
        }
        val normalizedBusinessNumber = draft.businessNumberDigits.filter(Char::isDigit)
        require(s.applications.none {
            it.status == MockApplicationStatus.PENDING &&
                (if (draft.kind == MockApplicationKind.EXISTING_BAR)
                    it.kind == MockApplicationKind.EXISTING_BAR && it.barId == draft.existingBarId
                else it.kind == MockApplicationKind.NEW_BAR &&
                    normalizedBusinessNumber.isNotEmpty() &&
                    it.businessNumberDigits?.filter(Char::isDigit) == normalizedBusinessNumber)
        }) { "Already have a pending application for this bar or business number" }
        // External test fixtures may already use local-application-N IDs. Reserve an
        // unused ID instead of trusting nextLocalId from a pre-seeded snapshot.
        var generatedId = s.nextLocalId
        while (s.applications.any { it.applicationId == "local-application-$generatedId" }) {
            generatedId++
        }
        val id = "local-application-$generatedId"
        val application = MockOwnerApplication(
            applicationId = id, kind = draft.kind,
            status = MockApplicationStatus.PENDING,
            // A claim references the selected bar; no proposedBar name is required by API 3.11.2.
            proposedBarName = existingBar?.name ?: draft.proposedBarName,
            barId = existingBar?.barId,
            proposedBarAddress = if (existingBar == null)
                listOf(draft.proposedBarAddress, draft.proposedBarAddressDetail).filter { it.isNotBlank() }
                    .joinToString(" ").trim() else null,
            representativeName = draft.representativeName.ifBlank { null },
            businessNumberDigits = draft.businessNumberDigits.filter(Char::isDigit).ifBlank { null },
            openingDateIso = draft.openingDateIso.ifBlank { null },
            contactPhone = draft.contactPhone.ifBlank { null },
            storePhone = draft.storePhone.ifBlank { null },
            registrationPhotos = listOfNotNull(draft.certificatePhoto) + draft.applicantGallery + draft.initialMenuPhotos,
        )
        s.copy(
            applications = s.applications + application,
            registrationDraft = null,
            nextLocalId = generatedId + 1,
        ) to id
    }

    override fun registerApplication(application: MockOwnerApplication) {
        require(application.status == MockApplicationStatus.PENDING)
        change { s ->
            require(s.applications.none { it.applicationId == application.applicationId })
            s.copy(applications = s.applications + application) to Unit
        }
    }

    /**
     * TEST FIXTURE ONLY. Actual owner approval belongs to an operator API, NOT to Owner UI.
     * Do not bind this method to any owner approval button.
     */
    override fun approveForFixture(applicationId: String, bar: MockBar) {
        change { s ->
            val a = s.applications.firstOrNull { it.applicationId == applicationId }
                ?: error("Unknown mock application")
            require(a.status == MockApplicationStatus.PENDING)
            if (a.kind == MockApplicationKind.NEW_BAR) {
                require(s.bars.none { it.barId == bar.barId })
            } else {
                require((s.bars + s.existingBarCandidates).any { it.barId == bar.barId } &&
                    a.barId == bar.barId) { "Existing bar ID does not match claim" }
            }
            val approved = s.applications.map {
                if (it.applicationId == applicationId)
                    it.copy(status = MockApplicationStatus.APPROVED, barId = bar.barId) else it
            }
            s.copy(
                applications = approved,
                bars = if (s.bars.none { it.barId == bar.barId }) s.bars + bar else s.bars,
                existingBarCandidates = s.existingBarCandidates.filterNot { it.barId == bar.barId },
                selectedBarId = bar.barId,
            ) to Unit
        }
    }

    override fun closeApplicationForFixture(applicationId: String, status: MockApplicationStatus) {
        require(status in listOf(MockApplicationStatus.REJECTED, MockApplicationStatus.CANCELED))
        change { s ->
            require(s.applications.any { it.applicationId == applicationId &&
                it.status == MockApplicationStatus.PENDING })
            s.copy(applications = s.applications.map {
                if (it.applicationId == applicationId) it.copy(status = status,
                    rejectionReason = if (status == MockApplicationStatus.REJECTED)
                        "Mock 운영팀: 매장 정보를 다시 확인해 주세요." else it.rejectionReason) else it
            }) to Unit
        }
    }

    /** Hides a rejected card in this device's Mock list without deleting audit history. */
    override fun dismissRejectedForFixture(applicationId: String) {
        change { s ->
            require(s.applications.any { it.applicationId == applicationId &&
                it.status == MockApplicationStatus.REJECTED })
            s.copy(dismissedApplicationIds = s.dismissedApplicationIds + applicationId) to Unit
        }
    }

    override fun saveBar(bar: MockBar) {
        require(bar.barId.isNotBlank() && bar.name.isNotBlank())
        // Validate and persist the same normalized value (current API spec §3.5).
        val normalizedAddress = bar.address.trim()
        require(normalizedAddress.length in 1..500) { "Bar address must be 1..500 characters" }
        require(bar.tags.size <= 5 && bar.tags.distinct().size == bar.tags.size)
        require(bar.defaultPourMl == null || bar.defaultPourMl > 0)
        require((bar.latitude == null) == (bar.longitude == null))
        require(bar.latitude == null || (bar.latitude in -90.0..90.0 &&
            bar.longitude != null && bar.longitude in -180.0..180.0))
        require(bar.weeklyHours.map { it.isoDayOfWeek }.distinct().size == bar.weeklyHours.size)
        require(bar.weeklyHours.all {
            it.isoDayOfWeek in 1..7 &&
                (it.closed || (it.openMinutes != null && it.openMinutes in 0..1439 &&
                    it.closeMinutes != null && it.closeMinutes in 0..1439))
        })
        require(bar.exceptions.all(::validMockOperatingException)) {
            "Invalid local operating exception dates or times"
        }
        change { s ->
            require(s.bars.any { it.barId == bar.barId }) { "Unknown bar; use approved fixture for new bar" }
            s.copy(bars = s.bars.map {
                if (it.barId == bar.barId) bar.copy(address = normalizedAddress) else it
            }) to Unit
        }
    }

    /** Quick actions are saved atomically into the same persisted owner snapshot. */
    override fun confirmMenuInformation(barId: String, confirmedAtEpochMs: Long) {
        require(confirmedAtEpochMs >= 0L)
        change { s ->
            require(s.bars.any { it.barId == barId })
            require(s.menuItems.any { it.barId == barId }) {
                "게시된 메뉴가 있어야 판매 정보를 확인할 수 있어요."
            }
            s.copy(bars = s.bars.map { bar ->
                if (bar.barId == barId) bar.copy(lastVerifiedAtEpochMs = confirmedAtEpochMs)
                else bar
            }) to Unit
        }
    }

    override fun applyOperatingException(barId: String, exception: MockOperatingException) {
        require(validMockOperatingException(exception))
        require(exception.exceptionId.isNotBlank())
        change { s ->
            require(s.bars.any { it.barId == barId })
            s.copy(bars = s.bars.map { bar ->
                if (bar.barId != barId) bar else bar.copy(
                    // The management-home quick action is one current selection, not
                    // a stack of hidden states to restore after the user presses X.
                    // Retain non-quick schedules even when dates overlap:
                    // the newer quick override wins by list order and cancelling it
                    // restores the untouched underlying schedule.
                    exceptions = bar.exceptions.filterNot {
                        it.exceptionId == exception.exceptionId ||
                            (exception.exceptionId.startsWith("quick-") &&
                                it.exceptionId.startsWith("quick-"))
                    } + exception
                )
            }) to Unit
        }
    }

    override fun cancelOperatingException(barId: String, exceptionId: String) {
        change { s ->
            require(s.bars.any { it.barId == barId })
            require(s.bars.first { it.barId == barId }.exceptions.any {
                it.exceptionId == exceptionId
            })
            s.copy(bars = s.bars.map { bar ->
                if (bar.barId == barId) bar.copy(exceptions = bar.exceptions.filterNot {
                    it.exceptionId == exceptionId ||
                        (exceptionId.startsWith("quick-") && it.exceptionId.startsWith("quick-"))
                }) else bar
            }) to Unit
        }
    }

    override fun selectBar(barId: String) {
        change { s ->
            require(s.bars.any { it.barId == barId })
            s.copy(selectedBarId = barId) to Unit
        }
    }

    override fun saveBrand(brand: MockBrand) {
        require(brand.brandId.isNotBlank() && brand.name.isNotBlank())
        change { s ->
            s.copy(brands = s.brands.filterNot { it.brandId == brand.brandId } + brand) to Unit
        }
    }

    override fun saveCatalogProduct(product: MockCatalogProduct) {
        require(product.productId.isNotBlank() && product.displayName.isNotBlank())
        change { s ->
            require(s.brands.any { it.brandId == product.brandId }) { "Unknown brand ID" }
            s.copy(products = s.products.filterNot { it.productId == product.productId } + product) to Unit
        }
    }

    private fun menuHistoryKey(barId: String, productId: String) = "$barId|$productId"

    private fun retainedMenuId(s: MockOwnerSnapshot, item: MockBarMenuItem): MockBarMenuItem {
        val originalId = s.menuItemIdHistory[menuHistoryKey(item.barId, item.productId)]
        val alreadyPublished = s.menuItems.any {
            it.barId == item.barId && it.productId == item.productId
        }
        return if (!alreadyPublished && originalId != null)
            item.copy(barMenuItemId = originalId) else item
    }

    private fun retainMenuOrder(rows: List<MockBarMenuItem>, item: MockBarMenuItem) =
        if (rows.any { it.barMenuItemId == item.barMenuItemId })
            rows.map { if (it.barMenuItemId == item.barMenuItemId) item else it }
        else rows + item

    override fun saveMenuItem(item: MockBarMenuItem) {
        require(item.barMenuItemId.isNotBlank())
        require(item.options.isNotEmpty())
        require(item.options.all { it.optionId.isNotBlank() }) { "Serving option ID must not be blank" }
        require(item.options.distinctBy { it.identityKey() }.size == item.options.size) { "Duplicate serving option" }
        require(item.options.map { it.optionId }.distinct().size == item.options.size)
        require(item.options.all(::validMockMenuOption))
        change { s ->
            require(s.bars.any { it.barId == item.barId })
            require(s.products.any { it.productId == item.productId }) { "Unknown catalog product" }
            require(s.menuItems.none {
                it.barId == item.barId && it.productId == item.productId &&
                    it.barMenuItemId != item.barMenuItemId
            }) { "Same canonical product already in bar menu; add a serving option" }
            require(s.menuItems.none { existing ->
                existing.barMenuItemId != item.barMenuItemId &&
                    existing.options.any { option -> item.options.any { it.optionId == option.optionId } }
            }) { "Serving option ID is already used in another menu row" }
            require(s.menuItems.none { it.barMenuItemId == item.barMenuItemId &&
                (it.barId != item.barId || it.productId != item.productId) })
            val saved = retainedMenuId(s, item)
            require(s.menuItems.none { it.barMenuItemId == saved.barMenuItemId &&
                (it.barId != saved.barId || it.productId != saved.productId) })
            s.copy(menuItems = retainMenuOrder(s.menuItems, saved),
                menuItemIdHistory = s.menuItemIdHistory +
                    (menuHistoryKey(saved.barId, saved.productId) to saved.barMenuItemId)) to Unit
        }
    }

    override fun saveManualMenuItem(
        item: MockBarMenuItem, newProduct: MockCatalogProduct?, newBrand: MockBrand?,
    ) {
        require(item.barMenuItemId.isNotBlank() && item.productId.isNotBlank())
        require(item.options.all { it.optionId.isNotBlank() })
        require(item.options.map { it.optionId }.distinct().size == item.options.size)
        change { state ->
            require(state.bars.any { it.barId == item.barId }) { "Unknown bar" }
            val product = state.products.firstOrNull { it.productId == item.productId }
                ?: requireNotNull(newProduct) { "상품을 먼저 확인해 주세요." }
            require(product.productId == item.productId && product.displayName.isNotBlank())
            // A locally unverified product may be re-categorized in this atomic write.
            // Validate against its replacement rather than its previous stored category.
            val proposedProduct = newProduct ?: product
            require(proposedProduct.productId == item.productId)
            // Photo-imported rows can predate the direct editor's three-option cap.
            // Keep their original overflow untouched when editing the first three.
            val oldRow = state.menuItems.firstOrNull { it.barMenuItemId == item.barMenuItemId }
            val editableLimit = if (manualMenuCategoryLabel(proposedProduct.category) == "위스키")
                MANUAL_MENU_MAX_OPTIONS else 1
            val legacyTail = oldRow?.options?.drop(editableLimit).orEmpty()
            val preservesLegacyTail = oldRow != null && legacyTail.isNotEmpty() &&
                item.options.size == oldRow.options.size &&
                item.options.drop(editableLimit) == legacyTail &&
                item.options.take(editableLimit).all { proposed ->
                    oldRow.options.any { it.optionId == proposed.optionId }
                }
            val directOptions = if (preservesLegacyTail)
                item.options.take(editableLimit) else item.options
            val error = manualMenuOptionError(directOptions, proposedProduct.category,
                oldRow?.options.orEmpty())
            require(error == null) { error ?: "잘못된 가격 옵션" }
            require(item.options.all { it.optionId.isNotBlank() } &&
                item.options.map { it.optionId }.distinct().size == item.options.size &&
                item.options.distinctBy { it.identityKey() }.size == item.options.size &&
                item.options.all(::validMockMenuOption)) { "잘못된 저장 옵션입니다." }
            if (state.products.none { it.productId == product.productId }) {
                require(newBrand != null && newBrand.brandId == product.brandId ||
                    state.brands.any { it.brandId == product.brandId }) { "Unknown brand" }
                require(product.catalogMatched || product.productId.startsWith("local-unverified-")) {
                    "Unmatched product needs an unverified local ID"
                }
            }
            require(state.menuItems.none {
                it.barId == item.barId && it.productId == item.productId &&
                    it.barMenuItemId != item.barMenuItemId
            }) { "이미 등록한 제품이에요. 기존 메뉴에서 용량·가격을 수정해 주세요." }
            require(state.menuItems.none {
                it.barMenuItemId == item.barMenuItemId &&
                    (it.productId != item.productId || it.barId != item.barId)
            }) { "기존 메뉴의 제품 ID는 변경할 수 없어요." }
            require(state.menuItems.none { existing ->
                existing.barMenuItemId != item.barMenuItemId && existing.options.any { other ->
                    item.options.any { it.optionId == other.optionId }
                }
            }) { "판매 옵션 ID 중복" }
            // Canonical catalog records are immutable; local unverified menu products
            // may change their display name/type without changing their stable local ID.
            val finalProduct = if (newProduct != null &&
                state.products.any { it.productId == product.productId }) {
                require(!product.catalogMatched && newProduct.productId == product.productId) {
                    "카탈로그 제품명은 직접 변경할 수 없어요."
                }
                newProduct
            } else product
            val newBrands = if (newBrand != null) {
                val existingBrand = state.brands.firstOrNull { it.brandId == newBrand.brandId }
                require(existingBrand == null || !product.catalogMatched ||
                    existingBrand == newBrand) { "카탈로그 브랜드는 변경할 수 없어요." }
                state.brands.filterNot { it.brandId == newBrand.brandId } + newBrand
            } else state.brands
            val newProducts = state.products.filterNot { it.productId == finalProduct.productId } +
                finalProduct
            val saved = retainedMenuId(state, item)
            require(state.menuItems.none { it.barMenuItemId == saved.barMenuItemId &&
                (it.barId != saved.barId || it.productId != saved.productId) })
            state.copy(
                brands = newBrands, products = newProducts,
                menuItems = retainMenuOrder(state.menuItems, saved),
                menuItemIdHistory = state.menuItemIdHistory +
                    (menuHistoryKey(saved.barId, saved.productId) to saved.barMenuItemId),
                bars = state.bars.map { b ->
                    if (b.barId == item.barId)
                        b.copy(lastMenuPublishedAtEpochMs = System.currentTimeMillis())
                    else b
                },
            ) to Unit
        }
    }

    private fun updatedMenuTimestamp(bars: List<MockBar>, barId: String): List<MockBar> =
        bars.map { bar ->
            if (bar.barId == barId) bar.copy(lastMenuPublishedAtEpochMs = System.currentTimeMillis())
            else bar
        }

    override fun setSoldOut(barMenuItemId: String, value: Boolean) {
        change { s ->
            val row = s.menuItems.firstOrNull { it.barMenuItemId == barMenuItemId }
                ?: error("Unknown menu item")
            if (row.soldOut == value) s to Unit else s.copy(
                menuItems = s.menuItems.map {
                    if (it.barMenuItemId == barMenuItemId) it.copy(soldOut = value) else it
                }, bars = updatedMenuTimestamp(s.bars, row.barId)
            ) to Unit
        }
    }

    override fun deleteMenuItem(barMenuItemId: String) {
        change { s ->
            val row = s.menuItems.firstOrNull { it.barMenuItemId == barMenuItemId }
                ?: error("Unknown menu item")
            s.copy(
                menuItems = s.menuItems.filterNot { it.barMenuItemId == barMenuItemId },
                menuItemIdHistory = s.menuItemIdHistory +
                    (menuHistoryKey(row.barId, row.productId) to row.barMenuItemId),
                bars = updatedMenuTimestamp(s.bars, row.barId)
            ) to Unit
        }
    }

    override fun clearMenuForBar(barId: String) {
        change { s ->
            require(s.bars.any { it.barId == barId })
            val remaining = s.menuItems.filterNot { it.barId == barId }
            if (remaining.size == s.menuItems.size) s to Unit else s.copy(
                menuItems = remaining,
                menuItemIdHistory = s.menuItemIdHistory + s.menuItems
                    .filter { it.barId == barId }.associate {
                        menuHistoryKey(it.barId, it.productId) to it.barMenuItemId
                    },
                bars = updatedMenuTimestamp(s.bars, barId)
            ) to Unit
        }
    }

    override fun startPhotoImport(
        barId: String, selectedUris: List<String>, fixture: MockPhotoExtractionSource,
    ): String {
        require(selectedUris.isNotEmpty() && selectedUris.all { it.isNotBlank() })
        require(selectedUris.distinct().size == selectedUris.size)
        return change { s ->
            require(s.bars.any { it.barId == barId })
            require(s.imports.none { it.barId == barId &&
                it.status in listOf(MockImportStatus.PROCESSING, MockImportStatus.READY_FOR_REVIEW) })
            // Fixture/restored snapshots may contain imports without advancing the local
            // sequence. Reserve a unique job ID before creating any image/line IDs.
            var reserved = s.nextLocalId
            while (s.imports.any { it.menuImportId == "local-import-$reserved" }) {
                reserved++
            }
            val id = "local-import-$reserved"
            // Each selected image gets its OWN extraction lines and candidate IDs.
            var sequence = reserved + 1
            val images = selectedUris.mapIndexed { index, uri ->
                val sourceLines = fixture.linesFor(uri)
                val lines = sourceLines.map { line ->
                    val newLineId = "local-line-${sequence++}"
                    line.copy(
                        extractedItemId = newLineId,
                        decision = null,
                        options = line.options.map { it.copy(optionId = "local-option-${sequence++}") },
                    )
                }
                MockPhotoExtraction("local-image-${sequence++}", uri, index + 1, lines)
            }
            val job = MockMenuImport(id, barId, MockImportStatus.READY_FOR_REVIEW, 1, images)
            s.copy(imports = s.imports + job, nextLocalId = sequence) to id
        }
    }

    override fun decideLine(
        importId: String, extractedItemId: String, expectedVersion: Int, decision: MockReviewDecision,
    ) {
        change { s ->
            val job = s.imports.firstOrNull { it.menuImportId == importId } ?: error("Unknown import")
            require(job.status == MockImportStatus.READY_FOR_REVIEW)
            require(job.reviewVersion == expectedVersion) { "REVIEW_OUTDATED" }
            require(job.images.any { image -> image.lines.any { it.extractedItemId == extractedItemId } })
            if (decision.kind == MockDecisionKind.SELECT_PRODUCT) {
                require(decision.productId != null && s.products.any { it.productId == decision.productId })
                require(decision.correctedOptions == null ||
                    (decision.correctedOptions.isNotEmpty() &&
                        decision.correctedOptions.map { it.identityKey() }.distinct().size == decision.correctedOptions.size &&
                        decision.correctedOptions.all(::validMockMenuOption)))
            } else require(decision.productId == null && decision.correctedOptions == null)
            val updated = job.copy(images = job.images.map { image ->
                image.copy(lines = image.lines.map { line ->
                    if (line.extractedItemId == extractedItemId) line.copy(decision = decision) else line
                })
            })
            s.copy(imports = s.imports.map { if (it.menuImportId == importId) updated else it }) to Unit
        }
    }

    /** Only new canonical products are added. Existing menu options and prices are untouched. */
    override fun publishAddOnly(importId: String, expectedVersion: Int): Int = change { s ->
        val job = s.imports.firstOrNull { it.menuImportId == importId } ?: error("Unknown import")
        require(job.status == MockImportStatus.READY_FOR_REVIEW)
        require(job.reviewVersion == expectedVersion) { "REVIEW_OUTDATED" }
        val allLines = job.images.flatMap { it.lines }
        require(allLines.all { it.decision != null }) { "Review required for every extracted line" }
        val grouped = allLines.filter { it.decision?.kind == MockDecisionKind.SELECT_PRODUCT }
            .groupBy { requireNotNull(it.decision?.productId) }
        var index = s.nextLocalId
        // Manual entries may use local-* IDs without advancing the import counter.
        // Reserve against all existing IDs AND those already generated in this publish.
        val usedMenuIds = s.menuItems.mapTo(mutableSetOf()) { it.barMenuItemId }
        val usedOptionIds = s.menuItems.flatMapTo(mutableSetOf()) { item ->
            item.options.map { it.optionId }
        }
        fun reserveUnusedLocalId(prefix: String, taken: MutableSet<String>): String {
            var candidate: String
            do {
                candidate = "$prefix${index++}"
            } while (!taken.add(candidate))
            return candidate
        }
        val added = grouped.mapNotNull { (productId, lines) ->
            if (s.menuItems.any { it.barId == job.barId && it.productId == productId }) return@mapNotNull null
            val options = lines.flatMap { it.decision?.correctedOptions ?: it.options }
            require(options.isNotEmpty()) { "Product needs at least one priced option" }
            require(options.all(::validMockMenuOption)) { "Invalid serving price or discount" }
            val byKey = options.groupBy { it.identityKey() }
            // Same serving + list price can still have incompatible discounts. Never
            // choose the first photo silently; the owner must resolve these terms.
            require(byKey.values.all { opts ->
                opts.map { it.priceKrw to it.discount }.distinct().size == 1
            }) {
                "Conflicting extracted price or discount for same serving option; review before publish"
            }
            val previousId = s.menuItemIdHistory[menuHistoryKey(job.barId, productId)]
            if (previousId != null) require(usedMenuIds.add(previousId)) {
                "Previously assigned menu ID conflicts with an active menu row"
            }
            MockBarMenuItem(
                barMenuItemId = previousId ?: reserveUnusedLocalId("local-menu-", usedMenuIds),
                barId = job.barId,
                productId = productId,
                options = byKey.values.map { opts ->
                    opts.first().copy(optionId = reserveUnusedLocalId("local-serving-", usedOptionIds))
                },
            )
        }
        val applied = job.copy(status = MockImportStatus.APPLIED)
        s.copy(
            menuItems = s.menuItems + added,
            menuItemIdHistory = s.menuItemIdHistory + added.associate {
                menuHistoryKey(it.barId, it.productId) to it.barMenuItemId
            },
            imports = s.imports.map { if (it.menuImportId == importId) applied else it },
            bars = s.bars.map { bar ->
                if (bar.barId == job.barId) bar.copy(
                    lastMenuPublishedAtEpochMs = System.currentTimeMillis()
                ) else bar
            },
            nextLocalId = index,
        ) to added.size
    }

    override fun preview(barId: String, nowEpochMs: Long): MockPreview? = synchronized(lock) {
        val s = snapshot()
        val bar = s.bars.firstOrNull { it.barId == barId } ?: return@synchronized null
        val visible = s.menuItems.filter { it.barId == barId && !it.soldOut }
        MockPreview(bar, visible, s.products.filter { p -> visible.any { it.productId == p.productId } }, nowEpochMs)
    }
}

/** Explicit fixtures: initial installation is always Empty, not a fabricated registered bar. */
object OwnerMockFixtures {
    fun empty() = MockOwnerSnapshot()
    fun registeredBar(): MockOwnerSnapshot {
        val bar = MockBar(barId = "fixture-bar", name = "테스트 매장", address = "테스트 주소")
        return MockOwnerSnapshot(bars = listOf(bar), selectedBarId = bar.barId)
    }
    fun imageFixtures(byUri: Map<String, List<MockExtractedLine>>): MockPhotoExtractionSource =
        MockPhotoExtractionSource { uri -> byUri[uri].orEmpty() }
}
