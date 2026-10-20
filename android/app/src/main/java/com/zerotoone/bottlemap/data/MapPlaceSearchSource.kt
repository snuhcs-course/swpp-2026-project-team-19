package com.zerotoone.bottlemap.data

/** Map lookup result; barId is present only for nearby Backend-listed BottleMap bars. */
data class MapPlace(
    val name: String,
    val address: String,
    val coordinate: NearbyCoordinate,
    val barId: String? = null,
)

interface MapPlaceSearchSource {
    /** One explicit user-submitted query; never run per keystroke. */
    suspend fun search(query: String): List<MapPlace>
}

/** Geographic guard for the Korea-only customer map lookup.
 * This is NOT a country polygon; islands/border cases remain provider-dependent.
 */
internal fun isInKoreaMapBounds(coordinate: NearbyCoordinate): Boolean =
    coordinate.isValid() &&
        coordinate.latitude in 33.0..39.0 &&
        coordinate.longitude in 124.0..132.0

/** Search only already-fetched Backend bars; no unimplemented bar-name endpoint. */
internal fun findRegisteredBarPlaces(query: String, bars: List<NearbyBar>): List<MapPlace> {
    val keyword = query.trim()
    if (keyword.isBlank()) return emptyList()
    return bars.asSequence()
        .filter { it.barId.isNotBlank() && isInKoreaMapBounds(it.location) &&
            (it.name.contains(keyword, ignoreCase = true) ||
                it.address.contains(keyword, ignoreCase = true)) }
        .distinctBy { it.barId }
        .map { MapPlace(it.name, it.address, it.location, barId = it.barId) }
        .take(5)
        .toList()
}

internal fun sanitizePlaces(places: List<MapPlace>): List<MapPlace> =
    places.asSequence()
        .filter { it.name.isNotBlank() && isInKoreaMapBounds(it.coordinate) }
        .distinctBy { it.name to it.coordinate }
        .take(5)
        .toList()
