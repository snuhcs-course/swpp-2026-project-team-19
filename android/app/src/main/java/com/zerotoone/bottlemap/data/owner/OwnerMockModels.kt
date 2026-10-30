package com.zerotoone.bottlemap.data.owner

/**
 * LOCAL MOCK DOMAIN ONLY, not API DTOs. Contract: docs/frontend_backend_api_spec.md.
 * The unagreed fields (photos, tags, schedules, discounts, stock and manual menu CRUD)
 * must never be serialized as requests to the current backend.
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
    val nextLocalId: Long = 1L,
)

data class MockBar(
    val barId: String,
    val name: String,
    val address: String,
    val phone: String? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
    val description: String? = null, // C38 unagreed
    val gallery: List<MockPhoto> = emptyList(), // C39 unagreed; first = cover in mock
    val tags: List<String> = emptyList(), // C40 unagreed
    val weeklyHours: List<MockWeeklyHours> = emptyList(), // C41 unagreed
    val exceptions: List<MockOperatingException> = emptyList(), // C42 unagreed
    val defaultPourMl: Int? = null, // R16 unagreed
    val lastVerifiedAtEpochMs: Long? = null, // C11 unagreed
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
    val businessNumberDigits: String = "",
    val representativeName: String = "",
    val openingDateIso: String = "",
    val contactPhone: String = "",
    val applicantGallery: List<MockPhoto> = emptyList(),
    val initialMenuPhotos: List<MockPhoto> = emptyList(),
)

enum class MockApplicationStatus { PENDING, APPROVED, REJECTED, CANCELED }
enum class MockApplicationKind { NEW_BAR, EXISTING_BAR }
data class MockOwnerApplication(
    val applicationId: String,
    val kind: MockApplicationKind,
    val status: MockApplicationStatus,
    val proposedBarName: String,
    val barId: String? = null,
    val representativeName: String? = null,
    val openingDateIso: String? = null,
    val contactPhone: String? = null,
    val submittedAtEpochMs: Long = 0L,
    val registrationPhotos: List<MockPhoto> = emptyList(), // C05 unagreed
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
)

enum class MockImportStatus { PROCESSING, READY_FOR_REVIEW, FAILED, APPLIED }
enum class MockLineKind { PRODUCT, NON_PRODUCT, UNKNOWN }
enum class MockDecisionKind { SELECT_PRODUCT, EXCLUDE, CONFIRM_NON_PRODUCT }
data class MockReviewDecision(
    val kind: MockDecisionKind,
    val productId: String? = null,
    val correctedOptions: List<MockMenuOption>? = null,
)

data class MockExtractedLine(
    val extractedItemId: String,
    val sourceText: String,
    val kind: MockLineKind,
    val suggestedProductId: String? = null,
    val candidateProductIds: List<String> = emptyList(),
    val options: List<MockMenuOption> = emptyList(),
    val decision: MockReviewDecision? = null,
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
    val failureReason: String? = null,
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
