package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.network.NearbyBarsResponseDto

/**
 * Public bar metadata is shared with map discovery. Origin and radius are
 * applied only on this device (spec 3.19.4); neither reaches the network.
 */
class BackendNearbyBarsRepository(
    private val allBars: AllBarsRepository = Repositories.allBars,
) : NearbyBarsSource {
    override suspend fun listNearbyBars(origin: NearbyCoordinate): List<NearbyBar> =
        listNearbyBars(origin, NEARBY_CAROUSEL_RADIUS_METERS)

    override suspend fun listNearbyBars(origin: NearbyCoordinate, radiusMeters: Int): List<NearbyBar> {
        require(origin.isValid()) { "Invalid map or user coordinate" }
        require(radiusMeters in 1..MAX_NEARBY_API_RADIUS_METERS) { "Unsupported nearby radius" }
        return allBars.listBars().map { bar ->
            NearbyBar(bar.barId, bar.name, bar.address, bar.location,
                roundedDistanceMeters(origin, bar.location).toDouble(), bar.menuUpdatedAt)
        }.filter { it.distanceMeters <= radiusMeters }
            .sortedWith(compareBy<NearbyBar> { it.distanceMeters }.thenBy { it.barId })
    }
}

/**
 * Legacy spec 3.12 DTO decoder, retained for backwards contract coverage.
 * Production discovery uses the complete spec 3.19 list above.
 * Preserve server order and server-computed distance.
 * Do not re-run Haversine/filter/sort: Backend rounds before testing <=radiusMeters.
 * Duplicate IDs are not displayed twice. Malformed data fails explicitly
 * rather than showing an incomplete response as a complete nearby catalog.
 */
internal fun NearbyBarsResponseDto.toNearbyBars(radiusMeters: Int = NEARBY_CAROUSEL_RADIUS_METERS): List<NearbyBar> {
    require(radiusMeters in 1..MAX_NEARBY_API_RADIUS_METERS)
    val ids = HashSet<String>()
    return items.mapNotNull { dto ->
        require(dto.barId.isNotBlank()) { "Nearby bar missing ID" }
        val coordinate = NearbyCoordinate(dto.latitude, dto.longitude)
        require(coordinate.isValid() && !(coordinate.latitude == 0.0 && coordinate.longitude == 0.0)) {
            "Nearby bar invalid coordinates"
        }
        require(dto.distanceMeters in 0..radiusMeters) { "Nearby bar invalid server distance" }
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
