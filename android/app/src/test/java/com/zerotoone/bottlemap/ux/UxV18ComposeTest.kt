package com.zerotoone.bottlemap.ux

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.assertIsNotSelected
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTextReplacement
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.hasText
import com.zerotoone.bottlemap.data.owner.review.MockPhotoReviewRepository
import com.zerotoone.bottlemap.data.owner.review.MockPhotoReviewScenario
import com.zerotoone.bottlemap.navigation.BottomTabs
import com.zerotoone.bottlemap.navigation.MainTab
import com.zerotoone.bottlemap.ui.auth.LoginErrorScreen
import com.zerotoone.bottlemap.ui.auth.WelcomeScreen
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewLoad
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewRules
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewScreen
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewViewModel
import com.zerotoone.bottlemap.ui.owner.review.ReviewGroup
import com.zerotoone.bottlemap.ui.theme.BottleMapTheme
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/** Compose behaviour of the v18 screens (Robolectric, so it runs with the unit tests). */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35], qualifiers = "w390dp-h2600dp-xhdpi")
class UxV18ComposeTest {
    @get:Rule val rule = createComposeRule()

    private fun review(scenario: MockPhotoReviewScenario = MockPhotoReviewScenario.BASIC,
        repo: MockPhotoReviewRepository = MockPhotoReviewRepository(scenario), onLeave: () -> Unit = {}): PhotoReviewViewModel {
        val vm = PhotoReviewViewModel(repo)
        rule.setContent { BottleMapTheme { PhotoReviewScreen(vm, onLeave = onLeave) } }
        rule.waitForIdle()
        return vm
    }

    private fun PhotoReviewViewModel.group(id: String): ReviewGroup {
        val s = (load.value as PhotoReviewLoad.Ready).review
        return PhotoReviewRules.displayGroup(s, s.items.first { it.id == id })
    }

    @Test fun welcomeButtonsReportEachChoice() {
        val calls = mutableListOf<String>()
        rule.setContent { BottleMapTheme { WelcomeScreen({ calls += "guest" }, { calls += "google" }, { calls += "owner" }) } }
        rule.onNodeWithText("Find the bottle first,\nthen the bar.").assertIsDisplayed()
        rule.onNodeWithTag("welcome-pin").assertIsDisplayed()
        rule.onNodeWithText("사장님이신가요?").assertIsDisplayed()
        rule.onNodeWithText("매장 등록하기").assertIsDisplayed()
        rule.onNodeWithText("BottleMap").assertDoesNotExist()
        rule.onNodeWithText("마시고 싶은 위스키, 어디에서 만날까요?").assertDoesNotExist()
        val first = rule.onNodeWithTag("welcome-google").fetchSemanticsNode().boundsInRoot
        val second = rule.onNodeWithTag("welcome-guest").fetchSemanticsNode().boundsInRoot
        assertTrue("Google must be above guest in v20", first.bottom < second.top)
        rule.onNodeWithTag("welcome-google").performClick()
        rule.onNodeWithTag("welcome-guest").performClick()
        rule.onNodeWithTag("welcome-owner").performClick()
        assertEquals(listOf("google", "guest", "owner"), calls)
    }

    @Test fun loginErrorOffersRetryAndGuest() {
        val calls = mutableListOf<String>()
        rule.setContent {
            BottleMapTheme { LoginErrorScreen("Google 로그인에 실패했어요.", { calls += "back" }, { calls += "retry" }, { calls += "guest" }) }
        }
        rule.onNodeWithText("Google 로그인에 실패했어요.").assertIsDisplayed()
        rule.onNodeWithTag("login-error-retry").performClick()
        rule.onNodeWithTag("login-error-guest").performClick()
        assertEquals(listOf("retry", "guest"), calls)
    }

