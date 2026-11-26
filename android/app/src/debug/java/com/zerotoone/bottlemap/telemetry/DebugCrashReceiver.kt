package com.zerotoone.bottlemap.telemetry

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import com.zerotoone.bottlemap.BuildConfig
import com.zerotoone.bottlemap.ui.auth.UserPrivacySettings

/** Shell-only verification hook. The receiver and crash code are absent from Release. */
class DebugCrashReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != "com.zerotoone.bottlemap.DEBUG_TELEMETRY_CRASH" ||
            !BuildConfig.FIREBASE_ENABLED || !BuildConfig.TELEMETRY_BUILD_ALLOWED ||
            !UserPrivacySettings.get(context).usageEnabled.value) return
        Handler(Looper.getMainLooper()).post {
            throw IllegalStateException("BottleMap telemetry verification crash")
        }
    }
}
