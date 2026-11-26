package com.zerotoone.bottlemap.ui.auth

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.ContextWrapper
import android.content.Intent
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.zerotoone.bottlemap.telemetry.AppTelemetry
import com.zerotoone.bottlemap.telemetry.FakeTelemetry
import com.zerotoone.bottlemap.telemetry.TelemetryEvent
import com.zerotoone.bottlemap.network.CurrentUserDto
import com.zerotoone.bottlemap.ui.theme.BottleMapTheme
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35], qualifiers = "w390dp-h1000dp-xhdpi")
class ProblemReportScreenTest {
    @get:Rule val compose = createComposeRule()

    @Test fun guestLaunchKeepsAccountOnReturnAndRecompositionDoesNotLaunchAgain() {
        val previous = AppTelemetry.current
        val telemetry = FakeTelemetry()
        AppTelemetry.current = telemetry
        try {
            val launches = mutableListOf<Intent>()
            val recompose = mutableStateOf(false)
            var navigation = 0
            compose.setContent {
                val activity = LocalContext.current
                val context = object : ContextWrapper(activity) {
                    override fun startActivity(intent: Intent) { launches += intent }
                }
                // Re-rendering the same account destination simulates a returning browser.
                val state = if (recompose.value) AuthUiState.Guest else AuthUiState.Guest
                CompositionLocalProvider(LocalContext provides context) {
                    BottleMapTheme {
                        AccountScreen(state, { navigation++ }, { navigation++ },
                            { navigation++ }, { navigation++ })
                    }
                }
            }
            compose.onNodeWithText("문제 신고하기").performClick()
            compose.onNodeWithText("문제 신고하기").performClick()
            compose.runOnIdle {
                assertEquals(1, launches.size)
                assertEquals(listOf(TelemetryEvent.ReportProblemOpened), telemetry.events)
                recompose.value = true
            }
            compose.onNodeWithText("내 정보").assertIsDisplayed()
            compose.onNodeWithText("로그인하기").assertIsDisplayed()
            compose.onNodeWithText("이 기능은 준비 중이에요.").assertDoesNotExist()
            compose.runOnIdle {
                assertEquals(1, launches.size)
                assertEquals(0, navigation)
            }
        } finally { AppTelemetry.current = previous }
    }

    @Test fun browserFailureUsesOnlyExistingNoticeAndSameRowRetriesImmediately() {
        val notices = mutableListOf<String>()
        var attempts = 0
        var browserAvailable = false
        val opened = mutableListOf<Intent>()
        compose.setContent {
            val base = LocalContext.current
            val context = object : ContextWrapper(base) {
                override fun startActivity(intent: Intent) {
                    attempts++
                    if (!browserAvailable) throw ActivityNotFoundException()
                    opened += intent
                }
            }
            CompositionLocalProvider(LocalContext provides context) {
                BottleMapTheme { AccountScreen(AuthUiState.Guest, {}, {}, {}, {}, onNotice = { notices += it }) }
            }
        }
        repeat(2) { compose.onNodeWithText("문제 신고하기").performClick() }
        compose.runOnIdle {
            assertEquals(2, attempts)
            assertEquals(List(2) { "문제 신고 폼을 열지 못했어요. 브라우저를 확인해 주세요." }, notices)
        }
        compose.onNodeWithText("다시 시도").assertDoesNotExist()
        compose.onNodeWithText("내 정보").assertIsDisplayed()
        compose.runOnIdle { browserAvailable = true }
        compose.onNodeWithText("문제 신고하기").performClick()
        compose.runOnIdle {
            assertEquals(3, attempts)
            assertEquals(2, notices.size)
            assertEquals(1, opened.size)
            assertEquals(PROBLEM_REPORT_FORM, opened.single().data!!.toString().substringBefore('?'))
        }
        compose.onNodeWithText("내 정보").assertIsDisplayed()
    }

    @Test fun signedInAccountCanReportWithoutPassingIdentityOrChangingLoginState() {
        val launches = mutableListOf<Intent>()
        val user = CurrentUserDto("private-user-id", "private@example.test", "테스트 사용자",
            "customer", "2026-11-26T00:00:00Z")
        compose.setContent {
            val base = LocalContext.current
            val context = object : ContextWrapper(base) {
                override fun startActivity(intent: Intent) { launches += intent }
            }
            // Robolectric's fresh storage has no Supabase session. The account's
            // unrelated owner lookup has no token and cannot make an API request.
            CompositionLocalProvider(LocalContext provides context) {
                BottleMapTheme { AccountScreen(AuthUiState.SignedIn(user), {}, {}, {}, {}) }
            }
        }
        compose.onNodeWithText("문제 신고하기").performClick()
        compose.onNodeWithText("테스트 사용자").assertIsDisplayed()
        compose.onNodeWithText("로그아웃").assertIsDisplayed()
        compose.runOnIdle {
            assertEquals(1, launches.size)
            val uri = launches.single().data!!
            assertFalse(uri.toString().contains(user.userId))
            assertFalse(uri.toString().contains("private"))
            assertNull(launches.single().extras)
        }
    }
}
