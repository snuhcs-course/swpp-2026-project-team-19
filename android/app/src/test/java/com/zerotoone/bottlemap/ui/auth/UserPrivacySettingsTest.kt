package com.zerotoone.bottlemap.ui.auth

import android.content.Context
import android.content.Intent
import com.zerotoone.bottlemap.BuildConfig
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk=[35])
class UserPrivacySettingsTest {
    @Test fun oldWelcomeCompletionDoesNotBypassNewSelfConfirmation() {
        val context=RuntimeEnvironment.getApplication()
        val prefs=context.getSharedPreferences("bottlemap-first-launch",Context.MODE_PRIVATE)
        prefs.edit().clear().putBoolean("welcome-done",true).commit()
        val store=SharedPrefsFirstLaunchStore(context)
        assertFalse(store.isDone()); assertFalse(store.isAgeConfirmed())
        store.confirmAge();store.markDone()
        assertTrue(SharedPrefsFirstLaunchStore(context).isDone())
        assertEquals(setOf("welcome-done","age-18-confirmed"),prefs.all.keys)
        store.reset();assertFalse(store.isDone())
    }
    @Test fun qualityRecordingIsOptionalAndStoredSeparatelyFromLogin() {
        val context=RuntimeEnvironment.getApplication()
        val settings=UserPrivacySettings.get(context)
        assertFalse(settings.usageEnabled.value)
        settings.setUsageEnabled(true)
        assertTrue(context.getSharedPreferences("bottlemap-privacy",Context.MODE_PRIVATE).getBoolean("usage-records",false))
        assertTrue(UserPrivacySettings.get(context).usageEnabled.value)
        settings.setUsageEnabled(false)
        assertFalse(settings.usageEnabled.value)
    }
    @Test fun policyOpensTheConfiguredPublicUrlWithoutAuthentication() {
        val app=RuntimeEnvironment.getApplication()
        openPrivacyPolicy(app)
        val intent=shadowOf(app).nextStartedActivity
        assertEquals(Intent.ACTION_VIEW,intent.action)
        assertEquals(BuildConfig.PRIVACY_POLICY_URL,intent.dataString)
    }
}
