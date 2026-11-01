package com.zerotoone.bottlemap.ui.owner

import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.performScrollTo
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
                OwnerInfoHtmlV4Screen(
                    state = vm.state.collectAsState().value, viewModel = vm,
                    onBack = { exits++ }, onPhotos = {}
                )
            }
        }
        val initial = vm.preview("fixture-bar", 0)!!.bar.name
        compose.onNodeWithTag("owner-info-name").performTextClearance()
        compose.onNodeWithTag("owner-info-name").performTextInput("바뀐 매장")
        compose.runOnIdle {
            assertEquals(initial, vm.preview("fixture-bar", 0)!!.bar.name)
        }
        compose.onNodeWithTag("owner-info-save").performScrollTo().assertIsEnabled().performClick()
        compose.runOnIdle {
            assertEquals("바뀐 매장", vm.preview("fixture-bar", 0)!!.bar.name)
            assertEquals(1, exits)
        }
    }

    @Test fun unsavedBackDiscardsDraftWithoutMutatingSharedPreview() {
        val repository = LocalOwnerMockRepository(InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val vm = OwnerMockViewModel(repository)
        var exited = false
        compose.setContent {
            MaterialTheme {
                OwnerInfoHtmlV4Screen(
                    vm.state.collectAsState().value, vm, onBack = { exited = true },
                    onPhotos = {}
                )
            }
        }
        val initial = vm.preview("fixture-bar", 0)!!.bar.name
        compose.onNodeWithTag("owner-info-name").performTextClearance()
        compose.onNodeWithTag("owner-info-name").performTextInput("임시 텍스트")
        compose.onNodeWithContentDescription("뒤로가기").performClick()
        // HTML goes straight back: the info draft was not submitted.
        compose.runOnIdle {
            assertEquals(initial, vm.preview("fixture-bar", 0)!!.bar.name)
            assertEquals(true, exited)
        }
    }

    @Test fun inlineTagSelectionOnlyReachesCustomerAfterFormSave() {
        val vm = OwnerMockViewModel(LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())))
        compose.setContent {
            MaterialTheme {
                OwnerInfoHtmlV4Screen(
                    vm.state.collectAsState().value, vm,
                    onBack = {}, onPhotos = {})
            }
        }
        val before = vm.preview("fixture-bar", 0)!!.bar.tags
        compose.onNodeWithTag("owner-tag-search").performTextInput("혼술바")
        compose.runOnIdle { assertEquals(before, vm.preview("fixture-bar", 0)!!.bar.tags) }
        compose.onNodeWithText("혼술바 ＋").performClick()
        compose.onNodeWithTag("owner-info-save").performScrollTo().assertIsEnabled().performClick()
        compose.runOnIdle {
            assertEquals(true, vm.preview("fixture-bar", 0)!!.bar.tags.contains("혼술바"))
        }
    }

    @Test fun selectingCoverInTwoColumnGridImmediatelyUpdatesSharedPreview() {
        val vm = OwnerMockViewModel(LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())))
        val old = vm.preview("fixture-bar", 0)!!.bar
        val first = com.zerotoone.bottlemap.data.owner.MockPhoto(
            "first", "content://mock/first",
            com.zerotoone.bottlemap.data.owner.MockPhotoKind.BAR_GALLERY)
        val second = first.copy(photoId = "second", uri = "content://mock/second")
        vm.saveBar(old.copy(gallery = listOf(first, second)))
        compose.setContent {
            MaterialTheme {
                OwnerPhotoHtmlV4Screen(
                    vm.state.collectAsState().value, vm, onBack = {})
            }
        }
        compose.onNodeWithTag("owner-photo-tile-1").performClick()
        compose.onNodeWithText("대표 사진 등록").performClick()
        compose.runOnIdle {
            assertEquals("second", vm.preview("fixture-bar", 0)!!.bar.gallery.first().photoId)
        }
    }

    @Test fun photoEditorUsesImmediateActionsAndDoneButton() {
        val vm = OwnerMockViewModel(
            LocalOwnerMockRepository(InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        )
        compose.setContent {
            MaterialTheme {
                OwnerPhotoHtmlV4Screen(vm.state.collectAsState().value, vm, onBack = {})
            }
        }
        compose.onNodeWithTag("owner-photo-add").assertExists()
        compose.onNodeWithTag("owner-photo-done").assertExists()
    }
}
