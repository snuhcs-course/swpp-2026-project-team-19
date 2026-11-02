package com.zerotoone.bottlemap.ui.owner

import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.test.assertExists
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.zerotoone.bottlemap.data.owner.*
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Reference: ACTION_FIRST v4 PDF 2–19. Tests the existing Mock state transitions,
 * not real NTS/OCR/approval API responses or unverified pixel parity. */
@RunWith(AndroidJUnit4::class)
class OwnerRegistrationV4ComposeTest {
    @get:Rule val compose=createAndroidComposeRule<ComponentActivity>()

    private fun show(snapshot:MockOwnerSnapshot=MockOwnerSnapshot()):OwnerMockViewModel {
        val vm=OwnerMockViewModel(LocalOwnerMockRepository(InMemoryMockOwnerStateStore(snapshot)))
        compose.setContent {
            MaterialTheme {
                OwnerOnboardingScreen(vm, onBack={}, onFirstReview={},
                    onManagerPreview={}, startRegistration=true)
            }
        }
        return vm
    }

    @Test fun introScrolledContentContainsAllFourReferenceStepsAndExactPreparationRows() {
        show()
        compose.onNodeWithText("매장 등록은\n이렇게 진행돼요").assertExists()
        for(text in listOf("사업자 정보 확인","사업자등록번호, 대표자 성명, 개업일",
            "매장 정보 입력","이름, 사진, 주소, 연락처","메뉴판 사진 올리기",
            "최대 15장","운영팀 승인","승인 전에는 손님에게 보이지 않아요",
            "미리 준비해 주세요","사업자등록증","가게 사진 1장","메뉴판 사진")) {
            compose.onNodeWithText(text).assertExists()
        }
        compose.onNodeWithTag("registration-intro-steps").assertExists()
        compose.onNodeWithText("시작하기").performClick()
        compose.onNodeWithText("사업자등록증으로\n한 번에 채울까요?").assertExists()
        compose.onNodeWithText("사진으로 채우기").assertExists()
        compose.onNodeWithText("직접 입력하기").assertExists()
    }

    @Test fun manualBusinessFormKeepsDigitsAndTransitionsToNextStages() {
        val vm=show()
        compose.onNodeWithText("시작하기").performClick()
        compose.onNodeWithText("직접 입력하기").performClick()
        compose.onNodeWithText("사업자등록번호를\n알려주세요").assertExists()
        for(digit in "1234567891")compose.onNodeWithText(digit.toString()).performClick()
        compose.onNodeWithText("123-45-67891").assertExists()
        compose.onNodeWithText("다음").performClick()
        compose.onNodeWithTag("registration-representative").performTextInput("김민준")
        compose.onNodeWithText("다음").performClick()
        compose.onNodeWithText("개업일을\n알려주세요").assertExists()
        for(digit in "20190514")compose.onNodeWithText(digit.toString()).performClick()
        compose.onNodeWithText("2019-05-14".replace("-",".")).assertExists()
        compose.onNodeWithText("다음").performClick()
        compose.onNodeWithText("이 정보로\n확인할게요").assertExists()
        compose.runOnIdle {
            val draft=(vm.state.value as MockOwnerLoadState.Ready).snapshot.registrationDraft!!
            assertEquals("1234567891",draft.businessNumberDigits)
            assertEquals("김민준",draft.representativeName)
            assertEquals("2019-05-14",draft.openingDateIso)
        }
        compose.onNodeWithText("국세청에 확인하기").performClick()
        compose.waitUntil(5000) {
            compose.onAllNodesWithText("사업자 정보가\n확인됐어요")
                .fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("다음").performClick()
        compose.onNodeWithText("매장 이름을\n알려주세요").assertExists()
    }

    @Test fun completeReviewSubmitsMockPendingApplicationWithoutNtsNetworkCall() {
        val gallery=MockPhoto("cover","content://mock/cover",MockPhotoKind.BAR_GALLERY)
        val menu=MockPhoto("menu","content://mock/menu",MockPhotoKind.MENU_CAPTURE)
        val draft=MockRegistrationDraft(
            businessNumberDigits="1234567891",representativeName="김민준",
            openingDateIso="2019-05-14",proposedBarName="몰트 앤 무드",
            proposedBarAddress="서울특별시 관악구 봉천로12길 8",
            proposedBarAddressDetail="2층",storePhone="025551234",
            contactPhone="01012345678",applicantGallery=listOf(gallery),
            initialMenuPhotos=listOf(menu),resumePageKey="REVIEW"
        )
        val vm=show(MockOwnerSnapshot(registrationDraft=draft))
        compose.waitUntil(4000) {
            compose.onAllNodesWithText("이렇게\n신청할게요")
                .fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("사업자 정보").assertExists()
        compose.onNodeWithText("확인 완료").assertExists()
        compose.onNodeWithText("등록번호").assertExists()
        compose.onNodeWithText("신청하기").performClick()
        compose.onNodeWithText("신청을 마쳤어요").assertExists()
        compose.runOnIdle {
            val state=vm.state.value as MockOwnerLoadState.Ready
            assertEquals(1,state.snapshot.applications.size)
            assertEquals(MockApplicationStatus.PENDING,state.snapshot.applications.single().status)
            assertNull(state.snapshot.registrationDraft)
            assertEquals(1,state.snapshot.applications.single()
                .registrationPhotos.count{it.kind==MockPhotoKind.MENU_CAPTURE})
        }
    }
}
