package com.zerotoone.bottlemap.ui.owner.review

import com.zerotoone.bottlemap.data.owner.review.MockPhotoReviewRepository
import com.zerotoone.bottlemap.data.owner.review.MockPhotoReviewScenario
import com.zerotoone.bottlemap.data.owner.review.PhotoReviewRepository
import com.zerotoone.bottlemap.network.BottleMapApiException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** Every button of the v18 review, driven through the ViewModel with the mock repository. */
@OptIn(ExperimentalCoroutinesApi::class)
class PhotoReviewViewModelTest {
    private val dispatcher = UnconfinedTestDispatcher()

    @Before fun setUp() = Dispatchers.setMain(dispatcher)
    @After fun tearDown() = Dispatchers.resetMain()

    private fun vm(scenario: MockPhotoReviewScenario = MockPhotoReviewScenario.BASIC,
        repository: MockPhotoReviewRepository = MockPhotoReviewRepository(scenario)) = PhotoReviewViewModel(repository)

    private val PhotoReviewViewModel.state get() = (load.value as PhotoReviewLoad.Ready).review
    private fun PhotoReviewViewModel.item(id: String) = state.items.first { it.id == id }
    private fun PhotoReviewViewModel.group(id: String) = PhotoReviewRules.displayGroup(state, item(id))

    private fun PhotoReviewViewModel.collectEvents(scope: kotlinx.coroutines.CoroutineScope): MutableList<PhotoReviewEvent> {
        val events = mutableListOf<PhotoReviewEvent>()
        scope.launch(dispatcher) { this@collectEvents.events.collect { events += it } }
        return events
    }

    @Test fun cardsStartFoldedAndExpandOnlyWhenAsked() = runTest(dispatcher) {
        val vm = vm()
        assertTrue(vm.state.items.none { it.expanded })
        vm.toggleExpanded("glen12")
        assertTrue(vm.item("glen12").expanded)
        vm.toggleExpanded("glen12")
        assertFalse(vm.item("glen12").expanded)
    }

    @Test fun choosingThePhotoPriceMovesTheCardAndSaysDone() = runTest(dispatcher) {
        val vm = vm()
        val events = vm.collectEvents(backgroundScope)
        vm.choosePrice("glendronach", PriceChoice.PHOTO)
        assertEquals(15000.0, vm.item("glendronach").price, 0.0)
        assertEquals(ReviewGroup.READY, vm.group("glendronach"))
        assertTrue(PhotoReviewEvent.Toast("확인 완료") in events)
    }

    @Test fun ambiguousYesLinksTheCandidate() = runTest(dispatcher) {
        val vm = vm()
        vm.confirmMatch("hakushu")
        assertEquals("hakushu-dr", vm.item("hakushu").linkedProductId)
        assertFalse(vm.item("hakushu").operatorPending)
        assertEquals(ReviewGroup.READY, vm.group("hakushu"))
    }

    @Test fun ambiguousNoOpensCatalogSearchWithResultsAndExplicitConfirm() = runTest(dispatcher) {
        val vm = vm()
        vm.startCatalogSearch("hakushu")
        assertTrue(vm.item("hakushu").searchMode)
        assertEquals("하쿠슈 DR", vm.item("hakushu").searchDraft)
        vm.typeCatalogQuery("hakushu", "하쿠슈 12")
        vm.searchCatalog("hakushu")
        assertEquals(listOf("hakushu-12"), vm.item("hakushu").searchResults?.map { it.productId })
        vm.selectSearchResult("hakushu", "hakushu-12")
        assertEquals(ReviewGroup.PENDING, vm.group("hakushu"))
        vm.confirmSelectedSearch("hakushu")
        assertEquals("hakushu-12", vm.item("hakushu").linkedProductId)
        assertEquals(ReviewGroup.READY, vm.group("hakushu"))
    }

    @Test fun emptySearchOffersRegisteringAsNew() = runTest(dispatcher) {
        val vm = vm(MockPhotoReviewScenario.CATALOG_EMPTY)
        val events = vm.collectEvents(backgroundScope)
        vm.registerAsNew("hakushu")
        val x = vm.item("hakushu")
        assertEquals(ReviewMatch.NEW, x.match)
        assertEquals("하쿠슈 XX 시음", x.newProductName)
        assertTrue(PhotoReviewEvent.FocusReviewName("hakushu") in events)
    }

