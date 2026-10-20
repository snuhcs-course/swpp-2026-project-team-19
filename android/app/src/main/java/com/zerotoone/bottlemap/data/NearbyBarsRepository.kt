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
    val menuUpdatedAt: String? = null,
)

const val NEARBY_CAROUSEL_RADIUS_METERS = 1000
const val MAX_NEARBY_API_RADIUS_METERS = 3000
const val NEARBY_RADIUS_METERS = NEARBY_CAROUSEL_RADIUS_METERS.toDouble()
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
 * Pure Haversine domain utility for deterministic distance boundary tests.
 * NOT used on Backend A9 results: the server includes bars based on rounded
 * integer meters, so a local floating-point filter would wrongly omit them.
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
 * Production A9 source returns a COMPLETE server-filtered, server-sorted catalog.
 * Never re-filter raw distances on Android; server rounds to integer meters.
 */
interface NearbyBarsSource {
    suspend fun listNearbyBars(origin: NearbyCoordinate): List<NearbyBar>

    /** Allows viewport queries without changing the existing A7 test-double contract. */
    suspend fun listNearbyBars(origin: NearbyCoordinate, radiusMeters: Int): List<NearbyBar> =
        listNearbyBars(origin)
}
