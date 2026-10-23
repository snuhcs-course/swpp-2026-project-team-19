package com.zerotoone.bottlemap.ui.customer

/**
 * Derived strictly from the bar menu API response, not a mock location.
 * Later A7/A8 can use lists of these targets for multiple markers.
 */
data class BarMapTarget(
    val barId: String,
    val name: String,
    val address: String,
    val latitude: Double,
    val longitude: Double,
)

internal fun validatedBarLocation(bar: BarDetailUiModel): BarMapTarget? {
    val latitude = bar.latitude ?: return null
    val longitude = bar.longitude ?: return null
    if (!latitude.isFinite() || !longitude.isFinite()) return null
    if (latitude !in -90.0..90.0 || longitude !in -180.0..180.0) return null
    // 0,0 is almost always a missing-coordinate sentinel for a real bar;
    // never display it as an actual point of interest.
    if (latitude == 0.0 && longitude == 0.0) return null
    if (bar.barId.isBlank()) return null
    return BarMapTarget(
        barId = bar.barId,
        name = bar.name,
        address = bar.address,
        latitude = latitude,
        longitude = longitude,
    )
}

/** No normalization: clipboard must preserve the Backend address verbatim. */
internal fun copyableBarAddress(address: String?): String? = address?.takeIf { it.isNotBlank() }
