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

/** First match registered active bars anywhere; fallback to device place geocoder. */
class CombinedMapPlaceSearchSource(
    private val registeredBars: MapPlaceSearchSource,
    private val genericPlaces: MapPlaceSearchSource,
) : MapPlaceSearchSource {
    override suspend fun search(query: String): List<MapPlace> {
        val bars = registeredBars.search(query)
        return if (bars.isNotEmpty()) bars else genericPlaces.search(query)
    }
}

/** Geographic guard for the Korea-only customer map lookup.
 * This is NOT a country polygon; islands/border cases remain provider-dependent.
 */
internal fun isInKoreaMapBounds(coordinate: NearbyCoordinate): Boolean =
    coordinate.isValid() &&
        coordinate.latitude in 33.0..39.0 &&
        coordinate.longitude in 124.0..132.0

internal fun sanitizePlaces(places: List<MapPlace>): List<MapPlace> =
    places.asSequence()
        .filter { it.name.isNotBlank() && isInKoreaMapBounds(it.coordinate) }
        .distinctBy { it.name to it.coordinate }
        .take(5)
        .toList()
