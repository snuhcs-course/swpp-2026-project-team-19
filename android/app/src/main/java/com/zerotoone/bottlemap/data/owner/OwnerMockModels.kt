package com.zerotoone.bottlemap.data.owner

/**
 * LOCAL MOCK DOMAIN ONLY, not API DTOs. Contract: docs/frontend_backend_api_spec.md.
 * Most features now have HTTP counterparts, but these local models are never
 * wire DTOs: map only fields confirmed in the latest repo contract explicitly.
 * See android/OWNER_REGISTRATION_API_INTEGRATION_HANDOFF.md.
 */
data class MockOwnerSnapshot(
    val bars: List<MockBar> = emptyList(),
    val applications: List<MockOwnerApplication> = emptyList(),
    val registrationDraft: MockRegistrationDraft? = null,
    val brands: List<MockBrand> = emptyList(),
    val products: List<MockCatalogProduct> = emptyList(),
    val menuItems: List<MockBarMenuItem> = emptyList(),
    val imports: List<MockMenuImport> = emptyList(),
    val selectedBarId: String? = null,
    val dismissedApplicationIds: Set<String> = emptySet(), // local-only hidden rejected cards
    val existingBarCandidates: List<MockBar> = emptyList(), // Local-only discovery fixtures, not owned bars
    val nextLocalId: Long = 1L,
    // Local Mock tombstones: canonical bar + product retains its menu-item ID after deletion/reset.
    val menuItemIdHistory: Map<String, String> = emptyMap(),
)

data class MockBar(
    val barId: String,
    val name: String,
    val address: String,
    val phone: String? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
    val description: String? = null, // C38 unagreed
    val gallery: List<MockPhoto> = emptyList(), // local photo references, not API photo URLs; first = cover in Mock
    val tags: List<String> = emptyList(), // local representation; map explicitly to API §3.7
    val weeklyHours: List<MockWeeklyHours> = emptyList(), // local representation; map explicitly to API §3.7
    val exceptions: List<MockOperatingException> = emptyList(), // local representation; map explicitly to API §3.15
    val defaultPourMl: Int? = null, // local representation; map explicitly to API §3.7
    val lastVerifiedAtEpochMs: Long? = null, // Owner confirmed the currently sold menu
    val lastMenuPublishedAtEpochMs: Long? = null, // Independent from owner verification; local Mock only
)

enum class MockPhotoKind { BAR_GALLERY, MENU_CAPTURE, REGISTRATION_ATTACHMENT }
data class MockPhoto(val photoId: String, val uri: String, val kind: MockPhotoKind)

/**
 * Local form draft only. These fields must never be sent to an unagreed API.
 * App-private Mock preferences are NOT suitable for real applicant PII.
 */
data class MockRegistrationDraft(
    val kind: MockApplicationKind = MockApplicationKind.NEW_BAR,
    val existingBarId: String? = null,
    val proposedBarName: String = "",
    val proposedBarAddress: String = "", // 3.11.2 required for new_bar; local-only draft
    val proposedBarAddressDetail: String = "", // Mock-only optional address line
    val businessNumberDigits: String = "",
    val representativeName: String = "",
    val openingDateIso: String = "",
    val contactPhone: String = "",
    val storePhone: String = "", // local-only public shop phone
    val certificatePhoto: MockPhoto? = null, // Mock-only stored reference to registration certificate
    val applicantGallery: List<MockPhoto> = emptyList(),
    val initialMenuPhotos: List<MockPhoto> = emptyList(),
    val resumePageKey: String? = null, // Local UI checkpoint; no Backend field
)

