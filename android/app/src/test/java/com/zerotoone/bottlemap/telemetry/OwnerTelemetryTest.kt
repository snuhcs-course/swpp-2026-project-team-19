package com.zerotoone.bottlemap.telemetry

import com.zerotoone.bottlemap.data.owner.*
import com.zerotoone.bottlemap.data.owner.review.PhotoReviewRepository
import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.ui.owner.OwnerMockViewModel
import com.zerotoone.bottlemap.ui.owner.review.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.*
import org.junit.After
import org.junit.Before
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class OwnerTelemetryTest {
    private val dispatcher=StandardTestDispatcher()
    @Before fun setup() { Dispatchers.setMain(dispatcher) }
    @After fun cleanup() { Dispatchers.resetMain() }
    private class ReviewRepo : PhotoReviewRepository {
        var state=PhotoReviewState(items=listOf(ReviewItem(id="id",name="private menu",type=ReviewItemType.OTHER,price=9000.0)))
        var failure:Exception?=null
        var draftFailure:Exception?=null
        var committed=false
        override suspend fun loadReview()=state
        override suspend fun searchCatalog(query:String)=emptyList<CatalogProduct>()
        override suspend fun exactMatches(name:String)=emptyList<CatalogProduct>()
        override suspend fun needsOperatorCheck(item:ReviewItem,product:CatalogProduct)=false
        override suspend fun saveDefaultPour(ml:Int) { }
        override suspend fun saveDraft(state:PhotoReviewState) { draftFailure?.let { throw it }; this.state=state }
        override suspend fun publish(state:PhotoReviewState) { committed=true;failure?.let { throw it } }
        override suspend fun checkPublishedStatus()=committed
    }
    @Test fun reviewReloadAndDuplicatePublishDoNotDuplicateEvents()=runTest(dispatcher) {
        val repo=ReviewRepo();val fake=FakeTelemetry();var now=0L
        val vm=PhotoReviewViewModel(repo,fake){now};advanceUntilIdle()
        vm.reload();advanceUntilIdle()
        now=180_000
        vm.requestPublish();vm.confirmPublish();vm.confirmPublish();advanceUntilIdle()
        assertEquals(listOf(TelemetryEvent.MenuReviewOpened,
            TelemetryEvent.MenuPublished(CheckCount.ZERO,ReviewTime.FROM_3_TO_10)),fake.events)
    }
    @Test fun lostPublishResponseRecordsFailureThenConfirmedSuccessWithoutResubmit()=runTest(dispatcher) {
        val repo=ReviewRepo().apply { failure=BottleMapApiException(code="NETWORK_ERROR",message="private") }
        val fake=FakeTelemetry();val vm=PhotoReviewViewModel(repo,fake){100L};advanceUntilIdle()
        vm.requestPublish();vm.confirmPublish();advanceUntilIdle()
        assertTrue(fake.events.contains(TelemetryEvent.MenuPublishFailed(ErrorCode.NETWORK_ERROR)))
        vm.checkPublishStatus();advanceUntilIdle()
        vm.checkPublishStatus();advanceUntilIdle()
        assertEquals(1,fake.events.filterIsInstance<TelemetryEvent.MenuPublished>().size)
        assertEquals(1,fake.events.filterIsInstance<TelemetryEvent.MenuReviewOpened>().size)
    }
    @Test fun initialPendingCountSurvivesCorrectionsBeforePublish()=runTest(dispatcher) {
        val repo=ReviewRepo().apply { state=state.copy(items=state.items.map { it.copy(price=0.0) }) }
        val fake=FakeTelemetry();var now=0L
        val vm=PhotoReviewViewModel(repo,fake){now};advanceUntilIdle()
        // Repository reload represents recovered corrected draft; first-open pending count is retained.
        repo.state=repo.state.copy(items=repo.state.items.map { it.copy(price=9000.0) })
        vm.reload();advanceUntilIdle();now=600_000
        vm.requestPublish();vm.confirmPublish();advanceUntilIdle()
        assertEquals(TelemetryEvent.MenuPublished(CheckCount.ONE_TO_FIVE,ReviewTime.FROM_10_TO_30),fake.events.last())
    }
    @Test fun applicationTypeAndErrorCodeAreRecordedWithoutPrivateInput()=runTest(dispatcher) {
        val repo=LocalOwnerMockRepository(InMemoryMockOwnerStateStore())
        val fake=FakeTelemetry()
        val vm=OwnerMockViewModel(repo,registrationSubmissionFixture={
            throw BottleMapApiException(code="FORBIDDEN",message="private@example.invalid")
        },telemetry=fake)
        vm.saveRegistrationDraft(MockRegistrationDraft(kind=MockApplicationKind.EXISTING_BAR,
            existingBarId="private-id",resumePageKey="BN",contactPhone="01012345678",storePhone="028801234"))
        vm.saveRegistrationDraft((repo.state.value as? MockOwnerLoadState.Empty)?.snapshot?.registrationDraft
            ?: (repo.state.value as MockOwnerLoadState.Ready).snapshot.registrationDraft)
        try { vm.submitRegistrationDraftLive();fail() } catch (_:BottleMapApiException) { }
        assertEquals(listOf(TelemetryEvent.OwnerApplicationStarted(ApplicationType.CLAIM),
            TelemetryEvent.OwnerApplicationFailed(ErrorCode.FORBIDDEN)),fake.events)
    }
    @Test fun successfulApplicationIsMeasuredAfterAcknowledgementOnlyOnce()=runTest(dispatcher) {
        val repo=LocalOwnerMockRepository(InMemoryMockOwnerStateStore());val fake=FakeTelemetry()
        val vm=OwnerMockViewModel(repo,registrationSubmissionFixture={},telemetry=fake)
        vm.saveRegistrationDraft(MockRegistrationDraft(resumePageKey="BN",contactPhone="01012345678",storePhone="028801234"))
        vm.submitRegistrationDraftLive();vm.submitRegistrationDraftLive()
        assertEquals(listOf(TelemetryEvent.OwnerApplicationStarted(ApplicationType.NEW),
            TelemetryEvent.OwnerApplicationSubmitted(ApplicationType.NEW)),fake.events)
    }
    @Test fun autosaveConflictIsNotReportedAsAnAttemptedPublication()=runTest(dispatcher) {
        val repo=ReviewRepo();val fake=FakeTelemetry()
        val vm=PhotoReviewViewModel(repo,fake);advanceUntilIdle()
        repo.draftFailure=com.zerotoone.bottlemap.data.owner.review.ReviewDraftConflictException()
        vm.toggleExpanded("id");advanceUntilIdle()
        assertEquals(listOf(TelemetryEvent.MenuReviewOpened),fake.events)
    }
    @Test fun uploadRecordsSourceAndCountButNeverThePhotoOrBarIdentifiers()=runTest(dispatcher) {
        val local=LocalOwnerMockRepository(InMemoryMockOwnerStateStore())
        val repo=object:OwnerMockRepository by local {
            override fun queuePhotoImport(barId:String,photos:List<MockPhoto>):String="import-id"
        }
        val fake=FakeTelemetry();val vm=OwnerMockViewModel(repo,telemetry=fake)
        assertEquals("import-id",vm.submitPhotoImportLive("private-bar", listOf(
            MockPhoto("private-photo","file:///private",MockPhotoKind.MENU_CAPTURE,ImportSource.CAMERA))))
        assertEquals(listOf(TelemetryEvent.MenuImportStarted(ImportSource.CAMERA,PhotoCount.ONE)),fake.events)
    }
    @Test fun uploadFailureAddsOnlyTheAllowlistedCodeAndCancellationIsNotAFailure()=runTest(dispatcher) {
        val local=LocalOwnerMockRepository(InMemoryMockOwnerStateStore())
        var cancelled=false
        val repo=object:OwnerMockRepository by local {
            override fun queuePhotoImport(barId:String,photos:List<MockPhoto>):String {
                if(cancelled) throw kotlinx.coroutines.CancellationException()
                throw BottleMapApiException(code="FORBIDDEN",message="private URI")
            }
        }
        val fake=FakeTelemetry();val vm=OwnerMockViewModel(repo,telemetry=fake)
        val photos=(1..6).map { MockPhoto("id-$it","file:///private",MockPhotoKind.MENU_CAPTURE) }
        try { vm.submitPhotoImportLive("private",photos);fail() } catch(_:BottleMapApiException) { }
        assertEquals(listOf(TelemetryEvent.MenuImportStarted(ImportSource.GALLERY,PhotoCount.SIX_PLUS),
            TelemetryEvent.MenuImportFailed(ImportStage.UPLOAD,ErrorCode.FORBIDDEN)),fake.events)
        cancelled=true
        try { vm.submitPhotoImportLive("private",photos);fail() } catch(_:kotlinx.coroutines.CancellationException) { }
        assertEquals(1,fake.events.filterIsInstance<TelemetryEvent.MenuImportFailed>().size)
    }

}
