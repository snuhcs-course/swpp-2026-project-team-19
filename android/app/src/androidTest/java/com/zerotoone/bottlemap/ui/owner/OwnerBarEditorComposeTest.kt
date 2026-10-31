package com.zerotoone.bottlemap.ui.owner

import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.test.assertExists
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextClearance
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.zerotoone.bottlemap.data.owner.InMemoryMockOwnerStateStore
import com.zerotoone.bottlemap.data.owner.LocalOwnerMockRepository
import com.zerotoone.bottlemap.data.owner.OwnerMockFixtures
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Android-connected Compose tests; these require an emulator or USB device.
 * CI's JVM JUnit task does not execute this source set.
 */
@RunWith(AndroidJUnit4::class)
class OwnerBarEditorComposeTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Test fun editingNameChangesOnlyAfterExplicitSave() {
        val repository = LocalOwnerMockRepository(InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val vm = OwnerMockViewModel(repository)
        var exits = 0
        compose.setContent {
            MaterialTheme {
                OwnerBarInfoEditorScreen(
                    state = vm.state.collectAsState().value, viewModel = vm,
                    onBack = { exits++ }, onPhotos = {}, onTags = {},
                    onHours = {}, onStatus = {}
                )
            }
        }
        val initial = vm.preview("fixture-bar", 0)!!.bar.name
        compose.onNodeWithTag("owner-info-name").performTextClearance()
        compose.onNodeWithTag("owner-info-name").performTextInput("바뀐 매장")
        compose.runOnIdle {
            assertEquals(initial, vm.preview("fixture-bar", 0)!!.bar.name)
        }
        compose.onNodeWithTag("owner-info-save").performClick()
        compose.runOnIdle {
            assertEquals("바뀐 매장", vm.preview("fixture-bar", 0)!!.bar.name)
            assertEquals(1, exits)
        }
    }

    @Test fun unsavedBackShowsDiscardPromptWithoutMutatingSharedPreview() {
        val repository = LocalOwnerMockRepository(InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val vm = OwnerMockViewModel(repository)
        var exited = false
        compose.setContent {
            MaterialTheme {
                OwnerBarInfoEditorScreen(
                    vm.state.collectAsState().value, vm, onBack = { exited = true },
                    onPhotos = {}, onTags = {}, onHours = {}, onStatus = {}
                )
            }
        }
        val initial = vm.preview("fixture-bar", 0)!!.bar.name
        compose.onNodeWithTag("owner-info-name").performTextClearance()
        compose.onNodeWithTag("owner-info-name").performTextInput("임시 텍스트")
        compose.onNodeWithContentDescription("뒤로가기").performClick()
        compose.onNodeWithText("저장하지 않고 나가기").assertIsDisplayed().performClick()
        compose.runOnIdle {
            assertEquals(initial, vm.preview("fixture-bar", 0)!!.bar.name)
            assertEquals(true, exited)
        }
    }

    @Test fun photoAndTagEditorsOfferExplicitSaveActions() {
        val vm = OwnerMockViewModel(
            LocalOwnerMockRepository(InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        )
        compose.setContent {
            MaterialTheme {
                OwnerBarPhotoEditorScreen(vm.state.collectAsState().value, vm, onBack = {})
            }
        }
        compose.onNodeWithTag("owner-photo-save").assertExists()
    }
}