    @Test fun bottomTabsShowTwoTabsAndSelect() {
        var selected = MainTab.SEARCH
        rule.setContent { BottleMapTheme { BottomTabs(selected) { selected = it } } }
        rule.onNodeWithText("검색").assertIsDisplayed()
        rule.onNodeWithText("내 정보").assertIsDisplayed()
        rule.onNodeWithTag("bottom-tab-search").assertIsSelected()
        rule.onNodeWithTag("bottom-tab-account").assertIsNotSelected().performClick()
        assertEquals(MainTab.ACCOUNT, selected)
    }

    @Test fun v20ReviewHasBackOnlyToolbarStepperAndHeader() {
        review()
        rule.onNodeWithTag("review-steps").assertIsDisplayed()
        rule.onNodeWithText("사진 올리기").assertIsDisplayed()
        rule.onNodeWithText("읽기").assertIsDisplayed()
        rule.onNode(
            hasText("확인") and hasAnyAncestor(hasTestTag("review-steps"))
        ).assertIsDisplayed()
        rule.onNodeWithText("더하기").assertIsDisplayed()
        rule.onNodeWithText("메뉴 검수").assertIsDisplayed()
    }

    @Test fun cardsStartFoldedAndOpenOnlyByToggle() {
        review()
        rule.onNodeWithTag("review-details-glen15").assertDoesNotExist()
        rule.onNodeWithTag("review-toggle-glen15").performClick()
        rule.onNodeWithTag("review-details-glen15").assertIsDisplayed()
        rule.onNodeWithText("접기").assertIsDisplayed()
    }

    @Test fun choosingPriceMovesTheCardToReady() {
        val vm = review()
        rule.onNodeWithTag("review-price-photo-glendronach").performClick()
        rule.waitForIdle()
        assertEquals(ReviewGroup.READY, vm.group("glendronach"))
        rule.onNodeWithText("확인 완료").assertIsDisplayed()
    }

    @Test fun candidateConfirmNeedsASelection() {
        val vm = review()
        rule.onNodeWithTag("review-candidate-confirm-arran").performClick()
        assertEquals(ReviewGroup.PENDING, vm.group("arran"))
        rule.onNodeWithTag("review-candidate-arran-arran-sherry").performClick()
        rule.onNodeWithTag("review-candidate-confirm-arran").performClick()
        rule.waitForIdle()
        assertEquals(ReviewGroup.READY, vm.group("arran"))
    }

    @Test fun catalogSearchAndRegisterNew() {
        val vm = review(MockPhotoReviewScenario.CATALOG_EMPTY)
        rule.onNodeWithText("검색된 위스키가 없어요.").assertIsDisplayed()
        rule.onNodeWithTag("review-register-new-hakushu").performClick()
        rule.onNodeWithTag("review-name-input-hakushu").assertIsDisplayed()
        rule.onNodeWithTag("review-name-save-hakushu").performClick()
        rule.waitForIdle()
        assertEquals(ReviewGroup.READY, vm.group("hakushu"))
    }

    @Test fun inlinePriceEntry() {
        val vm = review()
        rule.onNodeWithTag("review-price-input-glen15").performTextReplacement("16,000")
        rule.onNodeWithTag("review-price-save-glen15").performClick()
        rule.waitForIdle()
        assertEquals(ReviewGroup.READY, vm.group("glen15"))
    }

    @Test fun photoModalClosesWithX() {
        review()
        rule.onNodeWithTag("review-source-glen15").performClick()
        rule.onNodeWithTag("review-photo-modal").assertIsDisplayed()
        rule.onNodeWithText("3번째 장 1번째 줄", useUnmergedTree = true)
        rule.onNodeWithTag("review-photo-close").performClick()
        rule.onNodeWithTag("review-photo-modal").assertDoesNotExist()
    }

