// Backend PR #54, API spec 3.13. The exact Kakao viewport replaces radius queries.
package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.MapBarsResponseDto

const val MAX_MAP_SPAN_DEGREES = 0.2
private const val MAP_SPAN_EPSILON = 1e-9

data class MapBounds(
    val south: Double,
    val west: Double,
    val north: Double,
    val east: Double,
) {
    init {
        require(south.isFinite() && north.isFinite() && west.isFinite() && east.isFinite())
        require(south in -90.0..90.0 && north in -90.0..90.0)
        require(west in -180.0..180.0 && east in -180.0..180.0)
        require(south <= north && west <= east) { "Invalid or antimeridian-crossing map bounds" }
    }

    fun isSupportedByBackend(): Boolean =
        north - south <= MAX_MAP_SPAN_DEGREES + MAP_SPAN_EPSILON &&
        east - west <= MAX_MAP_SPAN_DEGREES + MAP_SPAN_EPSILON

    fun isNearlySameAs(other: MapBounds): Boolean =
        kotlin.math.abs(south - other.south) < 0.00025 &&
        kotlin.math.abs(west - other.west) < 0.00025 &&
        kotlin.math.abs(north - other.north) < 0.00025 &&
        kotlin.math.abs(east - other.east) < 0.00025
}

/** Need all four corners: a missing native camera extent cannot be silently guessed. */
fun mapBoundsFromCorners(corners: List<NearbyCoordinate>): MapBounds? {
    if (corners.size != 4 || corners.any { !it.isValid() }) return null
    return MapBounds(
        south = corners.minOf { it.latitude },
        west = corners.minOf { it.longitude },
        north = corners.maxOf { it.latitude },
        east = corners.maxOf { it.longitude },
    )
}

interface MapBarsSource {
    suspend fun listMapBars(bounds: MapBounds): List<MapBar>
}

class BackendMapBarsRepository : MapBarsSource {
    override suspend fun listMapBars(bounds: MapBounds): List<MapBar> {
        require(bounds.isSupportedByBackend()) { "Map viewport exceeds API 0.2 degree limit" }
        val response = ApiClient.call {
            ApiClient.api.getMapBars(
                south = bounds.south,
                west = bounds.west,
                north = bounds.north,
                east = bounds.east,
            )
        }
        return response.toMapBars()
    }
}

/** Server includes edges and sorts by barId. Do not locally sort/re-filter. */
internal fun MapBarsResponseDto.toMapBars(): List<MapBar> {
    val ids = HashSet<String>()
    return items.mapNotNull { dto ->
        require(dto.barId.isNotBlank()) { "Map bar missing ID" }
        val coord = NearbyCoordinate(dto.latitude, dto.longitude)
        require(coord.isValid()) { "Map bar invalid coordinates" }
        if (!ids.add(dto.barId)) return@mapNotNull null
        MapBar(dto.barId, dto.name, dto.address, coord, dto.menuUpdatedAt)
    }
}
