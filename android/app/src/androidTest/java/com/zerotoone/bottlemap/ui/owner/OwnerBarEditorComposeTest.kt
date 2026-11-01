package com.zerotoone.bottlemap.ui.owner

import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.semantics.SemanticsProperties
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
import com.zerotoone.bottlemap.data.owner.MockExceptionKind
import com.zerotoone.bottlemap.data.owner.MockOperatingException
import com.zerotoone.bottlemap.data.owner.MockPhoto
import com.zerotoone.bottlemap.data.owner.MockPhotoKind
import com.zerotoone.bottlemap.data.owner.MockBrand
import com.zerotoone.bottlemap.data.owner.MockCatalogProduct
import com.zerotoone.bottlemap.data.owner.MockBarMenuItem
import com.zerotoone.bottlemap.data.owner.MockMenuOption
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

    @Test fun unsavedBackShowsConfirmationAndPreservesUntilExplicitDiscard() {
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
        compose.onNodeWithText("변경을 취소할까요?").assertIsDisplayed()
        compose.runOnIdle {
            assertEquals(false, exited)
            assertEquals(initial, vm.preview("fixture-bar", 0)!!.bar.name)
        }
        compose.onNodeWithText("계속 편집").performClick()
        compose.onNodeWithContentDescription("뒤로가기").performClick()
        compose.onNodeWithText("변경 취소").performClick()
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
        compose.onNodeWithText("혼술바 ＋").performScrollTo().performClick()
        compose.onNodeWithText("혼술바 ×").assertExists()
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

    @Test fun customerPreviewExpandsScheduleFromStatusArrowWithoutPourLabel() {
        val vm = OwnerMockViewModel(LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())))
        val saved = vm.preview("fixture-bar", 0)!!.bar.copy(
            defaultPourMl = 45,
            weeklyHours = listOf(com.zerotoone.bottlemap.data.owner.MockWeeklyHours(
                1, false, openMinutes = 18 * 60, closeMinutes = 2 * 60,
                closesNextDay = true))
        )
        vm.saveBar(saved)
        compose.setContent {
            MaterialTheme {
                OwnerPreviewHtmlV4Screen(vm.state.collectAsState().value, vm, onBack = {})
            }
        }
        compose.onNodeWithText("기본 잔 용량", substring = true).assertDoesNotExist()
        compose.onNodeWithText("영업시간", substring = false).assertDoesNotExist()
        compose.onNodeWithTag("owner-preview-hours-toggle").performClick()
        compose.onNodeWithText("18:00 – 익일 02:00", substring = true)
            .assertIsDisplayed()
    }

    @Test fun customerPreviewMapPhonePanelsAndManageReturnFollowHtmlV4() {
        val vm = OwnerMockViewModel(LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())))
        val current = vm.preview("fixture-bar", 0)!!.bar
        vm.saveBar(current.copy(address = "서울시 관악구 관악로 20",
            phone = "02-1234-5678"))
        var manageCount = 0
        compose.setContent {
            MaterialTheme {
                OwnerPreviewHtmlV4Screen(
                    vm.state.collectAsState().value, vm, onBack = {},
                    onManage = { manageCount++ })
            }
        }
        compose.onNodeWithText("지도").performScrollTo().performClick()
        compose.onNodeWithText("서울시 관악구 관악로 20").assertIsDisplayed()
        compose.onNodeWithText("전화").performClick()
        compose.onNodeWithText("02-1234-5678").assertIsDisplayed()
        compose.onNodeWithTag("owner-preview-manage").performClick()
        compose.runOnIdle { assertEquals(1, manageCount) }
    }

    @Test fun operatingCustomerNoteStopsAt100CharactersWithoutCounter() {
        val vm = OwnerMockViewModel(LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())))
        compose.setContent {
            MaterialTheme {
                OwnerOperatingQuickScreen(
                    vm.state.collectAsState().value, vm, onBack = {})
            }
        }
        compose.onNodeWithText("오늘 휴무").performClick()
        compose.onNodeWithTag("owner-operating-note").performTextInput("가".repeat(115))
        val actual = compose.onNodeWithTag("owner-operating-note")
            .fetchSemanticsNode().config[SemanticsProperties.EditableText].text
        assertEquals("가".repeat(100), actual)
        compose.onNodeWithText("100자", substring = true).assertDoesNotExist()
    }

    @Test fun customerStatusNoteAppearsAboveLabelOnlyWhenRequested() {
        val vm = OwnerMockViewModel(LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())))
        val today = ownerToday(System.currentTimeMillis()).toEpochDay()
        val initial = vm.preview("fixture-bar", 0)!!.bar
        vm.saveBar(initial.copy(exceptions = listOf(
            MockOperatingException(
                "qa-tooltip", MockExceptionKind.CLOSED_TODAY, today, today,
                note = "내부 사정",
            )
        )))
        compose.setContent {
            MaterialTheme {
                OwnerPreviewHtmlV4Screen(vm.state.collectAsState().value, vm, onBack = {})
            }
        }
        compose.onNodeWithText("내부 사정").assertDoesNotExist()
        compose.onNodeWithTag("owner-preview-status-label").performClick()
        compose.onNodeWithTag("owner-preview-status-note").assertIsDisplayed()
        compose.onNodeWithText("내부 사정").assertIsDisplayed()
        compose.onNodeWithTag("owner-preview-status-label").performClick()
        compose.onNodeWithText("내부 사정").assertDoesNotExist()
    }

    @Test fun photoPopupCoversImageAndCloseDoesNotAlterSavedGallery() {
        val vm = OwnerMockViewModel(LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())))
        val original = vm.preview("fixture-bar", 0)!!.bar
        val first = MockPhoto("first-photo", "content://mock/first", MockPhotoKind.BAR_GALLERY)
        val second = MockPhoto("second-photo", "content://mock/second", MockPhotoKind.BAR_GALLERY)
        vm.saveBar(original.copy(gallery = listOf(first, second)))
        compose.setContent {
            MaterialTheme {
                OwnerPhotoHtmlV4Screen(vm.state.collectAsState().value, vm, onBack = {})
            }
        }
        compose.onNodeWithTag("owner-photo-tile-1").performClick()
        compose.onNodeWithTag("owner-photo-action-panel").assertIsDisplayed()
        compose.onNodeWithText("대표 사진 등록").assertIsDisplayed()
        compose.onNodeWithText("삭제하기").assertIsDisplayed()
        compose.onNodeWithText("닫기").performClick()
        compose.onNodeWithTag("owner-photo-action-panel").assertDoesNotExist()
        compose.runOnIdle {
            assertEquals(listOf(first, second),
                vm.preview("fixture-bar", 0)!!.bar.gallery)
        }
    }

    @Test fun customerPreviewShowsFourthSavedServingOption() {
        val repo = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val brand = MockBrand("brand-1", "Brand A")
        repo.saveBrand(brand)
        repo.saveCatalogProduct(MockCatalogProduct("product-12", "brand-1",
            "Bottle 12", ageYears = 12))
        repo.saveMenuItem(MockBarMenuItem("menu-1", "fixture-bar", "product-12",
            (1..4).map { i ->
                MockMenuOption("option-$i", pourMl = i * 15, priceKrw = i * 1000)
            }))
        val preview = repo.preview("fixture-bar", 0)!!
        compose.setContent {
            MaterialTheme {
                OwnerPreviewV4Menu(preview.bar, preview, listOf(brand), 0)
            }
        }
        // Search expands the matching category independent of initial grouping.
        compose.onNodeWithTag("owner-preview-menu-search").performTextInput("Bottle")
        compose.onNodeWithText("15ml").assertExists()
        compose.onNodeWithText("45ml").assertExists()
        compose.onNodeWithText("60ml").assertExists()
        compose.onNodeWithText("4,000원").assertExists()
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
