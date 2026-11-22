package com.zerotoone.bottlemap.ui.owner

import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTextReplacement
import androidx.compose.ui.test.performImeAction
import androidx.compose.ui.test.hasText
import com.zerotoone.bottlemap.ui.auth.AccountScreen
import com.zerotoone.bottlemap.ui.auth.AuthUiState
import com.zerotoone.bottlemap.ui.auth.UserPrivacySettings
import com.zerotoone.bottlemap.ui.customer.CustomerP18Results
import com.zerotoone.bottlemap.ui.customer.P18SearchViewModel
import com.zerotoone.bottlemap.data.CustomerDiscoverySource
import com.zerotoone.bottlemap.network.*
import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.Density
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
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

    @Test fun welcomeRequiresAgeButNotOptionalUsageForEveryEntry() {
        val settings=UserPrivacySettings.get(compose.activity)
        val previous=settings.usageEnabled.value
        try {
            settings.setUsageEnabled(false)
            val calls=mutableListOf<String>()
            compose.setContent { MaterialTheme {
                WelcomeScreen({calls+="guest"},{calls+="google"},{calls+="owner"})
            } }
            for(tag in listOf("welcome-google","welcome-guest","welcome-owner"))
                compose.onNodeWithTag(tag).assertIsNotEnabled()
            compose.onNodeWithTag("welcome-usage-consent").performClick()
            compose.onNodeWithTag("welcome-google").assertIsNotEnabled()
            compose.onNodeWithTag("welcome-usage-consent").performClick()
            compose.onNodeWithTag("welcome-age-confirmation").performClick()
            for(tag in listOf("welcome-google","welcome-guest","welcome-owner"))
                compose.onNodeWithTag(tag).assertIsEnabled().performClick()
            compose.runOnIdle {assertEquals(listOf("google","guest","owner"),calls);assertEquals(false,settings.usageEnabled.value)}
            compose.onNodeWithTag("welcome-age-confirmation").performClick()
            compose.onNodeWithTag("welcome-guest").assertIsNotEnabled()
            compose.onNodeWithTag("welcome-privacy").assertExists()
        } finally {settings.setUsageEnabled(previous)}
    }

    @Test fun guestAccountHasPolicyAndQualityControlInApprovedOrder() {
        compose.setContent { MaterialTheme {
            AccountScreen(AuthUiState.Guest,{},{},{},{})
        } }
        val titles=listOf("공지사항","문의하기","개인정보처리방침","사용 기록 보내기")
        val tops=titles.map {compose.onNodeWithText(it).fetchSemanticsNode().boundsInRoot.top}
        for(i in 1 until tops.size) org.junit.Assert.assertTrue(tops[i]>tops[i-1])
        compose.onNodeWithText("로그아웃").assertDoesNotExist()
        compose.onNodeWithTag("account-usage-consent").assertExists()
    }

    @Test fun selectedWhiskyResultsKeepEditableSearchAboveScrolledRows() {
        val rows=(0..19).map {i->SearchResultDto("b$i","테스트 매장 $i","주소",37.0,127.0,
            productId="p",productDisplayName="아드벡 10",menuDisplayName="아드벡 10",
            options=listOf(SearchOptionDto(pourMl=30,priceKrw=10000+i,sortOrder=0)),menuUpdatedAt="2026-11-22T00:00:00Z")}
        val source=object:CustomerDiscoverySource {
            override suspend fun popularProducts(limit:Int)=PopularProductsResponseDto()
            override suspend fun searchProduct(query:String?,productId:String?,source:String,latitude:Double?,longitude:Double?)=
                SearchBarsResponseDto(query,"exact",listOf(MatchedProductDto("p","아드벡 10","아드벡",resultCount=20)),rows,false)
        }
        val vm=P18SearchViewModel(source)
        var submitted=""
        compose.setContent { MaterialTheme {
            CustomerP18Results(null,"p","popular",{},{_,_->},onSearchAgain={submitted=it},viewModel=vm)
        } }
        compose.waitUntil(5000) {compose.onAllNodesWithTag("customer-result-list").fetchSemanticsNodes().isNotEmpty()}
        val top=compose.onNodeWithTag("customer-search-field").fetchSemanticsNode().boundsInRoot.top
        compose.onNodeWithTag("customer-result-list").performScrollToNode(hasText("테스트 매장 19"))
        assertEquals(top,compose.onNodeWithTag("customer-search-field").fetchSemanticsNode().boundsInRoot.top,1f)
        compose.onNodeWithTag("customer-search-field").performTextReplacement("라가불린 16")
        compose.onNodeWithTag("customer-search-field").performImeAction()
        compose.runOnIdle {assertEquals("라가불린 16",submitted)}
    }

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

    @Test fun welcomePinAndHeadlineMatchTheApprovedHtmlStack() {
        compose.setContent { MaterialTheme { WelcomeScreen({}, {}, {}) } }
        val root=compose.onNodeWithTag("welcome-screen").getUnclippedBoundsInRoot()
        val pin=compose.onNodeWithTag("welcome-pin").getUnclippedBoundsInRoot()
        val headline=compose.onNodeWithTag("welcome-headline").getUnclippedBoundsInRoot()
        assertEquals(20f,(pin.left-root.left).value,1f)
        assertEquals(158f,(pin.right-pin.left).value,1f)
        assertEquals(194f,(pin.bottom-pin.top).value,1f)
        assertEquals(14f,(headline.top-pin.bottom).value,1.5f)
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
        compose.onNodeWithTag("manual-menu-edit-guidance").assertIsDisplayed()
        compose.onNodeWithText("사진 등록 중 · 편집 불가")
            .assertIsDisplayed()
        compose.onNodeWithText("메뉴를 선택해서 편집하세요").assertDoesNotExist()
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
    @Test fun completedPhotoJobRestoresOriginalEditGuidance() {
        val vm = jobState(MockImportStatus.APPLIED)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-edit-guidance").assertIsDisplayed()
        compose.onNodeWithText("메뉴를 선택해서 편집하세요").assertIsDisplayed()
        compose.onNodeWithText("사진 등록 중 · 편집 불가")
            .assertDoesNotExist()
    }

    @Test fun managerHomeKeepsReadableTitlesWhenSystemFontScaleIsDoubled() {
        val original = OwnerMockFixtures.registeredBar()
        val vm = OwnerMockViewModel(LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(original)))
        compose.setContent { MaterialTheme {
            val density = LocalDensity.current
            CompositionLocalProvider(LocalDensity provides Density(density.density, 2.0f)) {
                OwnerManagementHomeScreen(vm.state.collectAsState().value,
                    viewModel = vm,
                    onRetry = {}, onBack = {}, onPreview = {}, onInfo = {},
                    onStatus = {}, onMenu = {}, onAddBar = {}, onJob = {})
            }
        } }
        compose.onNodeWithText("매장 정보 관리").assertIsDisplayed()
        compose.onNodeWithText("영업 상태 변경").assertIsDisplayed()
        val infoCard = compose.onNodeWithTag("owner-home-info-card",
            useUnmergedTree = true).getUnclippedBoundsInRoot()
        val infoTitle = compose.onNodeWithTag("owner-home-info-title",
            useUnmergedTree = true).getUnclippedBoundsInRoot()
        val statusCard = compose.onNodeWithTag("owner-home-status-card",
            useUnmergedTree = true).getUnclippedBoundsInRoot()
        val statusTitle = compose.onNodeWithTag("owner-home-status-title",
            useUnmergedTree = true).getUnclippedBoundsInRoot()
        for ((label, card) in listOf(infoTitle to infoCard, statusTitle to statusCard)) {
            org.junit.Assert.assertTrue(label.top.value >= card.top.value - 1f)
            org.junit.Assert.assertTrue(label.bottom.value <= card.bottom.value + 1f)
            org.junit.Assert.assertTrue(label.left.value >= card.left.value - 1f)
            org.junit.Assert.assertTrue(label.right.value <= card.right.value + 1f)
        }
    }

    @Test fun hourButtonKeepsTouchTargetButDrawsCompactFrame() {
        compose.setContent { MaterialTheme {
            V4HourButton("18:30", onClick = {},
                modifier = androidx.compose.ui.Modifier.testTag("owner-hour-touch"))
        } }
        val touch = compose.onNodeWithTag("owner-hour-touch").getUnclippedBoundsInRoot()
        val visible = compose.onNodeWithTag("owner-hour-visual",
            useUnmergedTree = true).getUnclippedBoundsInRoot()
        org.junit.Assert.assertTrue((touch.bottom - touch.top).value >= 47.5f)
        org.junit.Assert.assertTrue((touch.right - touch.left).value >= 47.5f)
        org.junit.Assert.assertTrue((visible.bottom - visible.top) < (touch.bottom - touch.top))
        org.junit.Assert.assertTrue((visible.right - visible.left) <= (touch.right - touch.left))
    }

}
