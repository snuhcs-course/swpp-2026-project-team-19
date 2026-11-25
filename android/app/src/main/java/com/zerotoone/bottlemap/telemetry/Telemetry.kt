package com.zerotoone.bottlemap.telemetry

interface Telemetry {
    fun log(event: TelemetryEvent)
    fun setEnabled(enabled: Boolean)
    fun setScreen(route: ScreenRoute)
}

object NoOpTelemetry : Telemetry {
    override fun log(event: TelemetryEvent) = Unit
    override fun setEnabled(enabled: Boolean) = Unit
    override fun setScreen(route: ScreenRoute) = Unit
}

object AppTelemetry {
    @Volatile var current: Telemetry = NoOpTelemetry
}

/** Only enum/Boolean/bucket values can cross the collection boundary. */
sealed interface TelemetryEvent {
    data class SearchCompleted(val kind: SearchKind, val hasResults: Boolean) : TelemetryEvent
    data class BarDetailOpened(val source: DetailSource, val secondsSinceSearch: SearchTime? = null) : TelemetryEvent
    data class MenuImportStarted(val source: ImportSource, val photos: PhotoCount) : TelemetryEvent
    data class MenuImportFailed(val stage: ImportStage, val errorCode: ErrorCode) : TelemetryEvent
    data object MenuReviewOpened : TelemetryEvent
    data class MenuPublished(val neededCheck: CheckCount, val minutes: ReviewTime) : TelemetryEvent
    data class MenuPublishFailed(val errorCode: ErrorCode) : TelemetryEvent
    data class OwnerApplicationStarted(val type: ApplicationType) : TelemetryEvent
    data class OwnerApplicationSubmitted(val type: ApplicationType) : TelemetryEvent
    data class OwnerApplicationFailed(val errorCode: ErrorCode) : TelemetryEvent
    data class NearbyOpened(val permission: Permission) : TelemetryEvent
    data class SignInResult(val entry: SignInEntry, val result: SignInStatus) : TelemetryEvent
    data object ReportProblemOpened : TelemetryEvent
    data class ApiError(val endpoint: ApiEndpoint, val httpStatus: HttpStatus, val code: ErrorCode) : TelemetryEvent
}

enum class SearchKind { PRODUCT, BRAND, BAR_NAME }
enum class DetailSource { SEARCH, NEARBY, MAP, POPULAR }
enum class ImportSource { CAMERA, GALLERY, PDF }
enum class ImportStage { UPLOAD, EXTRACTION }
enum class ApplicationType { CLAIM, NEW }
enum class Permission { GRANTED, DENIED }
enum class SignInEntry { WELCOME, ACCOUNT }
enum class SignInStatus { SUCCESS, CANCEL, ERROR }
enum class SearchTime { UNDER_30, FROM_30_TO_60, FROM_60_TO_180, FROM_180;
    companion object { fun fromMillis(ms: Long) = when {
        ms < 30_000 -> UNDER_30; ms < 60_000 -> FROM_30_TO_60
        ms < 180_000 -> FROM_60_TO_180; else -> FROM_180
    } }
}
enum class ReviewTime { UNDER_3, FROM_3_TO_10, FROM_10_TO_30, FROM_30;
    companion object { fun fromMillis(ms: Long) = when {
        ms < 180_000 -> UNDER_3; ms < 600_000 -> FROM_3_TO_10
        ms < 1_800_000 -> FROM_10_TO_30; else -> FROM_30
    } }
}
enum class PhotoCount { ONE, TWO_TO_FIVE, SIX_PLUS;
    companion object { fun from(count: Int) = when { count <= 1 -> ONE; count <= 5 -> TWO_TO_FIVE; else -> SIX_PLUS } }
}
enum class CheckCount { ZERO, ONE_TO_FIVE, SIX_PLUS;
    companion object { fun from(count: Int) = when { count <= 0 -> ZERO; count <= 5 -> ONE_TO_FIVE; else -> SIX_PLUS } }
}

