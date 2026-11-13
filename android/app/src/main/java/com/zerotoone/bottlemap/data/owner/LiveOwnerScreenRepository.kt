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
import kotlinx.coroutines.withContext
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
    private val pendingCoverStore = PendingOwnerCoverStore(app.noBackupFilesDir)
    @Volatile var pendingCoverWarning: String? = null
        private set
    @Volatile var lastRefreshWarning: String? = null
        private set
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val writeMutex = Mutex()
    @Volatile var lastPublishWarning: String? = null
        private set
    private val generation = AtomicInteger(0)
    private val versionByBar = mutableMapOf<String, Int?>()
    private var sessionSubject: String? = null
    private var pendingPhotoRetry: Pair<List<String>, String>? = null
    private var pendingPhotoRetryBarId: String? = null

    /** This is a cache-partition key only, not an authorization check. */
    private fun sessionKey(accessToken: String): String {
        val subject = runCatching {
            val part = accessToken.split('.').getOrNull(1) ?: return@runCatching null
            val decoded = android.util.Base64.decode(part,
                android.util.Base64.URL_SAFE or android.util.Base64.NO_WRAP or
                    android.util.Base64.NO_PADDING)
            org.json.JSONObject(String(decoded, Charsets.UTF_8)).optString("sub")
                .takeIf { it.isNotBlank() }
        }.getOrNull()
        return subject ?: accessToken.hashCode().toString()
    }

    private fun menuImportStatus(value: String): MockImportStatus = when(value) {
        "uploaded" -> MockImportStatus.UPLOADED
        "processing" -> MockImportStatus.PROCESSING
        "ready_for_review" -> MockImportStatus.READY_FOR_REVIEW
        "failed" -> MockImportStatus.FAILED
        "applied" -> MockImportStatus.APPLIED
        "canceled" -> MockImportStatus.CANCELED
        else -> error("알 수 없는 서버 작업 상태: $value")
    }
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
        representativeName = app.representativeName,
        businessNumberDigits = app.businessRegistrationNumber,
        openingDateIso = app.openingDate,
        contactPhone = app.contactPhone,
        storePhone = app.proposedBar?.phone,
        rejectionReason = app.rejectionReason,
        submittedAtEpochMs = timestamp(app.createdAt) ?: 0L,
        reviewedAtEpochMs = timestamp(app.reviewedAt),
        registrationPhotos = listOfNotNull(app.coverPhoto?.let { photo ->
            MockPhoto("server-pending-cover", photo.imageUrl, MockPhotoKind.BAR_GALLERY)
        }) + app.menuPhotos.sortedBy { it.imageOrder }.map { photo ->
            MockPhoto("server-menu-${photo.imageOrder}", photo.imageUrl,
                MockPhotoKind.MENU_CAPTURE)
        },
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

    private suspend fun refresh(expectedGeneration: Int? = null) {
        val refreshGeneration = expectedGeneration ?: generation.get()
        val token = AppAuth.gateway.currentAccessTokenOrNull()
        if(token == null) {
            pendingCoverWarning = null
            sessionSubject = null
            pendingPhotoRetry = null
            pendingPhotoRetryBarId = null
            pendingApplicationId = null
            versionByBar.clear()
            publishSnapshot(MockOwnerSnapshot())
            return
        }
        val subject = sessionKey(token)
        if(subject != sessionSubject) {
            pendingCoverWarning = null
            // The singleton is shared across sign-in sessions. Never retain another
            // Owner's bars, imports, registration photos or unsent decisions.
            sessionSubject = subject
            pendingPhotoRetry = null
            pendingPhotoRetryBarId = null
            pendingApplicationId = null
            versionByBar.clear()
            publishSnapshot(MockOwnerSnapshot())
        }
        val old = snapshot()
        val bars = remote.getOwnedBars().map { bar ->
            // Existing unconfigured bars follow the Android decision: persist 30 ml.
            if(bar.defaultPourMl == null) runCatching {
                remote.updateBar(bar.barId, mapOf("defaultPourMl" to 30))
            }.getOrDefault(bar) else bar
        }
        val applications = remote.getMyApplications()
        // A freshly approved application now has barId, but its selected cover
        // was not accepted by POST /api/owner-applications. Upload to the first
        // available photo slot using the existing bar photo API, once.
        val coverApplications = applications.filter {
            it.applicationType == "new_bar" && !it.businessRegistrationNumber.isNullOrBlank()
        }
        withContext(Dispatchers.IO) {
            for(application in coverApplications) {
                val businessNumber = requireNotNull(application.businessRegistrationNumber)
                pendingCoverStore.attach(subject, businessNumber, application.applicationId)
                if(application.coverPhoto != null ||
                    application.status == "canceled" || application.status == "rejected")
                    pendingCoverStore.remove(subject, application.applicationId, businessNumber)
            }
        }
        var coverWarning: String? = null
        val barsWithCovers = bars.map { bar ->
            val approvedApplication = coverApplications.firstOrNull {
                it.status == "approved" && it.bar?.barId == bar.barId
            }
            val jpeg = approvedApplication?.let { application ->
                withContext(Dispatchers.IO) {
                    pendingCoverStore.read(subject, application.applicationId)
                }
            }
            if(jpeg == null) bar
            else if(bar.photos.isNotEmpty()) {
                // A successful upload can lose its HTTP response. Do not upload
                // again on refresh and risk adding the same cover twice.
                coverWarning = "매장 사진이 이미 등록되어 있어 대표 사진을 확인해 주세요."
                bar
            } else try {
                if(AppAuth.gateway.currentAccessTokenOrNull()?.let(::sessionKey) != subject)
                    return
                val photo = remote.addBarPhoto(bar.barId,
                    com.zerotoone.bottlemap.data.PreparedMenuImage(
                        "owner-representative.jpg", "image/jpeg", jpeg))
                val approved = requireNotNull(approvedApplication)
                withContext(Dispatchers.IO) {
                    pendingCoverStore.remove(subject, approved.applicationId,
                        approved.businessRegistrationNumber)
                }
                bar.copy(photos = photo.photos)
            } catch(cancelled: CancellationException) {
                throw cancelled
            } catch(error: Exception) {
                coverWarning = "대표 사진 업로드를 완료하지 못했어요. 매장 사진에서 다시 확인해 주세요."
                bar
            }
        }
        pendingCoverWarning = coverWarning
        val locallyStagedCoverIds = withContext(Dispatchers.IO) {
            coverApplications.filter { application ->
                application.status == "pending" &&
                    pendingCoverStore.read(subject, application.applicationId) != null
            }.mapTo(mutableSetOf()) { it.applicationId }
        }
        val importHistory = barsWithCovers.associate { bar ->
            bar.barId to remote.getMenuImports(bar.barId).items
        }
        val menus = barsWithCovers.associate { bar ->
            bar.barId to remote.getOwnedMenu(bar.barId)
        }
        // Do not let an older in-flight Owner entry request publish after a newer one.
        if (refreshGeneration != generation.get()) return
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
        val mappedBars = barsWithCovers.map(::toBar)
        val selected = old.selectedBarId?.takeIf { id -> mappedBars.any { it.barId == id } }
            ?: mappedBars.firstOrNull()?.barId
        // Restore the complete latest import history after process recreation, including
        // failed and ready_for_review jobs. The server list is newest first; the
        // existing screens select the last job, so reverse it into chronological order.
        val importedJobs = barsWithCovers.flatMap { bar ->
            val histories = importHistory[bar.barId].orEmpty().asReversed().toMutableList()
            val active = bar.activeMenuImport
            if(active != null && histories.none { it.menuImportId == active.menuImportId }) {
                histories.add(com.zerotoone.bottlemap.network.MenuImportListItemDto(
                    menuImportId = active.menuImportId,
                    mode = "partial_update", status = active.status,
                    imageCount = 0, reviewVersion = 0,
                    createdAt = "1970-01-01T00:00:00Z",
                ))
            }
            histories.map { historical ->
                val previous = old.imports.firstOrNull {
                    it.menuImportId == historical.menuImportId
                }
                val serverStatus = menuImportStatus(historical.status)
                // List responses omit extracted items. A recovered ready import must
                // open the polling screen once to fetch complete Stage 8 review data,
                // not show a 0-line publish screen after process recreation.
                val changedReviewVersion = previous != null &&
                    previous.reviewVersion != maxOf(1, historical.reviewVersion)
                val requiresDetails = needsReviewDetailReload(
                    previous, maxOf(1, historical.reviewVersion))
                val displayStatus = if(serverStatus == MockImportStatus.READY_FOR_REVIEW &&
                    requiresDetails) MockImportStatus.PROCESSING
                    else serverStatus
                (previous ?: MockMenuImport(
                    menuImportId = historical.menuImportId, barId = bar.barId,
                    status = displayStatus,
                    reviewVersion = maxOf(1,historical.reviewVersion),
                    images = emptyList(),
                )).copy(
                    status = displayStatus,
                    // Never retain decisions made against a stale server review diff.
                    images = if(changedReviewVersion) emptyList() else previous?.images.orEmpty(),
                    reviewVersion = maxOf(1,historical.reviewVersion),
                    imageCount = maxOf(historical.imageCount,previous?.imageCount ?: 0),
                    completedImages = previous?.completedImages ?: 0,
                )
            }
        }
        // Never publish a response from a former session after account switch.
        if(AppAuth.gateway.currentAccessTokenOrNull()?.let(::sessionKey) != subject ||
            refreshGeneration != generation.get()) return
        publishSnapshot(old.copy(
            bars = mappedBars, applications = applications.map { application ->
                val mapped = toApplication(application)
                if(application.applicationId in locallyStagedCoverIds)
                    mapped.copy(registrationPhotos = mapped.registrationPhotos.filterNot {
                        it.kind == MockPhotoKind.BAR_GALLERY
                    } + MockPhoto("local-pending-cover", "", MockPhotoKind.BAR_GALLERY))
                else mapped
            },
            menuItems = rows, brands = brands, products = products,
            selectedBarId = selected,
            imports = importedJobs,
        ))
    }

    override fun retryLoad() {
        lastReadySnapshot = snapshot()
        val requested = generation.incrementAndGet()
        local.serverLoading()
        scope.launch {
            try {
                if(requested == generation.get()) refresh(requested)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if(requested == generation.get())
                    local.serverError(error.message ?: "매장 정보를 가져오지 못했어요.")
            }
        }
    }

    /** A committed write is not a failed write just because the subsequent GET times out. */
    private suspend fun refreshAfterWrite() {
        try {
            refresh()
            lastRefreshWarning = null
        } catch(cancelled: CancellationException) {
            throw cancelled
        } catch(error: Exception) {
            lastRefreshWarning = "저장은 완료됐지만 목록을 새로고침하지 못했어요. 다시 불러와 주세요."
            local.serverError(requireNotNull(lastRefreshWarning))
        }
    }

    private fun write(op: suspend () -> Unit) {
        scope.launch {
            writeMutex.withLock {
                try {
                    op()
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (error: Exception) {
                    runCatching { refresh() }
                    local.serverError(error.message ?: "저장하지 못했어요. 다시 시도해 주세요.")
                    return@withLock
                }
                refreshAfterWrite()
            }
        }
    }

    override fun selectBar(barId: String) = local.selectBar(barId)

    /** Server limits gallery to a 2048 px JPEG under 2 MB, not menu's 10 MB. */
    private suspend fun prepareGalleryPhoto(uri: String):
        com.zerotoone.bottlemap.data.PreparedMenuImage {
        val prepared = ImageUploadPreparer(app.contentResolver).prepare(Uri.parse(uri))
        // A compressed 8K photo can still allocate >150 MB when decoded at full size.
        val bounds = android.graphics.BitmapFactory.Options().apply {
            inJustDecodeBounds = true
        }
        android.graphics.BitmapFactory.decodeByteArray(
            prepared.bytes, 0, prepared.bytes.size, bounds)
        require(bounds.outWidth > 0 && bounds.outHeight > 0) {
            "매장 사진을 읽을 수 없어요."
        }
        val sample = sampledBitmapSize(bounds.outWidth, bounds.outHeight)
        val decoded = android.graphics.BitmapFactory.decodeByteArray(
            prepared.bytes, 0, prepared.bytes.size,
            android.graphics.BitmapFactory.Options().apply { inSampleSize = sample })
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
        replaceOwnerGallerySafely(
            old = old, now = now,
            prepare = { prepareGalleryPhoto(it.uri) },
            upload = { prepared ->
                val result = remote.addBarPhoto(barId, prepared)
                result.photos.lastOrNull()?.photoId
                    ?: error("사진은 업로드됐지만 ID 확인에 실패했어요. 새로고침 후 확인해 주세요.")
            },
            delete = { photoId -> remote.deleteBarPhoto(barId, photoId); Unit },
            reorder = { ids -> remote.reorderBarPhotos(barId, ids); Unit },
        )
    }

    private suspend fun persistBar(old: MockBar, bar: MockBar) {
        val changes = mutableMapOf<String, Any?>()
        if(old.name != bar.name) changes["name"] = bar.name
        requireMovedBarCoordinates(old, bar)?.let { (latitude, longitude) ->
            changes["address"] = bar.address
            changes["latitude"] = latitude
            changes["longitude"] = longitude
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
        if(changes.isNotEmpty()) remote.updateBar(bar.barId, changes)
        if(old.gallery != bar.gallery) syncGallery(bar.barId, old.gallery, bar.gallery)
    }

    override fun saveBar(bar: MockBar) {
        val old = snapshot().bars.firstOrNull { it.barId == bar.barId }
            ?: error("매장 정보를 먼저 불러와 주세요.")
        local.saveBar(bar)
        write { persistBar(old,bar) }
    }

    /** Used by save buttons: return only after the server commits and the UI refreshes. */
    suspend fun saveBarLive(bar: MockBar) = confirmedWrite {
        val old = snapshot().bars.firstOrNull { it.barId == bar.barId }
            ?: error("매장 정보를 먼저 불러와 주세요.")
        persistBar(old,bar)
    }

    private suspend fun sendManualItemToServer(
        item: MockBarMenuItem, newProduct: MockCatalogProduct?,
        newBrand: MockBrand?, before: MockOwnerSnapshot,
    ) {
        val old = before.menuItems.firstOrNull { it.barMenuItemId == item.barMenuItemId }
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
                    val knownBrandId = before.brands.firstOrNull {
                    it.brandId == newProduct.brandId &&
                        runCatching { java.util.UUID.fromString(it.brandId) }.isSuccess
                }?.brandId
                val brand = if(knownBrandId != null)
                    mapOf("type" to "existing", "brandId" to knownBrandId)
                else mapOf("type" to "new",
                    "canonicalName" to (newBrand?.name ?: error("브랜드 이름이 없어요.")),
                    "aliases" to emptyList<Any>())
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
            }    }

    /** Manual menu screen awaits the HTTP response before claiming success or closing the editor. */
    suspend fun saveManualMenuItemLive(
        item: MockBarMenuItem, newProduct: MockCatalogProduct?, newBrand: MockBrand?,
    ) {
        writeMutex.withLock {
            try {
                sendManualItemToServer(item, newProduct, newBrand, snapshot())
            } catch(cancelled: CancellationException) {
                throw cancelled
            } catch(error: Exception) {
                runCatching { refresh() }
                throw error
            }
            refreshAfterWrite()
        }
    }

    override fun saveManualMenuItem(
        item: MockBarMenuItem, newProduct: MockCatalogProduct?, newBrand: MockBrand?,
    ) {
        val before = snapshot()
        local.saveManualMenuItem(item, newProduct, newBrand)
        write { sendManualItemToServer(item, newProduct, newBrand, before) }
    }

    override fun saveMenuItem(item: MockBarMenuItem) = saveManualMenuItem(item, null, null)

    private suspend fun confirmedWrite(operation: suspend () -> Unit) {
        writeMutex.withLock {
            try {
                operation()
            } catch(cancelled: CancellationException) {
                throw cancelled
            } catch(error: Exception) {
                runCatching { refresh() }
                throw error
            }
            refreshAfterWrite()
        }
    }

    suspend fun setSoldOutLive(itemId: String, value: Boolean) = confirmedWrite {
        val item = snapshot().menuItems.firstOrNull { it.barMenuItemId == itemId }
            ?: error("메뉴가 없어요.")
        remote.setSoldOut(item.barId, itemId, value)
    }

    suspend fun deleteMenuItemLive(itemId: String) = confirmedWrite {
        val item = snapshot().menuItems.firstOrNull { it.barMenuItemId == itemId }
            ?: error("메뉴가 없어요.")
        remote.deleteMenuItem(item.barId, itemId,
            versionByBar[item.barId] ?: error("메뉴 버전을 불러와 주세요."))
    }

    suspend fun clearMenuForBarLive(barId: String) = confirmedWrite {
        remote.resetMenu(barId, versionByBar[barId])
    }

    suspend fun confirmMenuInformationLive(barId: String) = confirmedWrite {
        remote.confirmMenu(barId, versionByBar[barId])
    }

    suspend fun cancelPhotoImportLive(importId: String) = confirmedWrite {
        remote.cancelMenuImport(importId)
    }

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
    suspend fun cancelOwnerApplicationLive(applicationId: String) {
        val subject = AppAuth.gateway.currentAccessTokenOrNull()?.let(::sessionKey)
        val application = remote.cancelOwnerApplication(applicationId)
        if(subject != null) withContext(Dispatchers.IO) {
            pendingCoverStore.remove(subject, applicationId,
                application.businessRegistrationNumber)
        }
        refreshAfterWrite()
    }

    suspend fun verifyBusinessBeforeApplicationLive(
        registrationNumber: String, representativeName: String, openingDate: String,
    ): String = remote.verifyBusinessRegistration(
        registrationNumber, representativeName, openingDate,
    ).result

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
        val ownerSubject = AppAuth.gateway.currentAccessTokenOrNull()?.let(::sessionKey)
            ?: error("로그인 후 신청해 주세요.")
        if(draft.kind == MockApplicationKind.NEW_BAR) {
            val coverUri = draft.applicantGallery.firstOrNull()?.uri
                ?: error("대표 사진을 선택해 주세요.")
            // Stage before POST: if Android is terminated after a server-side
            // success, GET /me/owner-applications can recover the association.
            withContext(Dispatchers.IO) {
                val cover = prepareGalleryPhoto(coverUri)
                pendingCoverStore.stage(ownerSubject, draft.businessNumberDigits, cover.bytes)
            }
        }
        val existing = remote.getMyApplications().firstOrNull {
            matchesPendingOwnerApplication(it, draft)
        }
        // Never reuse a retry ID belonging to another bar or another draft.
        val cachedId = pendingApplicationId?.takeIf { it == existing?.applicationId }
        val applicationId = cachedId ?: existing?.applicationId
            ?: remote.submitOwnerApplication(body).applicationId
        pendingApplicationId = applicationId
        if(draft.kind == MockApplicationKind.NEW_BAR) {
            withContext(Dispatchers.IO) {
                pendingCoverStore.attach(ownerSubject,draft.businessNumberDigits,applicationId)
            }
            val bytes=withContext(Dispatchers.IO) {
                pendingCoverStore.read(ownerSubject,applicationId)
            } ?: error("선택한 대표 사진을 찾지 못했어요.")
            try {
                remote.uploadApplicationCoverPhoto(applicationId,
                    com.zerotoone.bottlemap.data.PreparedMenuImage(
                        filename="owner-cover.jpg",mimeType="image/jpeg",bytes=bytes))
                withContext(Dispatchers.IO) {
                    pendingCoverStore.remove(ownerSubject,applicationId,draft.businessNumberDigits)
                }
            } catch(e: com.zerotoone.bottlemap.network.BottleMapApiException) {
                // Old servers have no cover upload route: retain private staged JPEG
                // for the existing after-approval attachment fallback.
                if(e.httpStatus != 404 || e.code != "HTTP_404") throw e
            }
        }
        if(draft.initialMenuPhotos.isNotEmpty()) {
            val preparer = ImageUploadPreparer(app.contentResolver)
            val images = draft.initialMenuPhotos.map { photo ->
                preparer.prepare(Uri.parse(photo.uri))
            }
            remote.uploadApplicationMenuPhotos(applicationId, images)
        }
        pendingApplicationId = null
        local.saveRegistrationDraft(null)
        refreshAfterWrite()
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

    suspend fun searchCatalogBrandsLive(query: String) {
        val trimmed=query.trim()
        if(trimmed.length<2 || trimmed.length>100) return
        val matches=remote.searchCatalogBrands(trimmed)
        val mapped=matches.map {
            MockBrand(it.brandId,it.canonicalName,it.matchedAlias)
        }
        val ids=mapped.mapTo(mutableSetOf()) { it.brandId }
        val previous=snapshot()
        publishSnapshot(previous.copy(
            brands=previous.brands.filterNot { it.brandId in ids } + mapped
        ))
    }

    suspend fun searchCatalogLive(query: String) {
        val trimmed = query.trim()
        if(trimmed.isEmpty() || trimmed.length > 100) return
        val results = remote.searchCatalogProducts(trimmed)
        val before = snapshot()
        publishSnapshot(before.copy(
            // New catalogue responses override cached activation flags.
            products = (results.map { item ->
                MockCatalogProduct(item.productId, item.brandId, item.displayName,
                    item.category, item.ageYears, item.editionName,
                    abvPercent = item.abv, isActive = item.isActive,
                    matchedAlias = item.matchedAlias)
            } + before.products).distinctBy { it.productId },
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
        val fingerprint = photos.map { it.uri }
        val key = if(pendingPhotoRetryBarId == barId &&
            pendingPhotoRetry?.first == fingerprint)
            requireNotNull(pendingPhotoRetry).second
        else java.util.UUID.randomUUID().toString()
        pendingPhotoRetryBarId = barId
        pendingPhotoRetry = fingerprint to key
        val accepted = remote.uploadMenuImport(
            barId = barId,
            images = images,
            // Existing backend supports partial_update; never request full_replace.
            mode = "partial_update",
            idempotencyKey = key,
        )
        pendingPhotoRetry = null
        pendingPhotoRetryBarId = null
        val job = MockMenuImport(
            menuImportId = accepted.menuImportId, barId = barId,
            status = MockImportStatus.PROCESSING, reviewVersion = 1,
            imageCount = accepted.imageCount,
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
        val status = menuImportStatus(dto.status)
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
                sourceUri = currentReviewImageUri(prior?.sourceUri, image.imageUrl),
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
        val priceCheckedImages = if(status == MockImportStatus.READY_FOR_REVIEW)
            requirePhotoPriceReviewOnConflict(images) else images
        val job = (old ?: MockMenuImport(
            menuImportId = importId, barId = dto.barId ?: before.selectedBarId.orEmpty(),
            status = status, reviewVersion = dto.reviewVersion ?: 1, images = images,
        )).copy(
            status = status,
            reviewVersion = dto.reviewVersion ?: old?.reviewVersion ?: 1,
            images = priceCheckedImages,
            imageCount = maxOf(old?.imageCount ?: 0,dto.progress?.totalImages ?: 0,
                priceCheckedImages.size),
            completedImages = dto.progress?.completedImages ?: old?.completedImages ?: 0,
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
            validateReviewOptionClearing(option,
                MockMenuOption(extracted.extractedOptionId,
                    label = extracted.extractedOptionLabel,
                    pourMl = extracted.extractedPourMl, priceKrw = extracted.extractedPriceKrw ?: 0))
            if(option.pourMl != extracted.extractedPourMl && option.pourMl != null)
                edits["correctedPourMl"] = option.pourMl
            if(option.label != extracted.extractedOptionLabel && option.label != null)
                edits["correctedOptionLabel"] = option.label
            edits
        }
    }

    /**
     * Stage 8 can collect a price for a product without extracted options, but the
     * backend review API cannot create a new extractedOptionId. Preserve that UI
     * choice and use the already-supported manual add API after review publish.
     */
    private suspend fun publishPriceEntryOnlyRows(
        before: MockOwnerSnapshot, job: MockMenuImport,
        missingOptionLineIds: Set<String>,
    ): Triple<Int, Int, List<String>> {
        var menu = remote.getOwnedMenu(job.barId)
        var added = 0
        var created = 0
        val warnings = mutableListOf<String>()
        val candidates = job.images.flatMap { it.lines }.filter { line ->
            line.extractedItemId in missingOptionLineIds &&
                line.decision?.kind in listOf(
                    MockDecisionKind.SELECT_PRODUCT, MockDecisionKind.CREATE_PRODUCT)
        }
        for(line in candidates) {
            val decision = requireNotNull(line.decision)
            val options = decision.correctedOptions.orEmpty()
            if(options.isEmpty() || options.any { it.priceKrw <= 0 } || options.size > 3) {
                warnings += "${line.sourceText}: 가격을 확인하고 직접 등록해 주세요."
                continue
            }
            val selectedId = decision.productId
            if(selectedId != null && (before.menuItems.any {
                it.barId == job.barId && it.productId == selectedId
            } || menu.items.any { it.productId == selectedId })) continue
            val display = if(decision.kind == MockDecisionKind.CREATE_PRODUCT)
                decision.newProduct?.name ?: line.sourceText
            else before.products.firstOrNull { it.productId == selectedId }?.displayName
                ?: line.sourceText
            val body = mutableMapOf<String, Any?>(
                "menuVersion" to menu.menuVersion,
                "displayName" to display.take(200),
                "options" to options.map { option ->
                    mapOf(
                        "optionLabel" to option.label,
                        "pourMl" to if(option.label in listOf("병", "Bottle", "bottle"))
                            null else option.pourMl ?: 30,
                        "priceKrw" to option.priceKrw,
                        "discount" to null,
                    )
                },
            )
            if(decision.kind == MockDecisionKind.SELECT_PRODUCT) {
                body["productId"] = requireNotNull(selectedId)
            } else {
                val draft = requireNotNull(decision.newProduct)
                body["newProduct"] = mapOf(
                    "brand" to if(draft.brandId != null)
                        mapOf("type" to "existing", "brandId" to draft.brandId)
                    else mapOf("type" to "new",
                        "canonicalName" to requireNotNull(draft.brandName),
                        "aliases" to emptyList<Any>()),
                    "product" to mapOf(
                        "category" to draft.category,
                        "displayName" to draft.name,
                        "ageYears" to draft.ageYears,
                        "editionName" to draft.editionName,
                        "abv" to draft.abvPercent,
                    ),
                    "aliases" to emptyList<Any>(),
                )
            }
            try {
                menu = remote.addMenuItem(job.barId, body)
                added++
                if(decision.kind == MockDecisionKind.CREATE_PRODUCT) created++
            } catch(cancelled: CancellationException) {
                throw cancelled
            } catch(error: Exception) {
                warnings += "${display}: 사진에서 입력한 가격을 추가하지 못했어요. 직접 등록해 주세요."
                menu = remote.getOwnedMenu(job.barId)
            }
        }
        return Triple(added, created, warnings)
    }

    private fun sameServing(
        current: com.zerotoone.bottlemap.network.BarMenuOptionDto, scanned: MockMenuOption,
    ): Boolean = if(current.pourMl != null || scanned.pourMl != null)
        current.pourMl != null && current.pourMl == scanned.pourMl
    else current.optionLabel.orEmpty().trim().equals(
        scanned.label.orEmpty().trim(), ignoreCase = true)

    /**
     * A photo must never overwrite a discount. The old catalog row is kept in the
     * publish transaction, then only the recognized option prices are updated with
     * the regular manual edit API. All untouched prices/options/discounts survive.
     */
    private suspend fun updatePreviouslyListedPrices(
        original: MockOwnerSnapshot, job: MockMenuImport,
    ): List<String> {
        val previouslyListed = original.menuItems.filter { it.barId == job.barId }
            .associateBy { it.productId }
        val selected = reviewedServingsByProduct(job, previouslyListed.keys)
        if(selected.isEmpty()) return emptyList()
        val warnings = mutableListOf<String>()
        var menu = remote.getOwnedMenu(job.barId)
        for((productId, priced) in selected) {
            val listed = menu.items.firstOrNull { it.productId == productId } ?: continue
            if(priced.isEmpty() || priced.any { it.priceKrw <= 0 }) {
                warnings += "${listed.displayName}: 가격을 확인하고 직접 수정해 주세요."
                continue
            }
            val existingOptions = listed.options.sortedBy { it.sortOrder }
            val options = existingOptions.map { entry ->
                mutableMapOf<String, Any?>(
                    "optionLabel" to entry.optionLabel,
                    "pourMl" to entry.pourMl,
                    "priceKrw" to entry.priceKrw,
                    "discount" to entry.discount?.let { discount ->
                        mapOf(
                            "discountedPriceKrw" to discount.discountedPriceKrw,
                            "startsAt" to discount.startsAt,
                            "endsAt" to discount.endsAt,
                        )
                    },
                )
            }.toMutableList()
            var changed = false
            for(scanned in priced) {
                val matchIndex = options.indexOfFirst { entry ->
                    reviewServingKey(entry["pourMl"] as? Int,
                        entry["optionLabel"] as? String) ==
                        reviewServingKey(scanned.pourMl, scanned.label)
                }
                if(matchIndex >= 0) {
                    val oldOption = existingOptions.getOrNull(matchIndex)
                    if(options[matchIndex]["priceKrw"] == scanned.priceKrw) continue
                    if(oldOption?.discount != null &&
                        scanned.priceKrw <= oldOption.discount.discountedPriceKrw) {
                        warnings += "${listed.displayName}: 기존 할인가보다 정가가 낮아 가격 확인이 필요해요."
                        continue
                    }
                    options[matchIndex]["priceKrw"] = scanned.priceKrw
                    changed = true
                } else if(options.size < 3 && listed.category == "whisky") {
                    options += mutableMapOf(
                        "optionLabel" to scanned.label,
                        "pourMl" to scanned.pourMl,
                        "priceKrw" to scanned.priceKrw,
                        "discount" to null,
                    )
                    changed = true
                } else {
                    warnings += "${listed.displayName}: 추가 용량은 메뉴에서 직접 확인해 주세요."
                }
            }
            if(!changed) continue
            try {
                menu = remote.updateMenuItem(
                    barId = job.barId, itemId = listed.barMenuItemId,
                    body = mapOf(
                        "menuVersion" to menu.menuVersion,
                        "displayName" to listed.displayName,
                        "options" to options,
                    ),
                )
            } catch(cancelled: CancellationException) {
                throw cancelled
            } catch(error: Exception) {
                warnings += "${listed.displayName}: 가격 변경 실패. 직접 수정해 주세요."
                // A successful request can race a lost response. Reload the version.
                menu = remote.getOwnedMenu(job.barId)
            }
        }
        return warnings
    }

    /** Apply all item decisions in one backend transaction, and never accept removals. */
    suspend fun publishPhotoImportLive(importId: String, version: Int): Int {
        val current = snapshot()
        val job = current.imports.firstOrNull { it.menuImportId == importId }
            ?: error("메뉴판 작업이 없어요.")
        val original = remote.getMenuImport(importId)
        require(original.status == "ready_for_review") { "검수할 수 없는 서버 작업이에요." }
        require(original.reviewVersion == version) { "REVIEW_OUTDATED" }
        require(conflictingReviewedPhotoPrices(job).isEmpty()) {
            "같은 메뉴·용량에 다른 가격을 입력했어요. 가격을 하나로 맞춘 후 게시해 주세요."
        }
        val decisions = job.images.flatMap { it.lines }.associateBy { it.extractedItemId }
        val missingOptionLineIds = original.images.flatMap { it.items }
            .filter { it.options.isEmpty() }.mapTo(mutableSetOf()) { it.extractedItemId }
        val itemDecisions = original.images.flatMap { it.items }.map { item ->
            val chosen = decisions[item.extractedItemId]?.decision
                ?: error("확인하지 않은 메뉴가 있어요.")
            when(chosen.kind) {
                MockDecisionKind.SELECT_PRODUCT -> {
                    // Existing rows are priced through the manual endpoint AFTER publish,
                    // so the backend's review transaction cannot drop their discounts.
                    if(item.extractedItemId in missingOptionLineIds ||
                        current.menuItems.any { row ->
                            row.barId == job.barId && row.productId == chosen.productId
                        }) mapOf(
                        "action" to "reject",
                        "extractedItemId" to item.extractedItemId,
                        "finalLineType" to "product",
                    ) else mapOf(
                        "action" to "select_existing_product",
                        "extractedItemId" to item.extractedItemId,
                        "finalLineType" to "product",
                        "productId" to chosen.productId,
                        "correctedProductName" to chosen.displayNameOverride,
                        "optionDecisions" to reviewOptions(item, chosen),
                    )
                }
                MockDecisionKind.CREATE_PRODUCT -> {
                    if(item.extractedItemId in missingOptionLineIds) {
                        mapOf(
                            "action" to "reject",
                            "extractedItemId" to item.extractedItemId,
                            "finalLineType" to "product",
                        )
                    } else {
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
                        "correctedProductName" to chosen.displayNameOverride,
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
                    it.changeType == "update" ||
                    it.extractedItemId in missingOptionLineIds ||
                    it.extractedItemId !in positiveItems ||
                    it.extractedItemId?.let { id ->
                        decisions[id]?.decision?.productId?.let { productId ->
                            current.menuItems.any { row ->
                                row.barId == job.barId && row.productId == productId
                            }
                        }
                    } == true) "ignore" else "apply",
            )
        }
        val result = remote.reviewAndApply(importId,
            com.zerotoone.bottlemap.network.ReviewAndApplyRequestDto(
                reviewVersion = version,
                itemDecisions = itemDecisions,
                changeDecisions = changes,
            ))
        // The review already succeeded: never show a retryable "publish failed" for
        // post-publish menu writes, because review-and-apply cannot be replayed.
        val extra = try {
            publishPriceEntryOnlyRows(current, job, missingOptionLineIds)
        } catch(cancelled: CancellationException) {
            throw cancelled
        } catch(error: Exception) {
            Triple(0, 0, listOf("가격 입력 메뉴를 자동 추가하지 못했어요. 직접 확인해 주세요."))
        }
        val warnings = try {
            extra.third + updatePreviouslyListedPrices(current, job)
        } catch(cancelled: CancellationException) {
            throw cancelled
        } catch(error: Exception) {
            extra.third + listOf("메뉴 게시 후 일부 기존 메뉴 가격을 확인하지 못했어요. 직접 확인해 주세요.")
        }
        publishSnapshot(current.copy(imports = current.imports.map {
            if(it.menuImportId == importId) it.copy(status = MockImportStatus.APPLIED,
                publishedAddedCount = result.result.added + extra.first,
                publishedNewProductCount = result.result.createdProducts + extra.second)
            else it
        }))
        val refreshError = runCatching { refresh() }.exceptionOrNull()
        lastPublishWarning = (warnings + listOfNotNull(
            refreshError?.let { "게시 후 최신 메뉴를 새로고침하지 못했어요." }
        )).distinct().take(3).joinToString("\n").ifEmpty { null }
        return result.result.added + extra.first
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
    private fun operatingExceptionBody(exception: MockOperatingException):
        Map<String, Any?> {
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
        return fields
    }

    suspend fun applyOperatingExceptionLive(barId: String, exception: MockOperatingException) =
        confirmedWrite { remote.setOperatingException(barId, operatingExceptionBody(exception)) }

    suspend fun cancelOperatingExceptionLive(barId: String) =
        confirmedWrite { remote.removeOperatingException(barId) }

    override fun applyOperatingException(barId: String, exception: MockOperatingException) {
        write { remote.setOperatingException(barId, operatingExceptionBody(exception)) }
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
    override fun cancelPhotoImport(importId: String) {
        write {
            remote.cancelMenuImport(importId)
            val before = snapshot()
            publishSnapshot(before.copy(imports = before.imports.map {
                if(it.menuImportId == importId)
                    it.copy(status = MockImportStatus.CANCELED) else it
            }))
        }
    }
    override fun discardPhotoImport(importId: String) = cancelPhotoImport(importId)
    override fun resetPhotoReview(importId: String, expectedVersion: Int) {
        val before = snapshot()
        val job = before.imports.firstOrNull { it.menuImportId == importId }
            ?: error("메뉴판 작업을 찾지 못했어요.")
        require(job.reviewVersion == expectedVersion) { "REVIEW_OUTDATED" }
        val reset = job.copy(images = job.images.map { image ->
            image.copy(lines = image.lines.map { line ->
                if(line.mockAutoAccepted || (line.kind == MockLineKind.NON_PRODUCT &&
                    line.decision?.kind == MockDecisionKind.CONFIRM_NON_PRODUCT)) line
                else line.copy(decision = null)
            })
        })
        publishSnapshot(before.copy(imports = before.imports.map {
            if(it.menuImportId == importId) reset else it
        }))
    }
    override fun retryFailedPhotoImport(importId: String): String =
        error("사진을 다시 선택해 등록해 주세요.")
    override fun decideLine(
        importId: String, extractedItemId: String, expectedVersion: Int,
        decision: MockReviewDecision,
    ) {
        // Stage 8 edits are an uncommitted local review draft, not a server-side action.
        // The server accepts the complete set of decisions at review-and-apply.
        val job=snapshot().imports.firstOrNull { it.menuImportId==importId }
            ?: error("메뉴판 작업이 없어요.")
        val originalLine = job.images.flatMap { it.lines }.firstOrNull {
            it.extractedItemId == extractedItemId
        } ?: error("검수 항목을 찾지 못했어요.")
        decision.correctedOptions?.forEach { edited ->
            val extracted = originalLine.options.firstOrNull { it.optionId == edited.optionId }
            if(extracted != null) {
                validateReviewOptionClearing(edited, extracted)
            }
        }
        val targets=if(decision.kind==MockDecisionKind.EXCLUDE)
            relatedPhotoProductLineIds(job,extractedItemId)
        else listOf(extractedItemId)
        targets.forEach { id ->
            local.decideLine(importId,id,expectedVersion,decision)
        }
        lastReadySnapshot = snapshot()
    }
    override fun publishAddOnly(importId: String, expectedVersion: Int): Int =
        error("서버 사진 검수를 완료해야 합니다.")
    override fun preview(barId: String, nowEpochMs: Long): MockPreview? =
        local.preview(barId, nowEpochMs)
}
