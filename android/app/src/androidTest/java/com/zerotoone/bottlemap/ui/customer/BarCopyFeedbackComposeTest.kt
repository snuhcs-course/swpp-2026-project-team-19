package com.zerotoone.bottlemap.ui.customer

import android.content.ClipboardManager
import android.content.Context
import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Shared public/owner-preview detail copy behavior. A missing map coordinate
 * intentionally renders the offline fallback rather than starting Kakao GL.
 */
@RunWith(AndroidJUnit4::class)
class BarCopyFeedbackComposeTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    private fun bar(phone: String? = "02-1234-5678") = BarDetailUiModel(
        barId = "test-bar",
        name = "테스트 매장",
        address = "서울특별시 관악구 테스트길 1",
        phone = phone,
        latitude = null,
        longitude = null,
        publishedAtText = null,
        items = emptyList(),
    )

    @Test fun addressCopyShowsTopToastAndPhoneUsesOnlySystemClipboard() {
        compose.setContent {
            MaterialTheme {
                CustomerP18BarDetail(
                    bar = bar(),
                    empty = null,
                    onBack = {},
                    highlightProductId = null,
                )
            }
        }
        compose.onNodeWithText("지도").performScrollTo().performClick()
        compose.onNodeWithText("복사").performScrollTo().performClick()
        compose.onNodeWithTag("ux-toast").assertIsDisplayed()
        compose.onNodeWithText("주소를 복사했어요.").assertIsDisplayed()
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        assertEquals("서울특별시 관악구 테스트길 1",
            clipboard.primaryClip?.getItemAt(0)?.coerceToText(context)?.toString())
        // The notice is transient: there is no blocking confirmation button.
        compose.mainClock.advanceTimeBy(3000)
        compose.waitForIdle()
        compose.onNodeWithTag("ux-toast").assertDoesNotExist()

        compose.onNodeWithText("전화").performScrollTo().performClick()
        compose.onNodeWithText("복사").performScrollTo().performClick()
        assertEquals("02-1234-5678",
            clipboard.primaryClip?.getItemAt(0)?.coerceToText(context)?.toString())
        compose.onNodeWithTag("ux-toast").assertDoesNotExist()
        compose.onNodeWithTag("ux-toast").assertDoesNotExist()
    }

    @Test fun missingPhoneNeverClaimsCopySucceeded() {
        compose.setContent {
            MaterialTheme {
                CustomerP18BarDetail(
                    bar = bar(phone = null),
                    empty = null,
                    onBack = {},
                    highlightProductId = null,
                )
            }
        }
        compose.onNodeWithText("전화").performScrollTo().performClick()
        compose.onNodeWithText("복사").assertIsNotEnabled()
        compose.onNodeWithTag("ux-toast").assertDoesNotExist()
    }
}