/** Unknown server prose or codes are never copied into telemetry. */
enum class ErrorCode {
    NETWORK_ERROR, UNAUTHENTICATED, FORBIDDEN, VALIDATION_FAILED, NOT_FOUND,
    SERVICE_UNAVAILABLE, MENU_OUTDATED, REVIEW_OUTDATED, BAR_NOT_FOUND,
    PRODUCT_NOT_FOUND, IMPORT_NOT_READY, IMPORT_ALREADY_APPLIED, IMPORT_FAILED,
    EXTRACTION_FAILED, UPLOAD_FAILED, RATE_LIMITED, FILE_TOO_LARGE,
    UNSUPPORTED_MEDIA_TYPE, BUSINESS_VERIFICATION_FAILED, APPLICATION_ALREADY_PENDING,
    ACTIVE_IMPORT_EXISTS,
    BAR_OWNER_EXISTS,
    BAR_OWNER_NOT_FOUND,
    BUSINESS_NUMBER_UNREADABLE,
    BUSINESS_VERIFICATION_UNAVAILABLE,
    DUPLICATE_BRAND_FOUND,
    DUPLICATE_PRODUCT_FOUND,
    IDEMPOTENCY_KEY_REUSED,
    INVALID_APPLICATION_STATE,
    INVALID_APPLICATION_TYPE,
    INVALID_CHECK_STATE,
    INVALID_IMPORT_STATE,
    INVALID_REQUEST,
    MENU_IMPORT_NOT_FOUND,
    MENU_ITEM_CHECK_NOT_FOUND,
    MENU_ITEM_EXISTS,
    MENU_ITEM_NOT_FOUND,
    METHOD_NOT_ALLOWED,
    NO_PUBLISHED_MENU,
    OCR_UNAVAILABLE,
    OWNER_APPLICATION_EXISTS,
    OWNER_APPLICATION_NOT_FOUND,
    PHOTOS_OUTDATED,
    PHOTO_EXISTS,
    PHOTO_LIMIT_REACHED,
    PHOTO_NOT_FOUND,
    REVIEW_DRAFT_OUTDATED,
    REVIEW_DRAFT_TOO_LARGE,
    TEMPORARY_WRITE_CONFLICT,
    UNSUPPORTED_IMAGE_TYPE,
    UPLOAD_TOO_LARGE,
    USER_NOT_FOUND,
    INTERNAL_ERROR, UNKNOWN;
    companion object {
        fun from(raw: String?) = entries.firstOrNull { it.name == raw } ?: UNKNOWN
        fun from(error: Throwable) = when (error) {
            is com.zerotoone.bottlemap.network.BottleMapApiException -> from(error.code)
            is java.io.IOException -> NETWORK_ERROR
            else -> UNKNOWN
        }
    }
}

enum class HttpStatus(val value: Long) {
    NO_RESPONSE(0), BAD_REQUEST(400), UNAUTHORIZED(401), FORBIDDEN(403), NOT_FOUND(404), METHOD_NOT_ALLOWED(405),
    TIMEOUT(408), CONFLICT(409), TOO_LARGE(413), MEDIA_TYPE(415), VALIDATION(422),
    RATE_LIMIT(429), SERVER_ERROR(500), BAD_GATEWAY(502), UNAVAILABLE(503), GATEWAY_TIMEOUT(504), OTHER(-1);
    companion object { fun from(status: Int?) = entries.firstOrNull { it.value == status?.toLong() } ?: OTHER }
}

/** All values are route templates; neither an argument nor a query can be logged. */
enum class ScreenRoute(val template: String) {
    WELCOME("welcome"), ACCOUNT("account"), SIGN_IN("sign_in"), SEARCH("search"),
    RESULTS("search/results"), DETAIL("bar/{barId}"), MAP("map"),
    OWNER("owner"), REGISTRATION("owner/registration"), IMPORT("owner/import"), REVIEW("owner/review"), UNKNOWN("unknown");
    companion object {
        fun fromTemplate(route: String?): ScreenRoute {
            if (route == null) return UNKNOWN
            val path = route.substringBefore('?')
            return when {
                path.startsWith("owner/ux/registration") -> REGISTRATION
                path.contains("review") -> REVIEW
                path.contains("registration") || path.contains("onboarding") -> REGISTRATION
                path.contains("import") || path.contains("photo") || path.endsWith("/job") -> IMPORT
                path.contains("owner") -> OWNER
                path.contains("welcome") -> WELCOME
                path.contains("login") -> SIGN_IN
                path.contains("account") -> ACCOUNT
                path.contains("bar-detail") || path.contains("bar/{") -> DETAIL
                path.contains("nearby") || path.contains("map") -> MAP
                path.contains("results") -> RESULTS
                path.contains("search") -> SEARCH
                else -> UNKNOWN
            }
        }
    }
}

/** Ephemeral timings only; no query, ID or coordinates, never persisted across process death. */
class DiscoveryJourney(private val clock: () -> Long = { System.nanoTime() / 1_000_000 }) {
    private var source = DetailSource.SEARCH
    private var searchedAt: Long? = null
    fun searched(popular: Boolean = false, startedAt: Long = clock()) {
        source = if (popular) DetailSource.POPULAR else DetailSource.SEARCH
        searchedAt = if (popular) null else startedAt
    }
    fun fromMap(nearby: Boolean = false) {
        source = if (nearby) DetailSource.NEARBY else DetailSource.MAP
        searchedAt = null
    }
    fun detailOpened() = TelemetryEvent.BarDetailOpened(source,
        if (source == DetailSource.SEARCH) searchedAt?.let { SearchTime.fromMillis((clock() - it).coerceAtLeast(0)) } else null)
}
object AppDiscoveryJourney { val current = DiscoveryJourney() }