    @Test fun candidateNeedsSelectionThenConfirm() = runTest(dispatcher) {
        val vm = vm()
        val events = vm.collectEvents(backgroundScope)
        vm.confirmSelectedCandidate("arran")
        assertTrue(PhotoReviewEvent.Toast("위스키를 먼저 선택해 주세요.") in events)
        vm.chooseCandidate("arran", "arran-sherry")
        assertEquals(ReviewGroup.PENDING, vm.group("arran"))
        vm.confirmSelectedCandidate("arran")
        assertEquals("arran-sherry", vm.item("arran").linkedProductId)
        assertFalse(vm.item("arran").operatorPending)
    }

    @Test fun editionConflictLinksWithoutAskingAndQueuesForOperator() = runTest(dispatcher) {
        val vm = vm(MockPhotoReviewScenario.EDITION_CONFLICT)
        val events = vm.collectEvents(backgroundScope)
        vm.confirmSelectedCandidate("arran")
        assertEquals("arran-port", vm.item("arran").linkedProductId)
        assertEquals(OperatorReason.SELECTED_PRODUCT_CONFLICT, vm.item("arran").operatorReason)
        assertTrue(PhotoReviewEvent.Toast("위스키를 연결했어요. 운영자 확인 대상으로 전달돼요.") in events)
    }

    @Test fun newMenuConfirmGoesToOperatorWithoutCatalogInput() = runTest(dispatcher) {
        val vm = vm()
        vm.confirmNew("bookers")
        val x = vm.item("bookers")
        assertNull(x.linkedProductId)
        assertEquals(OperatorReason.NEW, x.operatorReason)
        assertEquals(ReviewGroup.READY, vm.group("bookers"))
    }

    @Test fun newMenuNameEditClearAndSave() = runTest(dispatcher) {
        val vm = vm(MockPhotoReviewScenario.MANUAL_NAME)
        val events = vm.collectEvents(backgroundScope)
        vm.clearReviewName("bookers")
        vm.saveReviewName("bookers")
        assertTrue(PhotoReviewEvent.Toast("이름을 입력해 주세요.") in events)
        vm.typeReviewName("bookers", "부커스 2025")
        vm.saveReviewName("bookers")
        val x = vm.item("bookers")
        assertEquals("부커스 2025", x.name)
        assertTrue(x.operatorPending)
        assertTrue(PhotoReviewEvent.Toast("메뉴 이름 저장 · 상품 연결은 관리자 검토 대상이에요.") in events)
    }

    @Test fun detailRenameRematchesAndQueuesChangedLink() = runTest(dispatcher) {
        val vm = vm(MockPhotoReviewScenario.LINKED_NAME)
        vm.editDetailName("glen12")
        // As in v18: the card moves to "확인이 필요해요" folded, saying "세부사항에서 저장을 눌러 주세요."
        assertEquals(ReviewGroup.PENDING, vm.group("glen12"))
        assertFalse(vm.item("glen12").expanded)
        assertEquals(listOf(ReviewIssue.DETAIL_NAME), PhotoReviewRules.problems(vm.item("glen12")))
        vm.toggleExpanded("glen12")
        vm.typeDetailName("glen12", "글렌피딕 15")
        vm.saveDetailName("glen12")
        val x = vm.item("glen12")
        assertEquals("gf15", x.linkedProductId)
        assertEquals(OperatorReason.CHANGED, x.operatorReason)
        // Another OCR card (glen15) is already linked to gf15. Backend #164
        // keeps only the first proposal, so the owner must explicitly merge
        // servings and exclude one duplicate before publishing.
        assertEquals(ReviewGroup.PENDING, vm.group("glen12"))
        assertTrue(ReviewIssue.DUPLICATE_PRODUCT in
            PhotoReviewRules.problems(x, vm.state))
        vm.requestExclude("glen15")
        vm.confirmExclude("glen15")
        assertEquals(ReviewGroup.READY, vm.group("glen12"))
    }

    @Test fun conflictPriceChoice() = runTest(dispatcher) {
        val vm = vm(MockPhotoReviewScenario.MERGED_CONFLICT)
        vm.chooseConflictPrice("glen12", 14000.0)
        assertEquals(14000.0, vm.item("glen12").price, 0.0)
        assertEquals(ReviewGroup.READY, vm.group("glen12"))
    }

