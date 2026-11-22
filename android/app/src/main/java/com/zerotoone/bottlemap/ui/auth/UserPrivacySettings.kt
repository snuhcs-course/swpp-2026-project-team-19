package com.zerotoone.bottlemap.ui.auth

import android.content.Context
import android.content.Intent
import android.net.Uri
import com.zerotoone.bottlemap.BuildConfig
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Optional quality-recording consent, independent of login and age attestation.
 * No analytics SDK or collection endpoint is installed by this UI change.
 * Future optional collectors must observe this gate; the default is opt-out.
 */
class UserPrivacySettings private constructor(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("bottlemap-privacy", Context.MODE_PRIVATE)
    private val mutable = MutableStateFlow(prefs.getBoolean("usage-records", false))
    val usageEnabled: StateFlow<Boolean> = mutable.asStateFlow()
    fun setUsageEnabled(enabled: Boolean) {
        prefs.edit().putBoolean("usage-records", enabled).apply()
        mutable.value = enabled
    }
    companion object {
        @Volatile private var instance: UserPrivacySettings? = null
        fun get(context: Context): UserPrivacySettings = instance ?: synchronized(this) {
            instance ?: UserPrivacySettings(context.applicationContext).also { instance = it }
        }
    }
}

internal fun openPrivacyPolicy(context: Context, onFailure: (String) -> Unit = {}) {
    try {
        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(BuildConfig.PRIVACY_POLICY_URL))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    } catch (_: android.content.ActivityNotFoundException) {
        onFailure("개인정보처리방침을 열 수 있는 브라우저가 없어요.")
    }
}
