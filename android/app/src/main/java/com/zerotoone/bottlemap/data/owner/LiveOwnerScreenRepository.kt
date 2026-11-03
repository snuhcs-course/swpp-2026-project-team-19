package com.zerotoone.bottlemap.data.owner

import android.content.Context
import android.net.Uri
import com.zerotoone.bottlemap.data.ImageUploadPreparer
import com.zerotoone.bottlemap.data.AppAuth
import com.zerotoone.bottlemap.data.OwnerRepository
import com.zerotoone.bottlemap.network.BarMenuResponseDto
import com.zerotoone.bottlemap.network.OwnedBarDto
import com.zerotoone.bottlemap.network.OwnerApplicationDto
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneOffset
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * Thin production adapter: existing Owner Compose screens keep their current models,
 * but owner identity, published menus and mutations come from the live server.
 * Never persist fetched personal or owner data into local Mock preferences.
 */
class LiveOwnerScreenRepository(context: Context) : OwnerMockRepository {
    private val app = context.applicationContext
    private val local = LocalOwnerMockRepository(InMemoryMockOwnerStateStore())
    private var pendingApplicationId: String? = null
    private val remote = OwnerRepository()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val writeMutex = Mutex()
    private val generation = AtomicInteger(0)
    private val versionByBar = mutableMapOf<String, Int?>()
    @Volatile private var lastReadySnapshot = MockOwnerSnapshot()

    private fun publishSnapshot(value: MockOwnerSnapshot) {
        lastReadySnapshot = value
        local.replaceFromBackend(value)
    }
    override val state = local.state

    init { retryLoad() }

    private fun snapshot(): MockOwnerSnapshot = when (val s = state.value) {
        is MockOwnerLoadState.Ready -> s.snapshot
        is MockOwnerLoadState.Empty -> s.snapshot
        else -> lastReadySnapshot
    }
    private fun timestamp(s: String?): Long? = s?.let {
        runCatching { Instant.parse(it).toEpochMilli() }.getOrNull()
    }
    private fun minutes(s: String?): Int? = s?.let {
        runCatching { LocalTime.parse(it).toSecondOfDay() / 60 }.getOrNull()
    }
    private fun time(value: Int?): String? =
        value?.let { "%02d:%02d".format(it / 60, it % 60) }
    private fun epochDay(value: String): Long = LocalDate.parse(value).toEpochDay()
    private fun date(value: Long): String = LocalDate.ofEpochDay(value).toString()

    private fun toBar(bar: OwnedBarDto): MockBar = MockBar(
        barId = bar.barId, name = bar.name, address = bar.address, phone = bar.phone,
        latitude = bar.latitude, longitude = bar.longitude,
        description = bar.description, tags = bar.tags,
        defaultPourMl = bar.defaultPourMl ?: 30,
        gallery = bar.photos.map {
            MockPhoto(it.photoId, it.imageUrl, MockPhotoKind.BAR_GALLERY)
        },
        weeklyHours = bar.weeklyHours.map {
            MockWeeklyHours(
                isoDayOfWeek = it.dayOfWeek, closed = it.closed,
                openMinutes = minutes(it.openTime), closeMinutes = minutes(it.closeTime),
                closesNextDay = !it.closed && minutes(it.closeTime) != null &&
                    minutes(it.openTime) != null && minutes(it.closeTime)!! < minutes(it.openTime)!!,
            )
        },
        exceptions = listOfNotNull(bar.operatingException?.let { exception ->
            MockOperatingException(
                exceptionId = "server-exception-${bar.barId}",
                kind = when (exception.kind) {
                    "closed_today" -> MockExceptionKind.CLOSED_TODAY
                    "vacation" -> MockExceptionKind.VACATION
                    else -> MockExceptionKind.CUSTOM_HOURS
                },
                fromEpochDay = epochDay(exception.startDate),
                toEpochDay = epochDay(exception.endDate),
                openMinutes = minutes(exception.openTime), closeMinutes = minutes(exception.closeTime),
                note = exception.note,
            )
        }),
        lastVerifiedAtEpochMs = timestamp(bar.currentMenu?.confirmedAt),
        lastMenuPublishedAtEpochMs = timestamp(bar.currentMenu?.publishedAt),
    )