    @Test fun inlinePriceRejectsBadInputAndCreatesAnOptionForZeroOptionLine() = runTest(dispatcher) {
        val vm = vm(MockPhotoReviewScenario.ZERO_OPTION)
        val events = vm.collectEvents(backgroundScope)
        vm.typeInlinePrice("glen15", "abc")
        vm.commitInlinePrice("glen15")
        assertTrue(PhotoReviewEvent.Toast("가격을 확인해 주세요.") in events)
        vm.typeInlinePrice("glen15", "18,000원")
        vm.commitInlinePrice("glen15")
        val x = vm.item("glen15")
        assertTrue(x.primaryHasOption)
        assertEquals(30.0, x.volume, 0.0)
        assertEquals(VolumeSource.DEFAULT, x.volumeSource)
        assertEquals(ReviewGroup.READY, vm.group("glen15"))
    }

    @Test fun inlineVolumeRejectsDecimal() = runTest(dispatcher) {
        val vm = vm(MockPhotoReviewScenario.BAD_INPUTS)
        val events = vm.collectEvents(backgroundScope)
        vm.typeInlineVolume("glen12", "22.5")
        vm.commitInlineVolume("glen12")
        assertTrue(PhotoReviewEvent.Toast("1 ~ 999 사이의 숫자를 입력해주세요.") in events)
        vm.typeInlineVolume("glen12", "30")
        vm.commitInlineVolume("glen12")
        assertEquals(ReviewGroup.READY, vm.group("glen12"))
    }

    @Test fun defaultPourIsRequiredAndFillsDefaultGlasses() = runTest(dispatcher) {
        val repo = MockPhotoReviewRepository(MockPhotoReviewScenario.NO_DEFAULT)
        val vm = vm(repository = repo)
        val events = vm.collectEvents(backgroundScope)
        assertTrue(PhotoReviewRules.stats(vm.state).noDefault)
        vm.saveDefaultPour("1000")
        assertTrue(PhotoReviewEvent.Toast("1 ~ 999 사이의 숫자를 입력해주세요.") in events)
        vm.saveDefaultPour("45")
        assertEquals(45.0, vm.item("glen12").volume, 0.0)
        assertFalse(PhotoReviewRules.stats(vm.state).noDefault)
        assertEquals(45, repo.savedDefaultPour)
    }

    @Test fun failedLiveDefaultPourSaveDoesNotUnlockPublish() = runTest(dispatcher) {
        val mock = MockPhotoReviewRepository(MockPhotoReviewScenario.NO_DEFAULT)
        val failing = object : PhotoReviewRepository by mock {
            override suspend fun saveDefaultPour(ml: Int) {
                error("서버 저장 실패")
            }
        }
        val vm = PhotoReviewViewModel(failing)
        val events = vm.collectEvents(backgroundScope)
        assertTrue(PhotoReviewRules.stats(vm.state).noDefault)
        vm.saveDefaultPour("45")
        assertTrue(PhotoReviewRules.stats(vm.state).noDefault)
        assertTrue(PhotoReviewEvent.Toast("서버 저장 실패") in events)
    }

    @Test fun typingKeepsTheCardInPlaceUntilTheFieldIsLeft() = runTest(dispatcher) {
        val vm = vm()
        vm.toggleExpanded("glen15")
        vm.typeOptionField("glen15", PhotoReviewRules.OptionField.PRICE, null, "16000")
        assertEquals(ReviewGroup.PENDING, vm.group("glen15"))
        vm.commitOptionField()
        assertEquals(ReviewGroup.READY, vm.group("glen15"))
        assertFalse("A card that moved starts folded", vm.item("glen15").expanded)
        assertTrue(vm.state.show.ready)
    }

    @Test fun optionAddRemoveAndLimit() = runTest(dispatcher) {
        val vm = vm(MockPhotoReviewScenario.WHISKY_OPTIONS)
        val events = vm.collectEvents(backgroundScope)
        // A photo review supports up to ten options, not the manual form's three.
        vm.addOption("glen12")
        assertEquals(3, vm.item("glen12").options.size)
        vm.removeOption("glen12", 1)
        assertEquals(2, vm.item("glen12").options.size)
        vm.addOption("glen12")
        assertEquals(3, vm.item("glen12").options.size)
        assertEquals(ReviewGroup.PENDING, vm.group("glen12"))
        vm.removeOption("glen12", null)
        assertFalse(vm.item("glen12").primaryHasOption)
        vm.addOption("gin")
        assertTrue(PhotoReviewRules.countOptions(vm.item("gin")) >= 2)
        repeat(10) { vm.addOption("gin") }
        assertEquals(10, PhotoReviewRules.countOptions(vm.item("gin")))
        assertTrue(PhotoReviewEvent.Toast("검수 옵션은 최대 10개까지 등록할 수 있어요.") in events)
    }

