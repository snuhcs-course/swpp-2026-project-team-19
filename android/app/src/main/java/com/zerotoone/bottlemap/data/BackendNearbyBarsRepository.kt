// AI-assisted Android frontend integration, 2026-10-18, Backend A9 PR #43 (spec 3.12).
package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.NearbyBarsResponseDto

/**
 * Public, no Authorization. Backend returns ALL active bars within the radius
 * (no pagination) and their authoritative rounded integer meter distances.
 */
class BackendNearbyBarsRepository : NearbyBarsSource {
    override suspend fun listNearbyBars(origin: NearbyCoordinate): List<NearbyBar> {
        require(origin.isValid()) { "Invalid user location" }
        val response = ApiClient.call {
            ApiClient.api.getNearbyBars(
                latitude = origin.latitude,
                longitude = origin.longitude,
                radiusMeters = 500,
            )
        }
        return response.toNearbyBars()
    }
}

/**
 * Preserve server order and server-computed distance.
 * Do not re-run Haversine/filter/sort: Backend rounds before testing <=500m.
 * Duplicate IDs are not displayed twice. Malformed data fails explicitly
 * rather than showing an incomplete response as a complete nearby catalog.
 */
internal fun NearbyBarsResponseDto.toNearbyBars(): List<NearbyBar> {
    val ids = HashSet<String>()
    return items.mapNotNull { dto ->
        require(dto.barId.isNotBlank()) { "Nearby bar missing ID" }
        val coordinate = NearbyCoordinate(dto.latitude, dto.longitude)
        require(coordinate.isValid()) { "Nearby bar invalid coordinates" }
        require(dto.distanceMeters in 0..500) { "Nearby bar invalid server distance" }
        if (!ids.add(dto.barId)) return@mapNotNull null
        NearbyBar(
            barId = dto.barId,
            name = dto.name,
            address = dto.address,
            location = coordinate,
            distanceMeters = dto.distanceMeters.toDouble(),
            menuUpdatedAt = dto.menuUpdatedAt,
        )
    }
}