    private fun toApplication(app: OwnerApplicationDto) = MockOwnerApplication(
        applicationId = app.applicationId,
        kind = if(app.applicationType == "new_bar") MockApplicationKind.NEW_BAR
            else MockApplicationKind.EXISTING_BAR,
        status = when (app.status) {
            "approved" -> MockApplicationStatus.APPROVED
            "rejected" -> MockApplicationStatus.REJECTED
            "canceled" -> MockApplicationStatus.CANCELED
            else -> MockApplicationStatus.PENDING
        },
        proposedBarName = app.proposedBar?.name ?: app.bar?.name.orEmpty(),
        barId = app.bar?.barId,
        proposedBarAddress = app.proposedBar?.address,
        rejectionReason = app.rejectionReason,
        submittedAtEpochMs = timestamp(app.createdAt) ?: 0L,
        reviewedAtEpochMs = timestamp(app.reviewedAt),
    )

    private fun menuRows(barId: String, menu: BarMenuResponseDto): List<MockBarMenuItem> =
        menu.items.map { entry ->
            MockBarMenuItem(
                barMenuItemId = entry.barMenuItemId, barId = barId,
                productId = entry.productId, soldOut = entry.soldOut,
                displayNameOverride = entry.displayName,
                options = entry.options.map { option ->
                    MockMenuOption(
                        optionId = option.menuEntryOptionId,
                        label = option.optionLabel, pourMl = option.pourMl,
                        priceKrw = option.priceKrw,
                        discount = option.discount?.let { discount ->
                            val start = timestamp(discount.startsAt)
                            val end = timestamp(discount.endsAt)
                            if(start != null && end != null)
                                MockDiscount(discount.discountedPriceKrw, start, end)
                            else null
                        },
                    )
                },
            )
        }

    private suspend fun refresh() {
        val token = AppAuth.gateway.currentAccessTokenOrNull()
        if(token == null) {
            versionByBar.clear()
            publishSnapshot(MockOwnerSnapshot())
            return
        }
        val old = snapshot()
        val bars = remote.getOwnedBars()
        val applications = remote.getMyApplications()
        val menus = bars.associate { bar ->
            bar.barId to remote.getOwnedMenu(bar.barId)
        }
        versionByBar.clear()
        menus.forEach { (id, menu) -> versionByBar[id] = menu.menuVersion }
        val rows = menus.flatMap { (id, menu) -> menuRows(id, menu) }
        val brands = menus.values.flatMap { it.items }.mapNotNull { item ->
            item.brandId?.let { MockBrand(it, item.brandName ?: item.displayName) }
        }.distinctBy { it.brandId }
        val products = menus.values.flatMap { it.items }.map { item ->
            MockCatalogProduct(
                productId = item.productId,
                brandId = item.brandId ?: "",
                displayName = item.productName ?: item.displayName,
                category = item.category,
            )
        }.distinctBy { it.productId }
        val mappedBars = bars.map(::toBar)
        val selected = old.selectedBarId?.takeIf { id -> mappedBars.any { it.barId == id } }
            ?: mappedBars.firstOrNull()?.barId
        publishSnapshot(old.copy(
            bars = mappedBars, applications = applications.map(::toApplication),
            menuItems = rows, brands = brands, products = products,
            selectedBarId = selected,
        ))
    }

    override fun retryLoad() {
        lastReadySnapshot = snapshot()
        val requested = generation.incrementAndGet()
        local.serverLoading()
        scope.launch {
            try {
                if(requested == generation.get()) refresh()
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if(requested == generation.get())
                    local.serverError(error.message ?: "매장 정보를 가져오지 못했어요.")
            }
        }
    }

