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
    override val state = local.state

    init { retryLoad() }

    private fun snapshot(): MockOwnerSnapshot = when (val s = state.value) {
        is MockOwnerLoadState.Ready -> s.snapshot
        is MockOwnerLoadState.Empty -> s.snapshot
        else -> MockOwnerSnapshot()
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
            local.replaceFromBackend(MockOwnerSnapshot())
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
        local.replaceFromBackend(old.copy(
            bars = mappedBars, applications = applications.map(::toApplication),
            menuItems = rows, brands = brands, products = products,
            selectedBarId = selected,
        ))
    }

    override fun retryLoad() {
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
        if(changes.isNotEmpty()) write { remote.updateBar(bar.barId, changes) }
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
    override fun applyOperatingException(barId: String, exception: MockOperatingException) =
        error("임시 영업시간 변경은 API 연결이 필요합니다.")
    override fun cancelOperatingException(barId: String, exceptionId: String) =
        error("임시 영업시간 취소는 API 연결이 필요합니다.")
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
