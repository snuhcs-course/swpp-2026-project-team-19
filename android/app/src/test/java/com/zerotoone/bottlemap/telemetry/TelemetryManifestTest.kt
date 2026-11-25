package com.zerotoone.bottlemap.telemetry

import android.content.pm.PackageManager
import com.zerotoone.bottlemap.BuildConfig
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk=[35])
class TelemetryManifestTest {
    @Test fun mergedManifestBlocksPreConsentCollectionAdsAndProviderInitialization() {
        val app=RuntimeEnvironment.getApplication()
        val info=app.packageManager.getApplicationInfo(app.packageName,PackageManager.GET_META_DATA)
        for (key in listOf("firebase_analytics_collection_enabled","firebase_crashlytics_collection_enabled",
            "google_analytics_adid_collection_enabled","google_analytics_default_allow_ad_personalization_signals",
            "google_analytics_automatic_screen_reporting_enabled")) {
            assertTrue(key,info.metaData.containsKey(key));assertFalse(key,info.metaData.getBoolean(key))
        }
        assertEquals(!BuildConfig.TELEMETRY_BUILD_ALLOWED,info.metaData.getBoolean("firebase_analytics_collection_deactivated"))
        val pkg=app.packageManager.getPackageInfo(app.packageName,PackageManager.GET_PROVIDERS or PackageManager.GET_PERMISSIONS)
        assertFalse(pkg.providers.orEmpty().any { it.name=="com.google.firebase.provider.FirebaseInitProvider" })
        for (permission in listOf("com.google.android.gms.permission.AD_ID",
            "android.permission.ACCESS_ADSERVICES_AD_ID", "android.permission.ACCESS_ADSERVICES_ATTRIBUTION")) {
            assertFalse(permission,pkg.requestedPermissions.orEmpty().contains(permission))
        }
    }
}
