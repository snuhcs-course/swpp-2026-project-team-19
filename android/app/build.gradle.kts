plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    id("com.google.gms.google-services") version "4.6.0" apply false
    id("com.google.firebase.crashlytics") version "3.0.8" apply false
}

// No Firebase SDKs, plugin application or generated configuration in credential-free builds.
val firebaseEnabled = file("google-services.json").isFile &&
    providers.gradleProperty("BOTTLEMAP_FIREBASE_ENABLED").orNull != "false"
val releaseChannel = providers.gradleProperty("BOTTLEMAP_RELEASE_CHANNEL").orElse("dev").get()
require(releaseChannel in setOf("dev", "alpha", "beta", "release")) {
    "BOTTLEMAP_RELEASE_CHANNEL must be dev, alpha, beta or release"
}
val debugTelemetryEnabled = providers.gradleProperty("BOTTLEMAP_TELEMETRY_DEBUG_ENABLED").orNull == "true"
if (firebaseEnabled) {
    apply(plugin = "com.google.gms.google-services")
    apply(plugin = "com.google.firebase.crashlytics")
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

/** Optional during configuration so debug builds and CI need no release secrets. */
val releaseSigningValues = listOf(
    "BOTTLEMAP_RELEASE_STORE_FILE",
    "BOTTLEMAP_RELEASE_STORE_PASSWORD",
    "BOTTLEMAP_RELEASE_KEY_ALIAS",
    "BOTTLEMAP_RELEASE_KEY_PASSWORD",
).associateWith { providers.gradleProperty(it).orNull }
val releaseKeystoreFile = releaseSigningValues["BOTTLEMAP_RELEASE_STORE_FILE"]
    ?.takeIf { it.isNotBlank() }?.let { file(it) }
val validateReleaseSigning = tasks.register("validateReleaseSigning") {
    group = "verification"
    description = "Require local upload signing settings before a release build."
    doLast {
        val missing = releaseSigningValues.filterValues { it.isNullOrBlank() }.keys
        check(missing.isEmpty()) {
            "Missing release signing properties: " + missing.joinToString() +
                ". Set them in your user Gradle properties."
        }
        check(releaseKeystoreFile?.isFile == true) {
            "Release keystore file does not exist. Check BOTTLEMAP_RELEASE_STORE_FILE."
        }
    }
}
// Fail before a release artifact can silently be produced unsigned.
tasks.matching { it.name == "preReleaseBuild" }.configureEach {
    dependsOn(validateReleaseSigning)
}

// The Android SDK jar Robolectric runs the unit tests on (`@Config(sdk = [35])`), resolved by Gradle. Robolectric
// 4.17 looks for exactly this file name in `robolectric.dependency.dir`; change the version with Robolectric.
val robolectricSdk: Configuration by configurations.creating { isTransitive = false }
val robolectricSdkDir = layout.buildDirectory.dir("robolectric-sdk")
val prepareRobolectricSdk by tasks.registering(Sync::class) {
    from(robolectricSdk)
    into(robolectricSdkDir)
}

android {
    sourceSets.named("main") {
        kotlin.directories += if (firebaseEnabled) "src/firebase/java" else "src/noFirebase/java"
    }
    namespace = "com.zerotoone.bottlemap"
    compileSdk = 37

    defaultConfig {
        buildConfigField("boolean", "FIREBASE_ENABLED", firebaseEnabled.toString())
        buildConfigField("String", "RELEASE_CHANNEL", stringBuildConfigValue(releaseChannel))
        manifestPlaceholders["analyticsDeactivated"] = "false"
        applicationId = "com.zerotoone.bottlemap"
        buildConfigField("String", "PRIVACY_POLICY_URL", stringBuildConfigValue(
            providers.gradleProperty("BOTTLEMAP_PRIVACY_POLICY_URL")
                .orElse("https://bottlemap.o-r.kr/privacy").get()))
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

    // Values and the upload keystore stay outside Git.
    signingConfigs {
        create("release") {
            storeFile = releaseKeystoreFile
            storePassword = releaseSigningValues["BOTTLEMAP_RELEASE_STORE_PASSWORD"]
            keyAlias = releaseSigningValues["BOTTLEMAP_RELEASE_KEY_ALIAS"]
            keyPassword = releaseSigningValues["BOTTLEMAP_RELEASE_KEY_PASSWORD"]
        }
    }

    // One APK for customer and owner flows.
    buildTypes {
        debug {
            buildConfigField("boolean", "TELEMETRY_BUILD_ALLOWED", debugTelemetryEnabled.toString())
            // A persisted SDK opt-in from a previous APK cannot enable an ordinary debug build.
            manifestPlaceholders["analyticsDeactivated"] = (!debugTelemetryEnabled).toString()

            // AGP's built-in JaCoCo collects local JVM coverage.
            enableUnitTestCoverage = true
            // Instrument Compose tests only when explicitly requested by the emulator CI.
            // Default debug APKs (including the deployed-server APK) stay uninstrumented.
            enableAndroidTestCoverage = providers.gradleProperty("BOTTLEMAP_ANDROID_TEST_COVERAGE")
                .orNull == "true"
            buildConfigField("String", "API_BASE_URL", "\"$debugApiBaseUrl\"")
        }
        release {
            buildConfigField("boolean", "TELEMETRY_BUILD_ALLOWED", "true")

            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
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
            // Robolectric would download its SDK jar from Maven Central itself, on every CI run (it is kept in
            // ~/.m2, which CI does not cache), and Central refuses GitHub runners at times (HTTP 429). Gradle
            // downloads it instead (with retries, into the Gradle cache CI keeps), and Robolectric runs offline.
            it.dependsOn(prepareRobolectricSdk)
            it.systemProperty("robolectric.offline", "true")
            it.systemProperty("robolectric.dependency.dir", robolectricSdkDir.get().asFile.absolutePath)
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
    if (firebaseEnabled) {
        implementation(platform("com.google.firebase:firebase-bom:35.2.0"))
        implementation("com.google.firebase:firebase-analytics")
        implementation("com.google.firebase:firebase-crashlytics")
    }

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
    testImplementation("org.robolectric:robolectric:4.17")
    robolectricSdk("org.robolectric:android-all-instrumented:15-robolectric-13954326-i7")
    testImplementation(platform(libs.androidx.compose.bom))
    testImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    debugImplementation("androidx.compose.ui:ui-test-manifest")

    debugImplementation(libs.androidx.compose.ui.tooling)
}
