// AI-assisted implementation draft (2026-10-17, I2-P25/A6). Device verification pending.
package com.zerotoone.bottlemap

import android.app.Application
import com.kakao.vectormap.KakaoMapSdk

class BottleMapApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        // The native app key comes from the local Gradle property. Never commit it.
        // Kakao Developers must also register this package and signing key hash.
        if (BuildConfig.KAKAO_NATIVE_APP_KEY.isNotBlank()) {
            KakaoMapSdk.init(this, BuildConfig.KAKAO_NATIVE_APP_KEY)
        }
    }
}
