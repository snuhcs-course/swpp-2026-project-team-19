plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

val configuredApiBaseUrl = providers.gradleProperty("BOTTLEMAP_API_BASE_URL")
    .orNull
    ?.let { if (it.endsWith("/")) it else it + "/" }
val debugApiBaseUrl = configuredApiBaseUrl ?: "http://10.0.2.2:8000/"
val releaseApiBaseUrl = configuredApiBaseUrl ?: "https://api.example.invalid/"
// Native Android app keys are bundled into APKs; restrict use via package+key-hash
// registration in Kakao Developers. Never commit a real value to this repository.
fun stringBuildConfigValue(value: String): String =
    "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

val supabaseUrl = providers.gradleProperty("BOTTLEMAP_SUPABASE_URL").orElse("").get()
val supabasePublishableKey = providers.gradleProperty("BOTTLEMAP_SUPABASE_PUBLISHABLE_KEY").orElse("").get()
val googleWebClientId = providers.gradleProperty("BOTTLEMAP_GOOGLE_WEB_CLIENT_ID").orElse("").get()

val kakaoNativeAppKey = providers.gradleProperty("BOTTLEMAP_KAKAO_NATIVE_APP_KEY")
    .orElse("")
    .get()

android {
    namespace = "com.zerotoone.bottlemap"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.zerotoone.bottlemap"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "KAKAO_NATIVE_APP_KEY", stringBuildConfigValue(kakaoNativeAppKey))
        buildConfigField("String", "SUPABASE_URL", stringBuildConfigValue(supabaseUrl))
        buildConfigField("String", "SUPABASE_PUBLISHABLE_KEY", stringBuildConfigValue(supabasePublishableKey))
        buildConfigField("String", "GOOGLE_WEB_CLIENT_ID", stringBuildConfigValue(googleWebClientId))
    }

    // One APK for customer and owner flows.
    buildTypes {
        debug {
            // AGP's built-in JaCoCo collects local JVM coverage.
            enableUnitTestCoverage = true
            // Instrument Compose tests only when explicitly requested by the emulator CI.
            // Default debug APKs (including the deployed-server APK) stay uninstrumented.
            enableAndroidTestCoverage = providers.gradleProperty("BOTTLEMAP_ANDROID_TEST_COVERAGE")
                .orNull == "true"
            buildConfigField("String", "API_BASE_URL", "\"$debugApiBaseUrl\"")
        }
        release {
            isMinifyEnabled = false
            buildConfigField("String", "API_BASE_URL", "\"$releaseApiBaseUrl\"")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    // Robolectric UX screenshots are an opt-in visual artifact, NOT regular
    // unit tests. Exclude the class from normal CI instead of silently
    // counting three Assume skips, which violates our test-inventory policy.
    // Keep the original explicit command:
    // ./gradlew :app:testDebugUnitTest --tests '*UxV18ScreenshotTest*' -PbmUxScreenshots=true
    testOptions {
        unitTests.isIncludeAndroidResources = true
        unitTests.all {
            val screenshots = providers.gradleProperty("bmUxScreenshots").orNull == "true"
            if (!screenshots) {
                it.filter.excludeTestsMatching("com.zerotoone.bottlemap.ux.UxV18ScreenshotTest")
            }
            it.systemProperty("bm.ux.screenshots", screenshots.toString())
            it.systemProperty("bm.ux.screenshotDir", layout.buildDirectory.dir("ux-screenshots").get().asFile.path)
        }
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.viewmodel.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.exifinterface)

    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.kakao.maps)
    implementation(libs.google.play.services.location)
    implementation(libs.kotlinx.coroutines.play.services)
    implementation(libs.androidx.credentials)
    implementation(libs.androidx.credentials.play.services)
    implementation(libs.google.id)
    implementation(platform(libs.supabase.bom))
    implementation(libs.supabase.auth)
    implementation(libs.ktor.client.okhttp)

    implementation(libs.retrofit.core)
    implementation(libs.retrofit.converter.moshi)
    implementation(libs.okhttp.core)
    implementation(libs.okhttp.logging)
    implementation(libs.moshi.kotlin)

    testImplementation(libs.junit4)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.robolectric)
    testImplementation(platform(libs.androidx.compose.bom))
    testImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    debugImplementation("androidx.compose.ui:ui-test-manifest")

    debugImplementation(libs.androidx.compose.ui.tooling)
}
