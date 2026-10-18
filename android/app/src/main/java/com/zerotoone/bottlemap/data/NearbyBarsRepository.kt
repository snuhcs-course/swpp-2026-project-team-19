// AI-assisted Android frontend foundation (2026-10-18, I2-A7/A8).
package com.zerotoone.bottlemap.data

import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/** WGS84. No user coordinates are persisted, logged or sent to analytics. */
data class NearbyCoordinate(val latitude: Double, val longitude: Double) {
    fun isValid(): Boolean = latitude.isFinite() && longitude.isFinite() &&
        latitude in -90.0..90.0 && longitude in -180.0..180.0
}

/**
 * Internal frontend projection, NOT an API response DTO. Backend owner must
 * provide a complete public nearby-bar query before a live source can exist.
 */
data class NearbyBarCandidate(
    val barId: String,
    val name: String,
    val address: String,
    val location: NearbyCoordinate?,
)

data class NearbyBar(
    val barId: String,
    val name: String,
    val address: String,
    val location: NearbyCoordinate,
    val distanceMeters: Double,
)

const val NEARBY_RADIUS_METERS = 500.0
private const val EARTH_RADIUS_METERS = 6_371_000.0

/** Pure, deterministic Haversine distance; lat FIRST, lng SECOND. */
fun distanceMeters(from: NearbyCoordinate, to: NearbyCoordinate): Double {
    require(from.isValid() && to.isValid()) { "Invalid WGS84 coordinates" }
    val fromLat = Math.toRadians(from.latitude)
    val toLat = Math.toRadians(to.latitude)
    val deltaLat = Math.toRadians(to.latitude - from.latitude)
    val deltaLng = Math.toRadians(to.longitude - from.longitude)
    val a = sin(deltaLat / 2).pow(2) +
        cos(fromLat) * cos(toLat) * sin(deltaLng / 2).pow(2)
    return 2 * EARTH_RADIUS_METERS * asin(min(1.0, sqrt(a)))
}

/**
 * Caller must supply the COMPLETE active-bar catalog for the user vicinity,
 * not truncated/paginated product search results. Stable distance then ID sort.
 */
fun filterNearbyBars(
    origin: NearbyCoordinate,
    candidates: List<NearbyBarCandidate>,
    radiusMeters: Double = NEARBY_RADIUS_METERS,
): List<NearbyBar> {
    require(origin.isValid())
    require(radiusMeters.isFinite() && radiusMeters >= 0)
    return candidates.asSequence()
        .filter { it.barId.isNotBlank() && it.location?.isValid() == true }
        .map { item ->
            NearbyBar(
                barId = item.barId,
                name = item.name,
                address = item.address,
                location = requireNotNull(item.location),
                distanceMeters = distanceMeters(origin, item.location),
            )
        }
        .filter { it.distanceMeters <= radiusMeters + 1e-6 }
        .sortedWith(compareBy<NearbyBar> { it.distanceMeters }.thenBy { it.barId })
        .distinctBy { it.barId }
        .toList()
}

interface NearbyLocationSource {
    /** Single foreground precise location fix, no continuous tracking. */
    suspend fun currentLocation(): NearbyCoordinate
}

/**
 * Must return EVERY active bar that could be inside 500 m, including full
 * pagination. Returning a product-search subset is a correctness violation.
 */
interface NearbyBarsSource {
    suspend fun listNearbyCandidates(origin: NearbyCoordinate): List<NearbyBarCandidate>
}

class NearbyContractUnavailableException : IllegalStateException(
    "공개 주변 바 목록 API 계약이 아직 없습니다. Backend 담당자의 Nearby 조회 API가 필요합니다.",
)

/**
 * Production-safe placeholder: fail explicitly instead of presenting a
 * partial search dataset as all bars within 500m.
 */
object AwaitingPublicNearbyApi : NearbyBarsSource {
    override suspend fun listNearbyCandidates(origin: NearbyCoordinate): List<NearbyBarCandidate> {
        throw NearbyContractUnavailableException()
    }
}
