// AI-assisted implementation (2026-10-18, I2-A7).
package com.zerotoone.bottlemap.data

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.location.LocationManager
import androidx.core.content.ContextCompat
import com.google.android.gms.location.CurrentLocationRequest
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withTimeout

class NearbyLocationServicesDisabledException : IllegalStateException()
class NearbyLocationUnavailableException : IllegalStateException()
class NearbyLocationInaccurateException : IllegalStateException()

/**
 * Single location fix. Never subscribes to background updates or persists
 * the user's coordinates. SDK cancellation follows coroutine cancellation.
 */
class AndroidNearbyLocationSource(context: Context) : NearbyLocationSource {
    private val appContext = context.applicationContext
    private val client = LocationServices.getFusedLocationProviderClient(appContext)

    @SuppressLint("MissingPermission")
    override suspend fun currentLocation(): NearbyCoordinate {
        if (ContextCompat.checkSelfPermission(
                appContext, Manifest.permission.ACCESS_FINE_LOCATION,
            ) != PackageManager.PERMISSION_GRANTED
        ) throw SecurityException("Precise location permission required")

        val manager = appContext.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        if (!manager.isProviderEnabled(LocationManager.GPS_PROVIDER) &&
            !manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)
        ) throw NearbyLocationServicesDisabledException()

        val cancellation = CancellationTokenSource()
        try {
            val request = CurrentLocationRequest.Builder()
                .setPriority(Priority.PRIORITY_HIGH_ACCURACY)
                .setMaxUpdateAgeMillis(10_000L)
                .setDurationMillis(12_000L)
                .build()
            val fix = withTimeout(15_000L) {
                client.getCurrentLocation(request, cancellation.token).await()
            } ?: throw NearbyLocationUnavailableException()
            if (!fix.hasAccuracy() || fix.accuracy > 200f) {
                throw NearbyLocationInaccurateException()
            }
            val point = NearbyCoordinate(fix.latitude, fix.longitude)
            if (!point.isValid()) throw NearbyLocationUnavailableException()
            return point
        } catch (cancelled: TimeoutCancellationException) {
            throw NearbyLocationUnavailableException()
        } catch (cancelled: CancellationException) {
            throw cancelled
        } finally {
            cancellation.cancel()
        }
    }
}
