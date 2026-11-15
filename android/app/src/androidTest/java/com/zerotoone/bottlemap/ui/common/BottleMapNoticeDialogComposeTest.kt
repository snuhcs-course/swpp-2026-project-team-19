package com.zerotoone.bottlemap.ui.common

import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.remember
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class BottleMapNoticeDialogComposeTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Test fun uatValidationNoticeIsModalAndDismissible() {
        compose.setContent {
            var open by remember { mutableStateOf(true) }
            MaterialTheme {
                if (open) BottleMapNoticeDialog(
                    message = "검색어를 입력해 주세요.",
                    onDismiss = { open = false },
                    tag = "uat-validation-popup",
                    title = "검색 안내",
                )
            }
        }
        compose.onNodeWithTag("uat-validation-popup").assertIsDisplayed()
        compose.onNodeWithText("검색어를 입력해 주세요.").assertIsDisplayed()
        compose.onNodeWithText("확인").performClick()
        compose.onNodeWithTag("uat-validation-popup").assertDoesNotExist()
    }

    @Test fun photoLimitNoticeShowsExactSheetWording() {
        compose.setContent {
            MaterialTheme {
                BottleMapNoticeDialog(
                    message = "사진은 최대 15장까지 선택할 수 있어요.",
                    onDismiss = {},
                    tag = "stage7-photo-limit-dialog",
                    title = "사진 추가 안내",
                )
            }
        }
        compose.onNodeWithTag("stage7-photo-limit-dialog").assertIsDisplayed()
        compose.onNodeWithText("사진은 최대 15장까지 선택할 수 있어요.").assertIsDisplayed()
    }
}