    @Test fun reclassifyMovesToOtherAndBackRestoringOptions() = runTest(dispatcher) {
        val vm = vm(MockPhotoReviewScenario.RECLASSIFY)
        val options = vm.item("glen12").options
        vm.reclassify("glen12")
        assertEquals(ReviewGroup.OTHER, vm.group("glen12"))
        vm.reclassify("glen12")
        assertEquals(options, vm.item("glen12").options)
        assertEquals(ReviewGroup.READY, vm.group("glen12"))
    }

    @Test fun excludeNeedsConfirmationAndCanBeUndone() = runTest(dispatcher) {
        val vm = vm()
        vm.requestExclude("ardbeg")
        assertEquals(ReviewModalType.EXCLUDE, vm.state.modal?.type)
        vm.dismissModal()
        assertNull(vm.state.modal)
        vm.requestExclude("ardbeg")
        vm.confirmExclude("ardbeg")
        assertEquals(ReviewGroup.EXCLUDED, vm.group("ardbeg"))
        vm.unexclude("ardbeg")
        assertEquals(ReviewGroup.READY, vm.group("ardbeg"))
    }

    @Test fun otherMenuNameCheck() = runTest(dispatcher) {
        val vm = vm(MockPhotoReviewScenario.OTHER_TYPO)
        assertEquals(listOf(ReviewIssue.NAME), PhotoReviewRules.problems(vm.item("gin")))
        vm.confirmName("gin")
        assertEquals(ReviewGroup.OTHER, vm.group("gin"))
    }

    @Test fun sourcePhotoOpensAndCloses() = runTest(dispatcher) {
        val vm = vm(MockPhotoReviewScenario.MERGED_LINES)
        vm.openSourcePhoto("glen12", 0)
        assertEquals(ReviewModal(ReviewModalType.SOURCE_PHOTO, "glen12", 0), vm.state.modal)
        vm.dismissModal()
        assertNull(vm.state.modal)
    }

    @Test fun publishOnlyWhenReadyAndShowsSuccessBeforeLeaving() = runTest(dispatcher) {
        val blocked = vm()
        blocked.requestPublish()
        assertNull(blocked.state.modal)
        val repo = MockPhotoReviewRepository(MockPhotoReviewScenario.READY)
        val vm = vm(repository = repo)
        val events = vm.collectEvents(backgroundScope)
        vm.requestPublish()
        assertEquals(ReviewModalType.PUBLISH, vm.state.modal?.type)
        vm.confirmPublish()
        assertNotNull(repo.published)
        assertTrue(vm.publishOutcome.value is PublishOutcome.Success)
        assertFalse(PhotoReviewEvent.Leave in events)
        vm.leave()
        assertTrue(PhotoReviewEvent.Leave in events)
    }

    @Test fun laterLeavesWithoutPublishingAndKeepsTheDraft() = runTest(dispatcher) {
        val repo = MockPhotoReviewRepository()
        val vm = vm(repository = repo)
        vm.choosePrice("glendronach", PriceChoice.OLD)
        val first = vm.events.first().let { it }
        assertEquals(PhotoReviewEvent.Toast("확인 완료"), first)
        vm.leave()
        assertNull(repo.published)
        assertEquals(PriceChoice.OLD, repo.savedDraft?.items?.first { it.id == "glendronach" }?.priceChoice)
        assertEquals(PriceChoice.OLD, PhotoReviewViewModel(repo).item("glendronach").priceChoice)
    }
    @Test fun doublePublishTapSubmitsExactlyOnceAndDisablesWhileSaving() = runTest(dispatcher) {
        val gate = CompletableDeferred<Unit>()
        val base = MockPhotoReviewRepository(MockPhotoReviewScenario.READY)
        var submits = 0
        val source = object : PhotoReviewRepository by base {
            override suspend fun publish(state: PhotoReviewState) {
                submits++
                gate.await()
            }
        }
        val vm = PhotoReviewViewModel(source)
        vm.requestPublish()
        vm.confirmPublish()
        vm.confirmPublish()
        assertEquals(1, submits)
        assertTrue(vm.publishing.value)
        vm.dismissModal()
        assertNull(vm.state.modal)
        assertTrue(vm.publishOutcome.value is PublishOutcome.Submitting)
        gate.complete(Unit)
        assertFalse(vm.publishing.value)
    }

