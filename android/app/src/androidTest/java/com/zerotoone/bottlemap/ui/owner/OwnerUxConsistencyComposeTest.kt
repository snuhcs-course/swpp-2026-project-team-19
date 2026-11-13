package com.zerotoone.bottlemap.ui.owner

import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.test.assertDoesNotExist
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.zerotoone.bottlemap.data.owner.InMemoryMockOwnerStateStore
import com.zerotoone.bottlemap.data.owner.LocalOwnerMockRepository
import com.zerotoone.bottlemap.data.owner.MockImportStatus
import com.zerotoone.bottlemap.data.owner.MockMenuImport
import com.zerotoone.bottlemap.data.owner.OwnerMockFixtures
import com.zerotoone.bottlemap.ui.common.OwnerBottomConfirmSheet
import com.zerotoone.bottlemap.ui.auth.WelcomeScreen
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class OwnerUxConsistencyComposeTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    private fun jobState(status: MockImportStatus): OwnerMockViewModel {
        val original = OwnerMockFixtures.registeredBar()
        val barId = requireNotNull(original.selectedBarId)
        val job = MockMenuImport(
            menuImportId = "reopened-job", barId = barId,
            status = status, reviewVersion = 1, images = emptyList(),
        )
        return OwnerMockViewModel(LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(original.copy(imports = listOf(job))),
        ))
    }

    @Test fun welcomePinIsHalfSizeQuarterScreenCenteredAndTouchesHeadlineTop() {
        compose.setContent { MaterialTheme {
            WelcomeScreen(onBrowseAsGuest = {}, onGoogle = {}, onOwner = {})
        } }
        val root = compose.onNodeWithTag("welcome-screen").getUnclippedBoundsInRoot()
        val pin = compose.onNodeWithTag("welcome-pin").getUnclippedBoundsInRoot()
        val headline = compose.onNodeWithTag("welcome-headline").getUnclippedBoundsInRoot()
        val horizontalCenter = (pin.left + pin.right) / 2
        val expectedCenter = root.left + root.width / 4
        org.junit.Assert.assertTrue(
            kotlin.math.abs((horizontalCenter - expectedCenter).value) <= 1.5f)
        org.junit.Assert.assertTrue(kotlin.math.abs(pin.width.value - 79f) <= 1f)
        org.junit.Assert.assertTrue(kotlin.math.abs(pin.bottom.value - headline.top.value) <= 1.5f)
    }

    @Test fun approvedBarAlwaysOffersManagementEvenIfInitialReviewPending() {
        val snapshot = OwnerMockFixtures.registeredBar()
        val bar = snapshot.bars.first()
        var managedBar: String? = null
        compose.setContent { MaterialTheme {
            OwnerRegistrationDashboard(
                snapshot = snapshot,
                onRegister = {},
                onManage = { managedBar = it.barId },
                onViewApplication = {},
                onCancel = {},
                onDismiss = {},
                onReapply = {},
            )
        } }
        compose.onNodeWithText("매장 관리하기").assertIsDisplayed()
        compose.onNodeWithText("메뉴 검수하기").assertDoesNotExist()
        compose.onNodeWithText("매장 관리하기").performClick()
        compose.runOnIdle { assertEquals(bar.barId, managedBar) }
    }

    @Test fun readyImportWithNoCachedOcrLinesShowsReviewImmediately() {
        val vm = jobState(MockImportStatus.READY_FOR_REVIEW)
        var opened: MockImportStatus? = null
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value,
                vm, {}, {}, { opened = it })
        } }
        compose.onNodeWithText("메뉴 검수 이어서 하기").assertIsDisplayed()
        compose.onNodeWithText("메뉴판 분석 중 · 작업 확인하기").assertDoesNotExist()
        compose.onNodeWithText("메뉴 검수 이어서 하기").performClick()
        compose.runOnIdle { assertEquals(MockImportStatus.READY_FOR_REVIEW, opened) }
    }

    @Test fun blockingOwnerEditsDuringPhotoImportOnlyUsesTopToastCallback() {
        val vm = jobState(MockImportStatus.PROCESSING)
        var notice: String? = null
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value,
                vm, {}, {}, {}, onNotice = { notice = it })
        } }
        compose.onNodeWithTag("manual-menu-add").performClick()
        compose.runOnIdle {
            assertEquals("사진으로 메뉴 등록 작업 중에는 메뉴를 수정할 수 없어요.", notice)
        }
        compose.onNodeWithText("메뉴판 사진 등록 작업 중에는 메뉴를 수정할 수 없어요.")
            .assertDoesNotExist()
    }

    @Test fun destructiveConfirmUsesBottomSheetAndNeverMutatesWithoutConfirmation() {
        var approved = false
        var dismissed = false
        compose.setContent { MaterialTheme {
            OwnerBottomConfirmSheet(
                title = "전체 메뉴를 초기화할까요?",
                message = "모든 메뉴와 용량·가격 정보가 삭제됩니다.",
                confirmLabel = "초기화",
                tag = "test-bottom-sheet",
                onConfirm = { approved = true }, onDismiss = { dismissed = true },
            )
        } }
        compose.onNodeWithTag("test-bottom-sheet").assertIsDisplayed()
        compose.onNodeWithText("전체 메뉴를 초기화할까요?").assertIsDisplayed()
        compose.runOnIdle { assertEquals(false, approved) }
        compose.onNodeWithTag("test-bottom-sheet-confirm").performClick()
        compose.runOnIdle {
            assertEquals(true, approved)
            assertEquals(false, dismissed)
        }
    }
}