enum class MockApplicationStatus { PENDING, APPROVED, REJECTED, CANCELED }
enum class MockApplicationKind { NEW_BAR, EXISTING_BAR }
data class MockOwnerApplication(
    val applicationId: String,
    val kind: MockApplicationKind,
    val status: MockApplicationStatus,
    val proposedBarName: String,
    val barId: String? = null,
    val proposedBarAddress: String? = null, // new_bar only; null for existing_bar
    val representativeName: String? = null,
    // Local copy of the submitted number. API §3.11.1 has a separate
    // businessRegistrationNumber field; never store production applicant PII here.
    val businessNumberDigits: String? = null,
    val openingDateIso: String? = null,
    val contactPhone: String? = null,
    val storePhone: String? = null, // local-only public phone
    val rejectionReason: String? = null, // Local fixture; API §3.11.1 also has rejectionReason
    val submittedAtEpochMs: Long = 0L, // local time; API uses createdAt/reviewedAt RFC 3339
    val registrationPhotos: List<MockPhoto> = emptyList(), // Mock union; API §3.11.15 is menuPhotos only
    val reviewedAtEpochMs: Long? = null, // local analog of API §3.11.1 reviewedAt (not wire DTO)
)

/** Product ID is a catalog identity, never a menu row ID. */
data class MockBrand(val brandId: String, val name: String)
data class MockCatalogProduct(
    val productId: String,
    val brandId: String,
    val displayName: String,
    val category: String = "whisky",
    val ageYears: Int? = null,
    val editionName: String? = null,
    // Local manual-menu state only. Never infer a verified catalog match from a name.
    val catalogMatched: Boolean = true,
    val otherAlcoholKind: String? = null,
    val abvPercent: Double? = null, // local review draft; not a backend DTO
    val isActive: Boolean = true,
)

data class MockDiscount(
    val discountedPriceKrw: Int,
    val startAtEpochMs: Long,
    val endAtEpochMs: Long,
) {
    fun effectivePrice(listPriceKrw: Int, nowEpochMs: Long): Int =
        if (nowEpochMs >= startAtEpochMs && nowEpochMs < endAtEpochMs) discountedPriceKrw else listPriceKrw
}

/** optionId is distinct from barMenuItemId and productId. Null pour is valid for Bottle. */
data class MockMenuOption(
    val optionId: String,
    val label: String? = null,
    val pourMl: Int? = null,
    val priceKrw: Int,
    val discount: MockDiscount? = null, // C10 unagreed
) {
    fun identityKey(): String = "${label.orEmpty().trim().lowercase()}|${pourMl ?: "-"}"
    fun displayPrice(nowEpochMs: Long): Int = discount?.effectivePrice(priceKrw, nowEpochMs) ?: priceKrw
}

/** One bar+canonical product -> one menu row with multiple option IDs. */
data class MockBarMenuItem(
    val barMenuItemId: String,
    val barId: String,
    val productId: String,
    val options: List<MockMenuOption>,
    val soldOut: Boolean = false, // C09 unagreed
    // Local-only bar-facing label. Canonical catalog displayName remains unchanged.
    val displayNameOverride: String? = null,
)

data class MockWeeklyHours(
    val isoDayOfWeek: Int, // 1=Mon .. 7=Sun, mock-only
    val closed: Boolean,
    val openMinutes: Int? = null,
    val closeMinutes: Int? = null,
    val closesNextDay: Boolean = false,
)
enum class MockExceptionKind { CLOSED_TODAY, CUSTOM_HOURS, VACATION }
data class MockOperatingException(
    val exceptionId: String,
    val kind: MockExceptionKind,
    val fromEpochDay: Long,
    val toEpochDay: Long,
    val note: String? = null,
    val openMinutes: Int? = null,
    val closeMinutes: Int? = null,
    val closesNextDay: Boolean = false, // local-only overnight temporary hours
)

