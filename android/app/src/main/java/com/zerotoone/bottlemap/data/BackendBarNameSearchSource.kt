// Backend PR #54 / API spec 3.11.11. Public global registered bar lookup.
package com.zerotoone.bottlemap.data

import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.BarNamesResponseDto

class BackendBarNameSearchSource : MapPlaceSearchSource {
    override suspend fun search(query: String): List<MapPlace> {
        require(query.isNotBlank() && query.length <= 100)
        val response = ApiClient.call { ApiClient.api.searchBarNames(query = query, limit = 20) }
        return response.toMapPlaces()
    }
}

/** Backend returns active bars, name-sorted; preserve order, no local name filtering. */
internal fun BarNamesResponseDto.toMapPlaces(): List<MapPlace> {
    val ids = HashSet<String>()
    return items.mapNotNull { dto ->
        require(dto.barId.isNotBlank()) { "Missing registered bar ID" }
        val pos = NearbyCoordinate(dto.latitude, dto.longitude)
        require(pos.isValid()) { "Invalid registered bar coordinates" }
        if (!ids.add(dto.barId)) return@mapNotNull null
        MapPlace(dto.name, dto.address, pos, dto.barId)
    }
}