    /** Apply on server before replacing the menu model. Retrying after failure reloads its version. */
    private fun write(op: suspend () -> Unit) {
        scope.launch {
            writeMutex.withLock {
                try {
                    op()
                    refresh()
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (error: Exception) {
                    runCatching { refresh() }
                    local.serverError(error.message ?: "저장하지 못했어요. 다시 시도해 주세요.")
                }
            }
        }
    }

    override fun selectBar(barId: String) = local.selectBar(barId)

    /** Server limits gallery to a 2048 px JPEG under 2 MB, not menu's 10 MB. */
    private suspend fun prepareGalleryPhoto(uri: String):
        com.zerotoone.bottlemap.data.PreparedMenuImage {
        val prepared = ImageUploadPreparer(app.contentResolver).prepare(Uri.parse(uri))
        val decoded = android.graphics.BitmapFactory.decodeByteArray(
            prepared.bytes, 0, prepared.bytes.size)
            ?: error("매장 사진을 읽을 수 없어요.")
        val maxEdge = maxOf(decoded.width, decoded.height)
        val finalBitmap = if(maxEdge > 2048) {
            val ratio = 2048f / maxEdge
            android.graphics.Bitmap.createScaledBitmap(decoded,
                maxOf(1,(decoded.width * ratio).toInt()),
                maxOf(1,(decoded.height * ratio).toInt()), true)
        } else decoded
        try {
            for(quality in listOf(85, 75, 65, 55, 45)) {
                val output = java.io.ByteArrayOutputStream()
                if(finalBitmap.compress(android.graphics.Bitmap.CompressFormat.JPEG,
                    quality, output)) {
                    val result = output.toByteArray()
                    if(result.size in 1..(2*1024*1024)) {
                        return com.zerotoone.bottlemap.data.PreparedMenuImage(
                            filename = "owner-bar-photo.jpg", mimeType = "image/jpeg", bytes = result)
                    }
                }
            }
        } finally {
            if(finalBitmap !== decoded) finalBitmap.recycle()
            decoded.recycle()
        }
        error("매장 사진을 2MB 이하로 압축하지 못했어요.")
    }

    private suspend fun syncGallery(barId: String, old: List<MockPhoto>, now: List<MockPhoto>) {
        val oldIds = old.map { it.photoId }.toSet()
        val newIds = now.map { it.photoId }.toSet()
        for(photo in old) {
            if(photo.photoId !in newIds) remote.deleteBarPhoto(barId, photo.photoId)
        }
        val mappedIds = mutableMapOf<String, String>()
        for(photo in now) {
            if(photo.photoId in oldIds) mappedIds[photo.photoId] = photo.photoId
            else {
                val result = remote.addBarPhoto(barId, prepareGalleryPhoto(photo.uri))
                mappedIds[photo.photoId] = result.photos.lastOrNull()?.photoId
                    ?: error("업로드한 사진의 ID를 확인하지 못했어요.")
            }
        }
        remote.reorderBarPhotos(barId, now.map { mappedIds.getValue(it.photoId) })
    }

    override fun saveBar(bar: MockBar) {
        val old = snapshot().bars.firstOrNull { it.barId == bar.barId }
            ?: error("매장 정보를 먼저 불러와 주세요.")
        local.saveBar(bar)
        val changes = mutableMapOf<String, Any?>()
        if(old.name != bar.name) changes["name"] = bar.name
        if(old.address != bar.address) {
            changes["address"] = bar.address
            changes["latitude"] = bar.latitude ?: old.latitude
            changes["longitude"] = bar.longitude ?: old.longitude
        }
        if(old.phone != bar.phone) changes["phone"] = bar.phone
        if(old.description != bar.description) changes["description"] = bar.description
        if(old.defaultPourMl != bar.defaultPourMl) changes["defaultPourMl"] = bar.defaultPourMl
        if(old.tags != bar.tags) changes["tags"] = bar.tags
        if(old.weeklyHours != bar.weeklyHours) changes["weeklyHours"] =
            bar.weeklyHours.map {
                mapOf("dayOfWeek" to it.isoDayOfWeek, "closed" to it.closed,
                    "openTime" to time(it.openMinutes), "closeTime" to time(it.closeMinutes))
            }
        if(changes.isNotEmpty() || old.gallery != bar.gallery) write {
            if(changes.isNotEmpty()) remote.updateBar(bar.barId, changes)
            if(old.gallery != bar.gallery) syncGallery(bar.barId, old.gallery, bar.gallery)
        }
    }

    override fun saveManualMenuItem(
        item: MockBarMenuItem, newProduct: MockCatalogProduct?, newBrand: MockBrand?,
    ) {
        val before = snapshot()
        val old = before.menuItems.firstOrNull { it.barMenuItemId == item.barMenuItemId }
        local.saveManualMenuItem(item, newProduct, newBrand)
        val optionBodies = item.options.map { option ->
            mapOf(
                "optionLabel" to option.label, "pourMl" to option.pourMl,
                "priceKrw" to option.priceKrw,
                "discount" to option.discount?.let {
                    mapOf("discountedPriceKrw" to it.discountedPriceKrw,
                        "startsAt" to Instant.ofEpochMilli(it.startAtEpochMs).toString(),
                        "endsAt" to Instant.ofEpochMilli(it.endAtEpochMs).toString())
                },
            )
        }
        write {
            val version = versionByBar[item.barId]
            val display = item.displayNameOverride
                ?: (newProduct ?: before.products.firstOrNull { it.productId == item.productId })?.displayName
                ?: error("메뉴 이름이 없어요.")
            if(old != null) {
                remote.updateMenuItem(item.barId, item.barMenuItemId,
                    mapOf("menuVersion" to version, "displayName" to display,
                        "options" to optionBodies))
            } else {
                val body = mutableMapOf<String, Any?>(
                    "menuVersion" to version, "displayName" to display,
                    "options" to optionBodies,
                )
                if(newProduct == null) {
                    body["productId"] = item.productId
                } else {
                    val brand = if(newBrand != null)
                        mapOf("type" to "new", "canonicalName" to newBrand.name, "aliases" to emptyList<Any>())
                    else mapOf("type" to "existing", "brandId" to newProduct.brandId)
                    body["newProduct"] = mapOf(
                        "brand" to brand,
                        "product" to mapOf(
                            "category" to newProduct.category,
                            "displayName" to newProduct.displayName,
                            "ageYears" to newProduct.ageYears,
                            "editionName" to newProduct.editionName,
                            "abv" to newProduct.abvPercent,
                        ),
                        "aliases" to emptyList<Any>(),
                    )
                }
                remote.addMenuItem(item.barId, body)
            }
        }
    }

    override fun saveMenuItem(item: MockBarMenuItem) = saveManualMenuItem(item, null, null)

    override fun setSoldOut(barMenuItemId: String, value: Boolean) {
        val row = snapshot().menuItems.firstOrNull { it.barMenuItemId == barMenuItemId }
            ?: error("메뉴가 없어요.")
        write { remote.setSoldOut(row.barId, barMenuItemId, value) }
    }

    override fun deleteMenuItem(barMenuItemId: String) {
        val row = snapshot().menuItems.firstOrNull { it.barMenuItemId == barMenuItemId }
            ?: error("메뉴가 없어요.")
        write {
            remote.deleteMenuItem(row.barId, barMenuItemId,
                versionByBar[row.barId] ?: error("메뉴 버전을 불러와 주세요."))
        }
    }

    override fun clearMenuForBar(barId: String) {
        write { remote.resetMenu(barId, versionByBar[barId]) }
    }

    override fun confirmMenuInformation(barId: String, confirmedAtEpochMs: Long) {
        write { remote.confirmMenu(barId, versionByBar[barId]) }
    }

    /** Called asynchronously by the existing registration form; never show success before HTTP 201 + photo PUT. */
    suspend fun submitRegistrationDraftLive() {
        val draft = snapshot().registrationDraft
            ?: error("등록 신청 정보를 먼저 입력해 주세요.")
        val body = mutableMapOf<String, Any?>(
            "applicationType" to if(draft.kind == MockApplicationKind.EXISTING_BAR)
                "existing_bar" else "new_bar",
            "businessRegistrationNumber" to draft.businessNumberDigits,
            "representativeName" to draft.representativeName,
            "openingDate" to draft.openingDateIso,
            "contactPhone" to draft.contactPhone,
        )
        if(draft.kind == MockApplicationKind.EXISTING_BAR) {
            body["barId"] = requireNotNull(draft.existingBarId)
        } else {
            body["proposedBar"] = mapOf(
                "name" to draft.proposedBarName,
                "address" to listOf(draft.proposedBarAddress, draft.proposedBarAddressDetail)
                    .filter { it.isNotBlank() }.joinToString(" "),
                "phone" to draft.storePhone.takeIf { it.isNotBlank() },
            )
        }
        // If POST succeeded but the image PUT failed, retry the same pending application.
        val existing = remote.getMyApplications().firstOrNull {
            it.status == "pending" &&
                it.businessRegistrationNumber == draft.businessNumberDigits &&
                it.applicationType == body["applicationType"]
        }
        val applicationId = pendingApplicationId ?: existing?.applicationId
            ?: remote.submitOwnerApplication(body).applicationId
        pendingApplicationId = applicationId
        if(draft.initialMenuPhotos.isNotEmpty()) {
            val preparer = ImageUploadPreparer(app.contentResolver)
            val images = draft.initialMenuPhotos.map { photo ->
                preparer.prepare(Uri.parse(photo.uri))
            }
            remote.uploadApplicationMenuPhotos(applicationId, images)
        }
        pendingApplicationId = null
        local.saveRegistrationDraft(null)
        refresh()
    }

    suspend fun readBusinessCertificateLive(uri: String):
        com.zerotoone.bottlemap.network.OwnerCertificateOcrDto {
        val prepared = ImageUploadPreparer(app.contentResolver).prepare(Uri.parse(uri))
        return remote.readBusinessCertificate(prepared)
    }

    suspend fun searchExistingBarCandidatesLive(query: String) {
        val trimmed=query.trim()
        if(trimmed.length < 2 || trimmed.length > 100) return
        val matches=com.zerotoone.bottlemap.network.ApiClient.call {
            com.zerotoone.bottlemap.network.ApiClient.api.searchBarNames(trimmed, limit=20)
        }
        val before=snapshot()
        publishSnapshot(before.copy(existingBarCandidates=matches.items
            .filter { !it.hasOwner }
            .map {
                MockBar(it.barId,it.name,it.address,
                    latitude=it.latitude, longitude=it.longitude)
            }))
    }

    suspend fun searchCatalogLive(query: String) {
        val trimmed = query.trim()
        if(trimmed.isEmpty() || trimmed.length > 100) return
        val results = remote.searchCatalogProducts(trimmed)
        val before = snapshot()
        publishSnapshot(before.copy(
            products = (before.products + results.map { item ->
                MockCatalogProduct(item.productId, item.brandId, item.displayName,
                    item.category, item.ageYears, item.editionName,
                    abvPercent = item.abv, isActive = item.isActive)
            }).distinctBy { it.productId },
            brands = (before.brands + results.map {
                MockBrand(it.brandId, it.brandName)
            }).distinctBy { it.brandId },
        ))
    }

    /** Uploads actual Stage 7 image bytes before navigation; no local fixture job. */
    suspend fun submitPhotoImportLive(barId: String, photos: List<MockPhoto>): String {
        require(photos.isNotEmpty()) { "메뉴판 사진을 선택해 주세요." }
        val preparer = ImageUploadPreparer(app.contentResolver)
        val images = photos.map { photo -> preparer.prepare(Uri.parse(photo.uri)) }
        val accepted = remote.uploadMenuImport(
            barId = barId,
            images = images,
            // Existing backend supports partial_update; never request full_replace.
            mode = "partial_update",
            idempotencyKey = java.util.UUID.randomUUID().toString(),
        )
        val job = MockMenuImport(
            menuImportId = accepted.menuImportId, barId = barId,
            status = MockImportStatus.PROCESSING, reviewVersion = 1,
            images = photos.mapIndexed { index, photo ->
                MockPhotoExtraction(photo.photoId, photo.uri, index + 1, emptyList())
            },
        )
        val before = snapshot()
        publishSnapshot(before.copy(
            imports = before.imports.filterNot { it.menuImportId == job.menuImportId } + job))
        return accepted.menuImportId
    }

    /** Poll only real server statuses; the backend controls the OCR/matching pipeline. */
    suspend fun pollPhotoImportLive(importId: String): MockImportStatus {
        val dto = remote.getMenuImport(importId)
        val before = snapshot()
        val old = before.imports.firstOrNull { it.menuImportId == importId }
        val status = when(dto.status) {
            "uploaded" -> MockImportStatus.UPLOADED
            "processing" -> MockImportStatus.PROCESSING
            "ready_for_review" -> MockImportStatus.READY_FOR_REVIEW
            "applied" -> MockImportStatus.APPLIED
            "failed" -> MockImportStatus.FAILED
            "canceled" -> MockImportStatus.CANCELED
            else -> error("알 수 없는 서버 작업 상태: ${dto.status}")
        }
        val extraBrands = dto.images.flatMap { image ->
            image.items.flatMap { item -> item.candidates.map { candidate ->
                MockBrand(candidate.brandId, candidate.brandName)
            } }
        }.distinctBy { it.brandId }
        val extraProducts = dto.images.flatMap { image ->
            image.items.flatMap { item -> item.candidates.map { c ->
                MockCatalogProduct(c.productId, c.brandId, c.displayName,
                    c.category, c.ageYears, c.editionName, abvPercent = c.abv)
            } }
        }.distinctBy { it.productId }
        val images = if(dto.status == "ready_for_review") dto.images.map { image ->
            val prior = old?.images?.firstOrNull { it.imageOrder == image.imageOrder }
            MockPhotoExtraction(
                imageId = image.imageId,
                sourceUri = prior?.sourceUri ?: image.imageUrl,
                imageOrder = image.imageOrder,
                lines = image.items.map { item ->
                    val kind = when(item.effectiveLineType) {
                        "product" -> MockLineKind.PRODUCT
                        "unknown" -> MockLineKind.UNKNOWN
                        else -> MockLineKind.NON_PRODUCT
                    }
                    val options = item.options.map { option ->
                        MockMenuOption(
                            optionId = option.extractedOptionId,
                            label = option.extractedOptionLabel,
                            pourMl = option.extractedPourMl
                                ?: if(option.extractedOptionLabel?.lowercase() in
                                    listOf("bottle", "병")) null else
                                    before.bars.firstOrNull { it.barId == (old?.barId ?: dto.barId) }
                                        ?.defaultPourMl ?: 30,
                            priceKrw = option.extractedPriceKrw ?: 0,
                        )
                    }
                    val exact = item.initialResolutionStatus == "exact_match" &&
                        item.proposedProductId != null && kind == MockLineKind.PRODUCT &&
                        options.isNotEmpty() && options.all { it.priceKrw > 0 }
                    val automatic = when {
                        kind == MockLineKind.NON_PRODUCT ->
                            MockReviewDecision(MockDecisionKind.CONFIRM_NON_PRODUCT)
                        exact -> MockReviewDecision(MockDecisionKind.SELECT_PRODUCT,
                            productId = item.proposedProductId, correctedOptions = options)
                        else -> null
                    }
                    MockExtractedLine(
                        extractedItemId = item.extractedItemId,
                        sourceText = item.rawText,
                        kind = kind, suggestedProductId = item.proposedProductId,
                        candidateProductIds = item.candidates.map { it.productId },
                        options = options, decision = automatic,
                        needsPriceEntry = options.isEmpty() || options.any { it.priceKrw <= 0 },
                        sourceBox = item.sourceBox,
                        mockAutoAccepted = exact,
                    )
                },
            )
        } else old?.images.orEmpty()
        val job = (old ?: MockMenuImport(
            menuImportId = importId, barId = dto.barId ?: before.selectedBarId.orEmpty(),
            status = status, reviewVersion = dto.reviewVersion ?: 1, images = images,
        )).copy(
            status = status,
            reviewVersion = dto.reviewVersion ?: old?.reviewVersion ?: 1,
            images = images,
            failureReason = dto.failure?.message,
        )
        publishSnapshot(before.copy(
            imports = before.imports.filterNot { it.menuImportId == importId } + job,
            brands = (before.brands + extraBrands).distinctBy { it.brandId },
            products = (before.products + extraProducts).distinctBy { it.productId },
        ))
        return status
    }

    private fun reviewOptions(
        item: com.zerotoone.bottlemap.network.ReviewItemDto,
        decision: MockReviewDecision,
    ): List<Map<String, Any?>> {
        val corrected = decision.correctedOptions ?: return emptyList()
        val byId = item.options.associateBy { it.extractedOptionId }
        return corrected.mapNotNull { option ->
            val extracted = byId[option.optionId] ?: return@mapNotNull null
            val edits = mutableMapOf<String, Any?>("extractedOptionId" to option.optionId)
            if(option.priceKrw != extracted.extractedPriceKrw)
                edits["correctedPriceKrw"] = option.priceKrw
            if(option.pourMl != extracted.extractedPourMl && option.pourMl != null)
                edits["correctedPourMl"] = option.pourMl
            if(option.label != extracted.extractedOptionLabel && option.label != null)
                edits["correctedOptionLabel"] = option.label
            edits
        }
    }

    /** Apply all item decisions in one backend transaction, and never accept removals. */
    suspend fun publishPhotoImportLive(importId: String, version: Int): Int {
        val current = snapshot()
        val job = current.imports.firstOrNull { it.menuImportId == importId }
            ?: error("메뉴판 작업이 없어요.")
        val original = remote.getMenuImport(importId)
        require(original.status == "ready_for_review") { "검수할 수 없는 서버 작업이에요." }
        require(original.reviewVersion == version) { "REVIEW_OUTDATED" }
        val decisions = job.images.flatMap { it.lines }.associateBy { it.extractedItemId }
        val itemDecisions = original.images.flatMap { it.items }.map { item ->
            val chosen = decisions[item.extractedItemId]?.decision
                ?: error("확인하지 않은 메뉴가 있어요.")
            when(chosen.kind) {
                MockDecisionKind.SELECT_PRODUCT -> mapOf(
                    "action" to "select_existing_product",
                    "extractedItemId" to item.extractedItemId,
                    "finalLineType" to "product",
                    "productId" to chosen.productId,
                    "optionDecisions" to reviewOptions(item, chosen),
                )
                MockDecisionKind.CREATE_PRODUCT -> {
                    val draft = requireNotNull(chosen.newProduct)
                    val brand = if(draft.brandId != null)
                        mapOf("type" to "existing", "brandId" to draft.brandId)
                    else mapOf("type" to "new",
                        "canonicalName" to requireNotNull(draft.brandName),
                        "aliases" to emptyList<Any>())
                    mapOf(
                        "action" to "create_product",
                        "extractedItemId" to item.extractedItemId,
                        "finalLineType" to "product",
                        "brand" to brand,
                        "product" to mapOf(
                            "category" to draft.category,
                            "displayName" to draft.name,
                            "ageYears" to draft.ageYears,
                            "editionName" to draft.editionName,
                            "abv" to draft.abvPercent,
                        ),
                        "optionDecisions" to reviewOptions(item, chosen),
                    )
                }
                MockDecisionKind.CONFIRM_NON_PRODUCT -> mapOf(
                    "action" to "confirm_non_product",
                    "extractedItemId" to item.extractedItemId,
                    "finalLineType" to (if(item.effectiveLineType=="product") "unknown"
                        else item.effectiveLineType),
                )
                MockDecisionKind.EXCLUDE -> mapOf(
                    "action" to "reject",
                    "extractedItemId" to item.extractedItemId,
                    "finalLineType" to item.effectiveLineType,
                )
            }
        }
        val positiveItems = job.images.flatMap { it.lines }.filter {
            it.decision?.kind in listOf(MockDecisionKind.SELECT_PRODUCT,
                MockDecisionKind.CREATE_PRODUCT)
        }.map { it.extractedItemId }.toSet()
        val changes = original.proposedChanges.map {
            com.zerotoone.bottlemap.network.ChangeDecisionDto(
                changeId = it.changeId,
                decision = if(it.changeType == "remove" ||
                    it.extractedItemId !in positiveItems) "ignore" else "apply",
            )
        }
        val result = remote.reviewAndApply(importId,
            com.zerotoone.bottlemap.network.ReviewAndApplyRequestDto(
                reviewVersion = version,
                itemDecisions = itemDecisions,
                changeDecisions = changes,
            ))
        publishSnapshot(current.copy(imports = current.imports.map {
            if(it.menuImportId == importId) it.copy(status = MockImportStatus.APPLIED,
                publishedAddedCount = result.result.added,
                publishedNewProductCount = result.result.createdProducts)
            else it
        }))
        refresh()
        return result.result.added
    }

    // Local-only interactions that have no published server equivalent must not fake a save.
    override fun registerApplication(application: MockOwnerApplication) =
        error("신청서는 서버 등록을 사용해야 합니다.")
    override fun submitRegistrationDraftForFixture(): String =
        error("실제 신청 접수 API 연결 전에는 신청을 완료할 수 없습니다.")
    override fun approveForFixture(applicationId: String, bar: MockBar) =
        error("매장 승인은 운영자 웹에서 진행합니다.")
    override fun closeApplicationForFixture(applicationId: String, status: MockApplicationStatus) {
        require(status == MockApplicationStatus.CANCELED) { "운영자만 상태를 변경할 수 있습니다." }
        write { remote.cancelOwnerApplication(applicationId) }
    }

    override fun saveRegistrationDraft(draft: MockRegistrationDraft?) =
        local.saveRegistrationDraft(draft)
    override fun seedExistingCandidateForFixture(bar: MockBar) =
        error("매장 검색은 서버 검색 API를 사용해 주세요.")
    override fun dismissRejectedForFixture(applicationId: String) =
        local.dismissRejectedForFixture(applicationId)
    override fun saveBrand(brand: MockBrand) =
        error("브랜드는 메뉴 저장 시 함께 등록해 주세요.")
    override fun saveCatalogProduct(product: MockCatalogProduct) =
        error("상품은 메뉴 저장 시 함께 등록해 주세요.")
    override fun applyOperatingException(barId: String, exception: MockOperatingException) {
        val fields = mutableMapOf<String, Any?>("note" to exception.note)
        when(exception.kind) {
            MockExceptionKind.CLOSED_TODAY -> {
                fields["kind"] = "closed_today"
                fields["date"] = date(exception.fromEpochDay)
            }
            MockExceptionKind.CUSTOM_HOURS -> {
                fields["kind"] = "custom_hours"
                fields["date"] = date(exception.fromEpochDay)
                fields["openTime"] = time(exception.openMinutes)
                fields["closeTime"] = time(exception.closeMinutes)
            }
            MockExceptionKind.VACATION -> {
                fields["kind"] = "vacation"
                fields["startDate"] = date(exception.fromEpochDay)
                fields["endDate"] = date(exception.toEpochDay)
            }
        }
        write { remote.setOperatingException(barId, fields) }
    }
    override fun cancelOperatingException(barId: String, exceptionId: String) {
        write { remote.removeOperatingException(barId) }
    }
    override fun startPhotoImport(
        barId: String, selectedUris: List<String>, fixture: MockPhotoExtractionSource,
    ): String = error("서버 사진 업로드를 사용해 주세요.")
    override fun queuePhotoImport(barId: String, photos: List<MockPhoto>): String =
        error("사진 업로드 API 연결 전에는 가짜 작업을 만들지 않습니다.")
    override fun finishPhotoImport(importId: String, source: MockPhotoExtractionSource): MockImportStatus =
        MockImportStatus.PROCESSING
    override fun cancelPhotoImport(importId: String) =
        error("사진 업로드 취소 API 연결이 필요합니다.")
    override fun discardPhotoImport(importId: String) =
        error("서버 작업 취소 API 연결이 필요합니다.")
    override fun resetPhotoReview(importId: String, expectedVersion: Int) =
        error("사진 검수 초기화 API는 제공되지 않습니다.")
    override fun retryFailedPhotoImport(importId: String): String =
        error("사진을 다시 선택해 등록해 주세요.")
    override fun decideLine(
        importId: String, extractedItemId: String, expectedVersion: Int,
        decision: MockReviewDecision,
    ) = error("서버 사진 검수를 완료해야 합니다.")
    override fun publishAddOnly(importId: String, expectedVersion: Int): Int =
        error("서버 사진 검수를 완료해야 합니다.")
    override fun preview(barId: String, nowEpochMs: Long): MockPreview? =
        local.preview(barId, nowEpochMs)
}
