package com.zerotoone.bottlemap.data

/**
 * A search result from the device's map-name geocoder. Never confuse these
 * locations with Backend bars: they have no BottleMap barId or menu.
 */
data class MapPlace(
    val name: String,
    val address: String,
    val coordinate: NearbyCoordinate,
)

interface MapPlaceSearchSource {
    /** One explicit user-submitted query; never run per keystroke. */
    suspend fun search(query: String): List<MapPlace>
}

internal fun sanitizePlaces(places: List<MapPlace>): List<MapPlace> =
    places.asSequence()
        .filter { it.name.isNotBlank() && it.coordinate.isValid() &&
            !(it.coordinate.latitude == 0.0 && it.coordinate.longitude == 0.0) }
        .distinctBy { it.name to it.coordinate }
        .take(5)
        .toList()