    @Test fun networkFailureChecksSameImportBeforeRetrying() = runTest(dispatcher) {
        val base = MockPhotoReviewRepository(MockPhotoReviewScenario.READY)
        var attempts = 0
        var published = false
        val source = object : PhotoReviewRepository by base {
            override suspend fun publish(state: PhotoReviewState) {
                attempts++
                if (attempts == 1) throw BottleMapApiException(
                    code = "NETWORK_ERROR", message = "offline")
                published = true
            }
            override suspend fun checkPublishedStatus(): Boolean = published
        }
        val vm = PhotoReviewViewModel(source)
        vm.requestPublish()
        vm.confirmPublish()
        assertFalse(vm.publishing.value)
        assertEquals(PublishFailure.NETWORK,
            (vm.publishOutcome.value as PublishOutcome.Failed).reason)
        vm.requestPublish()
        vm.confirmPublish()
        assertEquals(1, attempts) // no second POST without a GET
        vm.checkPublishStatus(retryWhenReady = true)
        assertEquals(2, attempts)
        assertTrue(vm.publishOutcome.value is PublishOutcome.Success)
    }

    @Test fun unknownResultNeverSubmitsTwiceWithoutStatusConfirmation() = runTest(dispatcher) {
        val base = MockPhotoReviewRepository(MockPhotoReviewScenario.READY)
        var attempts = 0
        val source = object : PhotoReviewRepository by base {
            override suspend fun publish(state: PhotoReviewState) {
                attempts++
                throw BottleMapApiException(httpStatus = 500, code = "HTTP_500", message = "error")
            }
            override suspend fun checkPublishedStatus(): Boolean? = null
        }
        val vm = PhotoReviewViewModel(source)
        vm.requestPublish()
        vm.confirmPublish()
        assertEquals(PublishFailure.SERVER,
            (vm.publishOutcome.value as PublishOutcome.Failed).reason)
        vm.checkPublishStatus()
        assertEquals(PublishFailure.UNKNOWN,
            (vm.publishOutcome.value as PublishOutcome.Failed).reason)
        assertEquals(1, attempts)
        vm.returnToReview()
        assertEquals(1, attempts)
        assertTrue(vm.publishOutcome.value is PublishOutcome.Failed)
    }

    @Test fun appliedStatusReturnsSuccessWithoutNewPost() = runTest(dispatcher) {
        val base = MockPhotoReviewRepository(MockPhotoReviewScenario.READY)
        var attempts = 0
        val source = object : PhotoReviewRepository by base {
            override suspend fun publish(state: PhotoReviewState) {
                attempts++
                throw BottleMapApiException(httpStatus = 500, code = "HTTP_500", message = "error")
            }
            override suspend fun checkPublishedStatus(): Boolean = true
        }
        val vm = PhotoReviewViewModel(source)
        vm.requestPublish()
        vm.confirmPublish()
        vm.checkPublishStatus()
        assertTrue(vm.publishOutcome.value is PublishOutcome.Success)
        assertEquals(1, attempts)
    }

    @Test fun authAndConflictFailuresPreserveReviewState() = runTest(dispatcher) {
        val base = MockPhotoReviewRepository(MockPhotoReviewScenario.READY)
        val source = object : PhotoReviewRepository by base {
            override suspend fun publish(state: PhotoReviewState) {
                throw BottleMapApiException(httpStatus = 401, code = "HTTP_401", message = "auth")
            }
        }
        val vm = PhotoReviewViewModel(source)
        val before = vm.state.items
        vm.requestPublish()
        vm.confirmPublish()
        assertEquals(PublishFailure.AUTH,
            (vm.publishOutcome.value as PublishOutcome.Failed).reason)
        vm.returnToReview()
        assertNull(vm.publishOutcome.value)
        assertEquals(before, vm.state.items)
        assertEquals(PublishFailure.CONFLICT, classifyPublishFailure(
            BottleMapApiException(httpStatus = 409, code = "VERSION_CONFLICT", message = "conflict")))
    }

}
