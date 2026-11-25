package com.zerotoone.bottlemap.telemetry

import android.content.Context
import android.os.Bundle
import com.google.firebase.FirebaseApp
import com.google.firebase.analytics.FirebaseAnalytics
import com.google.firebase.crashlytics.FirebaseCrashlytics
import com.zerotoone.bottlemap.BuildConfig

internal fun createPlatformTelemetry(context: Context, initiallyEnabled: Boolean): Telemetry =
    ConsentTelemetry(FirebaseTelemetry(context.applicationContext, initiallyEnabled), BuildConfig.TELEMETRY_BUILD_ALLOWED)

/** Lazy SDK initialization: no Firebase provider runs before optional consent. */
internal class FirebaseTelemetry(private val context: Context, private val initiallyEnabled: Boolean) : Telemetry {
    private var analytics: FirebaseAnalytics? = null
    private var crashlytics: FirebaseCrashlytics? = null
    private var enabled = false
    override fun setEnabled(enabled: Boolean) {
        if (enabled && analytics == null) {
            FirebaseApp.initializeApp(context) ?: return
            val crashes = FirebaseCrashlytics.getInstance()
            // Keep automatic upload OFF persistently, including before the next Application starts.
            // Only consented launches explicitly send the previous consented session's crash.
            crashes.setCrashlyticsCollectionEnabled(false)
            if (initiallyEnabled) crashes.sendUnsentReports() else crashes.deleteUnsentReports()
            crashlytics = crashes
            analytics = FirebaseAnalytics.getInstance(context)
        }
        if (!enabled) {
            analytics?.setAnalyticsCollectionEnabled(false)
            analytics?.resetAnalyticsData()
            crashlytics?.deleteUnsentReports()
        } else {
            analytics?.setConsent(mapOf(
                FirebaseAnalytics.ConsentType.AD_STORAGE to FirebaseAnalytics.ConsentStatus.DENIED,
                FirebaseAnalytics.ConsentType.AD_USER_DATA to FirebaseAnalytics.ConsentStatus.DENIED,
                FirebaseAnalytics.ConsentType.AD_PERSONALIZATION to FirebaseAnalytics.ConsentStatus.DENIED,
                FirebaseAnalytics.ConsentType.ANALYTICS_STORAGE to FirebaseAnalytics.ConsentStatus.GRANTED,
            ))
            analytics?.setUserProperty("release_channel", BuildConfig.RELEASE_CHANNEL)
            analytics?.setAnalyticsCollectionEnabled(true)
        }
        this.enabled = enabled
    }
    override fun log(event: TelemetryEvent) {
        if (!enabled) return
        val payload = event.payload()
        analytics?.logEvent(payload.name, Bundle().apply {
            payload.parameters.forEach { (key, value) ->
                when (value) { is Long -> putLong(key, value); is String -> putString(key, value) }
            }
        })
    }
    override fun setScreen(route: ScreenRoute) {
        if (enabled) crashlytics?.setCustomKey("screen_route", route.template)
    }
}
