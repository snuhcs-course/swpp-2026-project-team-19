package com.zerotoone.bottlemap.ux

import android.graphics.Bitmap
import android.graphics.Canvas
import android.os.Looper
import android.view.View
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.test.core.app.ActivityScenario
import com.zerotoone.bottlemap.data.owner.review.MockPhotoReviewRepository
import com.zerotoone.bottlemap.data.owner.review.MockPhotoReviewScenario
import com.zerotoone.bottlemap.navigation.BottomTabs
import com.zerotoone.bottlemap.navigation.MainTab
import com.zerotoone.bottlemap.ui.auth.LoginErrorScreen
import com.zerotoone.bottlemap.ui.auth.WelcomeScreen
import com.zerotoone.bottlemap.ui.common.UxColor
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewScreen
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewViewModel
import com.zerotoone.bottlemap.ui.theme.BottleMapTheme
import java.io.File
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * Renders every v18 screen state of this change at the prototype's 390dp width and saves
 * PNGs to app/build/ux-screenshots for the HTML comparison. Opt-in:
 * `./gradlew :app:testDebugUnitTest --tests '*UxV18ScreenshotTest*' -PbmUxScreenshots=true`.
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35])
class UxV18ScreenshotTest {
    private val outDir = File(System.getProperty("bm.ux.screenshotDir") ?: "build/ux-screenshots")

    @Before fun enabled() {
        assumeTrue(System.getProperty("bm.ux.screenshots") == "true")
        outDir.mkdirs()
    }

    private fun idle() = repeat(6) { shadowOf(Looper.getMainLooper()).idle() }

    private fun capture(name: String, widthDp: Int, heightDp: Int, content: @Composable () -> Unit) {
        RuntimeEnvironment.setQualifiers("w${widthDp}dp-h${heightDp}dp-xhdpi")
        ActivityScenario.launch(ComponentActivity::class.java).use { scenario ->
            scenario.onActivity { activity ->
                activity.setContent { BottleMapTheme { Box(Modifier.fillMaxSize().background(UxColor.bg)) { content() } } }
            }
            idle()
            scenario.onActivity { activity ->
                val view: View = activity.window.decorView
                val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
                view.draw(Canvas(bitmap))
                File(outDir, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
            }
        }
    }

    private fun review(name: String, scenario: MockPhotoReviewScenario, heightDp: Int = 3400,
        prepare: (PhotoReviewViewModel) -> Unit = {}) {
        val vm = PhotoReviewViewModel(MockPhotoReviewRepository(scenario))
        idle()
        prepare(vm)
        idle()
        capture("review-$name", 390, heightDp) { PhotoReviewScreen(vm, onLeave = {}) }
    }

    @Test fun firstLaunchAndTabs() {
        capture("auth-welcome", 390, 744) { WelcomeScreen({}, {}, {}) }
        capture("auth-login-fail", 390, 744) { LoginErrorScreen("Google 로그인에 실패했어요.", {}, {}, {}) }
        capture("auth-session-expired", 390, 744) { LoginErrorScreen("로그인이 만료됐어요.", {}, {}, {}) }
        capture("tabs-search", 390, 200) {
            Column(Modifier.fillMaxSize()) {
                Box(Modifier.weight(1f))
                BottomTabs(MainTab.SEARCH) {}
            }
        }
        capture("tabs-account", 390, 200) {
            Column(Modifier.fillMaxSize()) {
                Box(Modifier.weight(1f))
                BottomTabs(MainTab.ACCOUNT) {}
            }
        }
    }

    @Test fun everyReviewScenario() {
        MockPhotoReviewScenario.entries.forEach { review(it.id, it) }
    }

    @Test fun reviewDetailsAndModals() {
        review("default-pour-expanded", MockPhotoReviewScenario.DEFAULT_POUR) { it.toggleExpanded("glen12") }
        review("whisky-options-expanded", MockPhotoReviewScenario.WHISKY_OPTIONS) { it.toggleExpanded("glen12") }
        review("bad-inputs-expanded", MockPhotoReviewScenario.BAD_INPUTS) { it.toggleExpanded("glen12") }
        review("zero-option-expanded", MockPhotoReviewScenario.ZERO_OPTION) { it.toggleExpanded("glen15") }
        review("other-expanded", MockPhotoReviewScenario.OTHER) { it.toggleExpanded("gin") }
        review("candidate-selected", MockPhotoReviewScenario.CANDIDATES) { it.chooseCandidate("arran", "arran-sherry") }
        review("catalog-found-selected", MockPhotoReviewScenario.CATALOG_FOUND) {
            it.selectSearchResult("hakushu", "hakushu-12")
        }
        review("detail-name-editing", MockPhotoReviewScenario.LINKED_NAME) {
            it.editDetailName("glen12")
            it.toggleExpanded("glen12")
        }
        review("excluded-open", MockPhotoReviewScenario.EXCLUDE) { it.toggleGroup(com.zerotoone.bottlemap.ui.owner.review.ReviewGroup.EXCLUDED) }
        review("publish-sheet", MockPhotoReviewScenario.READY, 744) { it.requestPublish() }
        review("exclude-sheet", MockPhotoReviewScenario.BASIC, 744) { it.requestExclude("ardbeg") }
        review("photo-modal", MockPhotoReviewScenario.BASIC, 744) { it.openSourcePhoto("glen15") }
        review("photo-modal-no-box", MockPhotoReviewScenario.SOURCE_NO_BOX, 744) { it.openSourcePhoto("arran") }
        review("photo-modal-merged", MockPhotoReviewScenario.MERGED_LINES, 744) { it.openSourcePhoto("glen12", 0) }
        review("viewport-basic", MockPhotoReviewScenario.BASIC, 744)
    }
}
