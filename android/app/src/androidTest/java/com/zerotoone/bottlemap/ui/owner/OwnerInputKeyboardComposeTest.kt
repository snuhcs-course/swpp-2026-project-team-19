package com.zerotoone.bottlemap.ui.owner

import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.assertIsFocused
import androidx.compose.ui.test.assertIsNotFocused
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.click
import androidx.compose.ui.test.performTextInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.zerotoone.bottlemap.ui.common.dismissKeyboardOnOutsideTap
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class OwnerInputKeyboardComposeTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Test fun tappingOutsideClearsFocusAndFieldCanBeFocusedAgain() {
        var value by mutableStateOf("")
        compose.setContent {
            MaterialTheme {
                Box(Modifier.fillMaxSize().dismissKeyboardOnOutsideTap()
                    .testTag("keyboard-outside")) {
                    Column {
                        V4FormField("메뉴 이름", value, { value = it },
                            testTag = "keyboard-name")
                    }
                }
            }
        }
        compose.onNodeWithTag("keyboard-name").performClick()
        compose.onNodeWithTag("keyboard-name").assertIsFocused()
        compose.onNodeWithTag("keyboard-name").performTextInput("라가불린")
        compose.onNodeWithTag("keyboard-outside").performTouchInput {
            click()
        }
        compose.onNodeWithTag("keyboard-name").assertIsNotFocused()
        compose.onNodeWithTag("keyboard-name").performClick()
        compose.onNodeWithTag("keyboard-name").assertIsFocused()
        compose.runOnIdle { assertEquals("라가불린", value) }
    }
}
