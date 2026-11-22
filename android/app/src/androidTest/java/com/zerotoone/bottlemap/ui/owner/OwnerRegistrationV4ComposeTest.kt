package com.zerotoone.bottlemap.ui.owner

import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertTextEquals
import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTextReplacement
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
                OwnerOnboardingScreen(vm, onBack={},
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
        compose.onNodeWithTag("registration-business-number")
            .performTextInput("1234567891")
        // No app-owned keypad; the system number IME is attached to the field.
        assertEquals(0, compose.onAllNodesWithText("⌫").fetchSemanticsNodes().size)
        compose.onNodeWithText("123-45-67891").assertExists()
        compose.onNodeWithText("다음").performClick()
        compose.onNodeWithTag("registration-representative").performTextInput("김민준")
        compose.onNodeWithText("다음").performClick()
        compose.onNodeWithText("개업일을\n알려주세요").assertExists()
        compose.onNodeWithTag("registration-opening-date")
            .performTextInput("20190514")
        compose.onNodeWithText("2019-05-14".replace("-",".")).assertExists()
        compose.onNodeWithText("다음").performClick()
        compose.onNodeWithText("이 정보로\n확인할게요").assertExists()
        compose.runOnIdle {
            val draft=(vm.state.value as MockOwnerLoadState.Ready).snapshot.registrationDraft!!
            assertEquals("1234567891",draft.businessNumberDigits)
            assertEquals("김민준",draft.representativeName)
            assertEquals("2019-05-14",draft.openingDateIso)
        }
        compose.onNodeWithText("확인하기").performClick()
        compose.waitUntil(5000) {
            compose.onAllNodesWithText("사업자 정보가\n확인됐어요")
                .fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("다음").performClick()
        compose.onNodeWithText("매장 이름을\n알려주세요").assertExists()
    }

    @Test fun mismatchBackCorrectedDateThenContinueAdvancesWithoutLoop() {
        // This reproduces the failing LIVE navigation, not the Mock VERIFYING
        // animation. The server responses are faked so no NTS quota is used.
        val initial = MockRegistrationDraft(
            businessNumberDigits = "1234567891",
            representativeName = "김민준",
            openingDateIso = "2019-05-13",
            resumePageKey = "BIZCHECK",
        )
        val repo = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(MockOwnerSnapshot(registrationDraft = initial)))
        val requests = mutableListOf<String>()
        val vm = OwnerMockViewModel(repo,
            businessVerificationFixture = { number, name, date ->
                assertEquals("1234567891", number)
                assertEquals("김민준", name)
                requests.add(date)
                if (date == "2019-05-13") "not_matched" else "unavailable"
            })
        compose.setContent {
            MaterialTheme {
                OwnerOnboardingScreen(vm, onBack = {}, onManagerPreview = {},
                    startRegistration = true)
            }
        }

        fun waitFor(text: String) {
            compose.waitUntil(5000) {
                compose.onAllNodesWithText(text).fetchSemanticsNodes().isNotEmpty()
            }
        }
        waitFor("이 정보로\n확인할게요")
        compose.onNodeWithText("확인하기").performClick()
        compose.waitUntil(5000) {
            compose.onAllNodesWithText("사업자 정보가\n맞지 않아요")
                .fetchSemanticsNodes().isNotEmpty()
        }
        // Hardware Back, as in the Galaxy S23 reproduction.
        compose.runOnUiThread {
            compose.activity.onBackPressedDispatcher.onBackPressed()
        }
        waitFor("이 정보로\n확인할게요")
        compose.onAllNodesWithTag("registration-review-edit")[2].performClick()
        waitFor("개업일을\n알려주세요")
        compose.onNodeWithTag("registration-opening-date")
            .performTextReplacement("2019.05.14")
        compose.onNodeWithText("다음").performClick()
        waitFor("이 정보로\n확인할게요")
        compose.onNodeWithText("확인하기").performClick()
        compose.waitUntil(5000) {
            compose.onAllNodesWithText("지금은 국세청 확인이\n어려워요")
                .fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("계속하기").performClick()
        waitFor("매장 이름을\n알려주세요")
        compose.runOnIdle {
            assertEquals(listOf("2019-05-13", "2019-05-14"), requests)
            val saved = (vm.state.value as MockOwnerLoadState.Ready)
                .snapshot.registrationDraft!!
            assertEquals("2019-05-14", saved.openingDateIso)
            assertEquals("BARNAME", saved.resumePageKey)
        }
        // The old success/failure history must not bounce to another
        // mismatch result on the next user Back.
        compose.runOnUiThread {
            compose.activity.onBackPressedDispatcher.onBackPressed()
        }
        waitFor("이 정보로\n확인할게요")
    }

    @Test fun actualApplicationMismatchThenCorrectDateMustAdvanceToBarDetails() {
        // UAT 4.9 exact transition: POST fails with BUSINESS_VERIFICATION_FAILED,
        // return to the read-back page, edit the date and verify successfully.
        // No real NTS or application API calls are made.
        val certificate = MockPhoto(
            "cover-test", "content://fixture/cover", MockPhotoKind.BAR_GALLERY)
        val menu = MockPhoto(
            "menu-test", "content://fixture/menu", MockPhotoKind.MENU_CAPTURE)
        val original = MockRegistrationDraft(
            businessNumberDigits = "1234567891",
            representativeName = "김민준",
            openingDateIso = "2019-05-13",
            proposedBarName = "테스트 매장",
            proposedBarAddress = "서울특별시 관악구 봉천로 12",
            storePhone = "02-555-1234",
            contactPhone = "010-1234-5678",
            applicantGallery = listOf(certificate),
            initialMenuPhotos = listOf(menu),
            resumePageKey = "BIZCHECK",
        )
        val repo = LocalOwnerMockRepository(InMemoryMockOwnerStateStore(
            MockOwnerSnapshot(registrationDraft = original)))
        val requestedDates = mutableListOf<String>()
        var submitAttempts = 0
        val vm = OwnerMockViewModel(
            repo,
            businessVerificationFixture = { _, _, date ->
                requestedDates.add(date)
                "matched"
            },
            registrationSubmissionFixture = {
                submitAttempts++
                throw com.zerotoone.bottlemap.network.BottleMapApiException(
                    code = "BUSINESS_VERIFICATION_FAILED",
                    message = "Business registration mismatch",
                    httpStatus = 400)
            },
        )
        compose.setContent {
            MaterialTheme {
                OwnerOnboardingScreen(vm, onBack = {}, onManagerPreview = {},
                    startRegistration = true)
            }
        }
        fun waitFor(title: String) {
            compose.waitUntil(5000) {
                compose.onAllNodesWithText(title).fetchSemanticsNodes().isNotEmpty()
            }
        }
        waitFor("이 정보로\n확인할게요")
        compose.onNodeWithText("확인하기").performClick()
        waitFor("사업자 정보가\n확인됐어요")
        compose.onNodeWithText("다음").performClick()
        for (page in listOf("매장 이름을\n알려주세요", "매장 사진을\n올려 주세요",
            "매장 주소를\n알려주세요", "매장 전화번호를\n알려주세요",
            "메뉴판 사진을\n올려 주세요", "연락받을 번호를\n알려주세요")) {
            waitFor(page)
            compose.onNodeWithText("다음").performClick()
        }
        waitFor("이렇게\n신청할게요")
        compose.onNodeWithText("신청하기").performClick()
        waitFor("사업자 정보가\n맞지 않아요")
        compose.onNodeWithText("다시 확인하기").performClick()
        waitFor("이 정보로\n확인할게요")
        compose.onAllNodesWithTag("registration-review-edit")[2].performClick()
        waitFor("개업일을\n알려주세요")
        compose.onNodeWithTag("registration-opening-date")
            .performTextReplacement("2019.05.14")
        compose.onNodeWithText("다음").performClick()
        waitFor("이 정보로\n확인할게요")
        compose.onNodeWithText("확인하기").performClick()
        waitFor("사업자 정보가\n확인됐어요")
        compose.onNodeWithText("다음").performClick()
        waitFor("매장 이름을\n알려주세요")
        compose.runOnIdle {
            assertEquals(1, submitAttempts)
            assertEquals(listOf("2019-05-13", "2019-05-14"), requestedDates)
            val saved = (vm.state.value as MockOwnerLoadState.Ready)
                .snapshot.registrationDraft!!
            assertEquals("2019-05-14", saved.openingDateIso)
            assertEquals("BARNAME", saved.resumePageKey)
        }
    }

    @Test fun unavailable404VerificationContinuesWithoutAnotherReadback() {
        val draft = MockRegistrationDraft(
            businessNumberDigits = "1234567891",
            representativeName = "김민준", openingDateIso = "2019-05-14",
            resumePageKey = "BIZCHECK",
        )
        val repo = LocalOwnerMockRepository(InMemoryMockOwnerStateStore(
            MockOwnerSnapshot(registrationDraft = draft)))
        val vm = OwnerMockViewModel(repo,
            businessVerificationFixture = { _, _, _ ->
                throw com.zerotoone.bottlemap.network.BottleMapApiException(
                    httpStatus = 404, code = "HTTP_404", message = "Not Found")
            })
        compose.setContent {
            MaterialTheme {
                OwnerOnboardingScreen(vm, onBack = {}, onManagerPreview = {},
                    startRegistration = true)
            }
        }
        compose.waitUntil(5000) {
            compose.onAllNodesWithText("이 정보로\n확인할게요")
                .fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("확인하기").performClick()
        compose.waitUntil(5000) {
            compose.onAllNodesWithText("지금은 국세청 확인이\n어려워요")
                .fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("계속하기").performClick()
        compose.onNodeWithText("매장 이름을\n알려주세요").assertExists()
    }

    @Test fun registrationMenuUsesPr96HorizontalPhotoSourceDialogWithoutChangingText() {
        val photo=MockPhoto("preexisting","content://mock/preexisting",
            MockPhotoKind.MENU_CAPTURE)
        val draft=MockRegistrationDraft(resumePageKey="MENUS",initialMenuPhotos=listOf(photo))
        show(MockOwnerSnapshot(registrationDraft=draft))
        compose.waitUntil(4000) {
            compose.onAllNodesWithText("메뉴판 사진을\n올려 주세요")
                .fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("메뉴판 순서대로 올려 주세요").assertExists()
        compose.onNodeWithText("AI가 메뉴를 읽어 두면, 승인된 뒤에 확인만 하고 공개할 수 있어요.").assertExists()
        compose.onNodeWithTag("registration-menu-photo-1").assertExists()
        compose.onNodeWithTag("registration-add-menu").performClick()
        compose.onNodeWithText("사진을 어떻게 추가할까요?").assertExists()
        compose.onNodeWithTag("stage7-source-camera").assertExists()
        compose.onNodeWithTag("stage7-source-gallery").assertExists()
    }

    @Test fun whiskeyLoadingReusesAnimatedPr96Canvas() {
        compose.setContent {
            MaterialTheme {
                RegistrationCenterContent("사업자 정보를\n확인하고 있어요",
                    "국세청 정보와 비교하고 있어요.",loading=true)
            }
        }
        compose.onNodeWithTag("registration-processing-glass").assertExists()
    }

    @Test fun realVerificationErrorComposablesRetainAllThreeOutcomes() {
        val outcome=androidx.compose.runtime.mutableStateOf(OwnerVerifyOutcome.MISMATCH)
        compose.setContent { MaterialTheme { RegistrationVerifyException(outcome.value) } }
        for((state,tag) in listOf(
            OwnerVerifyOutcome.MISMATCH to "registration-verify-mismatch",
            OwnerVerifyOutcome.UNAVAILABLE to "registration-verify-unavailable",
            OwnerVerifyOutcome.LIMIT to "registration-verify-limit"
        )) {
            compose.runOnIdle { outcome.value=state }
            compose.onNodeWithTag(tag).assertExists()
        }
    }

    @Test fun uploadedScreenshotPartialOcrShowsMissingOpeningDateAndDisabledCta() {
        compose.setContent {
            MaterialTheme {
                RegistrationOcrPartialReview("123-45-67891","김민준",onEdit={})
            }
        }
        compose.onNodeWithText("읽은 내용이\n맞는지 확인해 주세요").assertExists()
        compose.onNodeWithText("읽지 못했어요").assertExists()
        compose.onNodeWithText("읽지 못한 항목은 직접 입력해 주세요.").assertExists()
        compose.onNodeWithText("입력").assertExists()
    }

    @Test fun dismissedApplicationSheetUsesApprovedShortCopy() {
        compose.setContent {
            MaterialTheme {
                RegistrationApplicationConfirmSheet(
                    kind=RegistrationApplicationSheet.DISMISS,
                    onClose={},onConfirm={}
                )
            }
        }
        compose.onNodeWithText("같은 매장은 언제든 다시 신청할 수 있어요.").assertExists()
        compose.onNodeWithTag("registration-dismiss-sheet").assertExists()
        compose.onNodeWithText("지우기").assertExists()
    }

    @Test fun editableReviewShowsCompactEditControlsWhileDetailsRemainReadOnly() {
        val triggered=androidx.compose.runtime.mutableStateOf(false)
        compose.setContent {
            MaterialTheme {
                RegistrationRow("대표 사진","1장",onEdit={triggered.value=true})
            }
        }
        compose.onNodeWithTag("registration-review-edit").assertExists()
        compose.onNodeWithText("수정").performClick()
        compose.runOnIdle { org.junit.Assert.assertTrue(triggered.value) }
    }

    @Test fun concurrentApplicationConflictOpensTheServerIdentifiedExistingApplication() {
        val draft = MockRegistrationDraft(
            businessNumberDigits="1234567891", representativeName="김민준", openingDateIso="2019-05-14",
            proposedBarName="작성 중인 매장", proposedBarAddress="서울특별시 관악구 봉천로12길 8",
            storePhone="025551234", contactPhone="01012345678", resumePageKey="REVIEW",
            applicantGallery=listOf(MockPhoto("cover","content://mock/cover",MockPhotoKind.BAR_GALLERY)),
            initialMenuPhotos=listOf(MockPhoto("menu","content://mock/menu",MockPhotoKind.MENU_CAPTURE)),
        )
        val existing = MockOwnerApplication("existing-application", MockApplicationKind.NEW_BAR,
            MockApplicationStatus.PENDING, "서버가 지정한 신청", proposedBarAddress="기존 주소")
        val base = LocalOwnerMockRepository(InMemoryMockOwnerStateStore(
            MockOwnerSnapshot(registrationDraft=draft, applications=listOf(existing))))
        var submits = 0
        val repo = object : OwnerMockRepository by base {
            override fun submitRegistrationDraftForFixture(): String {
                submits++
                throw com.zerotoone.bottlemap.network.BottleMapApiException(
                    code="OWNER_APPLICATION_EXISTS", httpStatus=409, message="raw conflict",
                    details=mapOf("applicationId" to existing.applicationId))
            }
        }
        val vm = OwnerMockViewModel(repo)
        compose.setContent { MaterialTheme {
            OwnerOnboardingScreen(vm, onBack={}, onManagerPreview={}, startRegistration=true)
        } }
        compose.waitUntil(4000) {
            compose.onAllNodesWithText("이렇게\n신청할게요").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("신청하기").performClick()
        compose.onNodeWithText("신청한 내용").assertExists()
        compose.onNodeWithText("서버가 지정한 신청").assertExists()
        compose.onNodeWithText("raw conflict").assertDoesNotExist()
        compose.onNodeWithText("신청을 마쳤어요").assertDoesNotExist()
        compose.runOnIdle { assertEquals(1, submits) }
    }

    @Test fun contactThenPublicPhoneCopiesExplicitlyAndReviewEditsKeepTheLink() {
        val draft=MockRegistrationDraft(
            businessNumberDigits="1234567891",representativeName="김민준",openingDateIso="2019-05-14",
            proposedBarName="테스트 매장",proposedBarAddress="서울특별시 관악구 봉천로12길 8",
            applicantGallery=listOf(MockPhoto("cover","content://mock/cover",MockPhotoKind.BAR_GALLERY)),
            initialMenuPhotos=listOf(MockPhoto("menu","content://mock/menu",MockPhotoKind.MENU_CAPTURE)),
            resumePageKey="CONTACT")
        val vm=show(MockOwnerSnapshot(registrationDraft=draft))
        compose.waitUntil(4000) {compose.onAllNodesWithTag("registration-contact").fetchSemanticsNodes().isNotEmpty()}
        compose.onNodeWithTag("registration-contact").performTextReplacement("025551234")
        compose.onNodeWithText("다음").performClick()
        compose.onNodeWithTag("registration-store-phone").assertExists()
        compose.onNodeWithText("가게 전화가 없어요").assertDoesNotExist()
        compose.onNodeWithText("다음").assertIsNotEnabled()
        compose.onNodeWithTag("registration-use-contact-phone").performClick()
        compose.onNodeWithTag("registration-store-phone").assertTextEquals("02-555-1234")
        compose.onNodeWithText("다음").performClick()
        compose.onNodeWithText("이렇게\n신청할게요").assertExists()
        compose.runOnIdle {
            val saved=(vm.state.value as MockOwnerLoadState.Ready).snapshot.registrationDraft!!
            assertEquals("025551234",saved.storePhone)
            assertEquals(true,saved.storePhoneMatchesContact)
        }
        val edits=compose.onAllNodesWithTag("registration-review-edit")
        edits[edits.fetchSemanticsNodes().size-1].performClick()
        compose.onNodeWithTag("registration-contact").performTextReplacement("07012345678")
        compose.onNodeWithText("다음").performClick()
        compose.onNodeWithText("이렇게\n신청할게요").assertExists()
        compose.runOnIdle {
            val saved=(vm.state.value as MockOwnerLoadState.Ready).snapshot.registrationDraft!!
            assertEquals("07012345678",saved.storePhone)
            assertEquals("07012345678",saved.contactPhone)
        }
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