enum class MockImportStatus { UPLOADED, PROCESSING, READY_FOR_REVIEW, FAILED, APPLIED, CANCELED }
enum class MockLineKind { PRODUCT, NON_PRODUCT, UNKNOWN }
enum class MockDecisionKind { SELECT_PRODUCT, CREATE_PRODUCT, EXCLUDE, CONFIRM_NON_PRODUCT }
/** Explicitly owner-entered mock catalog draft, never inferred from the OCR text. */
data class MockNewProductDraft(
    val name: String,
    val brandId: String? = null,
    val brandName: String? = null,
    val category: String = "whisky",
    val ageYears: Int? = null,
    val editionName: String? = null,
    val abvPercent: Double? = null,
    val otherAlcoholKind: String? = null,
)
data class MockReviewDecision(
    val kind: MockDecisionKind,
    val productId: String? = null,
    val correctedOptions: List<MockMenuOption>? = null,
    val newProduct: MockNewProductDraft? = null,
    val displayNameOverride: String? = null,
)

data class MockExtractedLine(
    val extractedItemId: String,
    val sourceText: String,
    val kind: MockLineKind,
    val suggestedProductId: String? = null,
    val candidateProductIds: List<String> = emptyList(),
    val options: List<MockMenuOption> = emptyList(),
    val decision: MockReviewDecision? = null,
    // Stage 8: this option's 0 price means manual entry is required, never 0 KRW.
    val needsPriceEntry: Boolean = false,
    val sourceBox: List<Int>? = null, // EXIF-normalized 0..1000 coordinates, null means unknown
    // Explicit local fixture-only exact catalog match. No OCR or backend inference.
    val mockAutoAccepted: Boolean = false,
)
data class MockPhotoExtraction(
    val imageId: String,
    val sourceUri: String,
    val imageOrder: Int,
    val lines: List<MockExtractedLine>,
)
data class MockMenuImport(
    val menuImportId: String,
    val barId: String,
    val status: MockImportStatus,
    val reviewVersion: Int,
    val images: List<MockPhotoExtraction>,
    // Populated by the backend import list/processing response, even after process death.
    val imageCount: Int = 0,
    val failureReason: String? = null,
    // Local Mock publication result: deduplicated actual new bar menu rows.
    val publishedAddedCount: Int? = null,
    // Actual number of distinct canonical products created during this Mock publish.
    val publishedNewProductCount: Int? = null,
)

/**
 * A fixture source is explicitly keyed by the selected image URI. Unknown photos produce
 * no extracted lines; we never pretend that a random image contains seven fixed whiskies.
 */
fun interface MockPhotoExtractionSource {
    fun linesFor(selectedImageUri: String): List<MockExtractedLine>
}

data class MockPreview(
    val bar: MockBar,
    val visibleMenu: List<MockBarMenuItem>,
    val products: List<MockCatalogProduct>,
    val generatedAtEpochMs: Long,
) {
    fun displayedPrice(option: MockMenuOption): Int = option.displayPrice(generatedAtEpochMs)
}

sealed interface MockOwnerLoadState {
    data object Loading : MockOwnerLoadState
    data class Ready(val snapshot: MockOwnerSnapshot) : MockOwnerLoadState
    data class Empty(val snapshot: MockOwnerSnapshot = MockOwnerSnapshot()) : MockOwnerLoadState
    data class Error(val message: String) : MockOwnerLoadState
}

fun MockOwnerSnapshot.asLoadState(): MockOwnerLoadState =
    if (bars.isEmpty() && applications.isEmpty() && imports.isEmpty() && registrationDraft == null)
        MockOwnerLoadState.Empty(this) else MockOwnerLoadState.Ready(this)

/** Entry routing is a local Owner UI policy; no server status is inferred. */
fun MockOwnerSnapshot.openSingleBarManager(): Boolean =
    bars.size == 1 && registrationDraft == null &&
        applications.none { it.applicationId !in dismissedApplicationIds &&
            it.status in listOf(MockApplicationStatus.PENDING, MockApplicationStatus.REJECTED) }

/** Local display readiness; never maps directly to Backend active/inactive. */
fun MockOwnerSnapshot.hasPublishedInitialReview(barId: String): Boolean =
    imports.any { it.barId == barId && it.status == MockImportStatus.APPLIED } &&
        menuItems.any { it.barId == barId }
