package com.zerotoone.bottlemap.data

import android.content.Context
import android.location.Address
import android.location.Geocoder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException
import java.util.Locale

/**
 * Device-provided named-place/address lookup. Unlike Kakao Local's keyword
 * search, this needs no REST API key in the APK or new Backend endpoint.
 * Availability and shop-name coverage depend on the installed geocoder.
 */
class AndroidMapPlaceSearchSource(context: Context) : MapPlaceSearchSource {
    private val applicationContext = context.applicationContext

    @Suppress("DEPRECATION")
    override suspend fun search(query: String): List<MapPlace> = withContext(Dispatchers.IO) {
        if (!Geocoder.isPresent()) {
            throw IOException("이 기기에서 지도 장소 검색을 지원하지 않습니다.")
        }
        // The deprecated synchronous overload is used on a bounded IO worker
        // for minSdk=26 compatibility. Never invoke geocoding on Compose/UI.
        val addresses = Geocoder(applicationContext, Locale.KOREA)
            .getFromLocationName(query, 5).orEmpty()
        sanitizePlaces(addresses.mapNotNull(::toPlace))
    }

    private fun toPlace(address: Address): MapPlace? {
        val coordinate = NearbyCoordinate(address.latitude, address.longitude)
        // Geocoder(Locale.KOREA) sets the output LANGUAGE, not the search area.
        // Exclude foreign matches explicitly even for Korean-language queries.
        val country = address.countryCode
        if (!country.isNullOrBlank() && !country.equals("KR", ignoreCase = true)) return null
        if (!isInKoreaMapBounds(coordinate)) return null
        val line = address.getAddressLine(0).orEmpty()
        val name = address.featureName?.takeIf { it.isNotBlank() }
            ?: address.premises?.takeIf { it.isNotBlank() }
            ?: line.takeIf { it.isNotBlank() }
            ?: return null
        return MapPlace(name = name, address = line, coordinate = coordinate)
    }
}
