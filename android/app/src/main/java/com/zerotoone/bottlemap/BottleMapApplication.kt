package com.zerotoone.bottlemap

import android.app.Application
import android.util.Log
import com.kakao.vectormap.KakaoMapSdk

class BottleMapApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        // The native app key comes from the local Gradle property. Never commit it.
        // Kakao Developers must also register this package and signing key hash.
        if (BuildConfig.KAKAO_NATIVE_APP_KEY.isNotBlank()) {
            try {
                KakaoMapSdk.init(this, BuildConfig.KAKAO_NATIVE_APP_KEY)
            } catch (error: LinkageError) {
                // SDK native libraries are ARM-only; keep non-ARM emulators usable.
                Log.e("BottleMapKakao", "SDK native library unavailable", error)
            } catch (error: Exception) {
                Log.e("BottleMapKakao", "SDK initialization failed", error)
            }
        }
    }
}