    @Test fun excludeAsksFirstAndCanBeUndone() {
        val vm = review(MockPhotoReviewScenario.BASIC)
        rule.onNodeWithTag("review-expand-ardbeg").performClick()
        rule.onNodeWithTag("review-exclude-ardbeg").performClick()
        rule.onNodeWithText("기존에 등록된 메뉴는 삭제하지 않아요.").assertIsDisplayed()
        rule.onNodeWithTag("review-exclude-sheet-confirm").performClick()
        rule.waitForIdle()
        assertEquals(ReviewGroup.EXCLUDED, vm.group("ardbeg"))
        rule.onNodeWithTag("review-group-excluded").performClick()
        rule.onNodeWithTag("review-unexclude-ardbeg").performClick()
        rule.waitForIdle()
        assertEquals(ReviewGroup.READY, vm.group("ardbeg"))
    }

    @Test fun publishIsBlockedUntilEverythingIsChecked() {
        val vm = review()
        rule.onNodeWithTag("photo-review-list").performScrollToNode(hasTestTag("review-publish"))
        rule.onNodeWithText("검수 0/5 완료").assertIsDisplayed()
        // Scrolling the publish action into view may clip the preceding helper
        // text with the new v20 stepper height; assert content, not viewport.
        rule.onNodeWithText("확인이 필요한 메뉴 5개를 먼저 검수해 주세요.").assertExists()
        rule.onNodeWithTag("review-publish").performClick()
        assertTrue((vm.load.value as PhotoReviewLoad.Ready).review.modal == null)
    }

    @Test fun missingDefaultPourExplainsWhyPublishIsBlocked() {
        review(MockPhotoReviewScenario.NO_DEFAULT)
        rule.onNodeWithTag("review-default-pour-panel").assertIsDisplayed()
        rule.onNodeWithTag("photo-review-list").performScrollToNode(hasTestTag("review-publish"))
        rule.onNodeWithText("매장 기본 잔 용량을 입력해주세요.").assertIsDisplayed()
    }

    @Test fun publishConfirmShowsResultBeforeMenuManagement() {
        val repo = MockPhotoReviewRepository(MockPhotoReviewScenario.READY)
        var left = false
        review(repo = repo, onLeave = { left = true })
        rule.onNodeWithTag("photo-review-list").performScrollToNode(hasTestTag("review-publish"))
        rule.onNodeWithTag("review-publish").performClick()
        rule.onNodeWithText("이대로 게시할까요?").assertIsDisplayed()
        // Only whisky / other menu / excluded counts appear in the confirmation.
        rule.onNodeWithText("연결 없이 등록할 메뉴", substring = true).assertDoesNotExist()
        rule.onNodeWithText("게시 후 운영자 확인", substring = true).assertDoesNotExist()
        rule.onNodeWithText("기존 가격 변경", substring = true).assertDoesNotExist()
        rule.onNodeWithText("여러 줄을 합친 위스키", substring = true).assertDoesNotExist()
        rule.onNodeWithTag("review-publish-sheet-confirm").performClick()
        rule.waitForIdle()
        assertFalse(left)
        rule.onNodeWithTag("review-publish-result").assertExists()
        rule.onNodeWithText("메뉴를 추가했어요.").assertIsDisplayed()
        assertTrue(repo.published != null)
        rule.onNodeWithTag("review-result-leave").performClick()
        rule.waitForIdle()
        assertTrue(left)
    }

    @Test fun laterLeavesWithoutPublishing() {
        val repo = MockPhotoReviewRepository()
        var left = false
        review(repo = repo, onLeave = { left = true })
        rule.onNodeWithTag("review-later").performClick()
        rule.waitForIdle()
        assertTrue(left)
        assertTrue(repo.published == null)
    }

    @Test fun mergedLinesShowTheMergeNoticeAndConflictAsksToChoose() {
        review(MockPhotoReviewScenario.MERGED_CONFLICT)
        rule.onNodeWithText("가격을 선택해 주세요.").assertIsDisplayed()
        rule.onNodeWithText("같은 위스키가 두 줄 있어 하나로 합쳤어요.").assertIsDisplayed()
    }
}
