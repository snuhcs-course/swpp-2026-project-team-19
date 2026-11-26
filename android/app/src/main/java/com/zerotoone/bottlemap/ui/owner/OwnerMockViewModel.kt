package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.telemetry.*
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.zerotoone.bottlemap.data.owner.MockBar
import com.zerotoone.bottlemap.data.owner.MockOperatingException
import com.zerotoone.bottlemap.data.owner.MockBrand
import com.zerotoone.bottlemap.data.owner.MockBarMenuItem
import com.zerotoone.bottlemap.data.owner.MockCatalogProduct
import com.zerotoone.bottlemap.data.owner.MockOwnerApplication
import com.zerotoone.bottlemap.data.owner.MockApplicationStatus
import com.zerotoone.bottlemap.data.owner.MockRegistrationDraft
import com.zerotoone.bottlemap.data.owner.MockOwnerLoadState
import com.zerotoone.bottlemap.data.owner.MockPhotoExtractionSource
import com.zerotoone.bottlemap.data.owner.MockPhoto
import com.zerotoone.bottlemap.data.owner.MockImportStatus
import com.zerotoone.bottlemap.data.owner.MockPreview
import com.zerotoone.bottlemap.data.owner.MockReviewDecision
import com.zerotoone.bottlemap.data.owner.OwnerMockRepository
import kotlinx.coroutines.flow.StateFlow

/**
 * Shared mock-data ViewModel. Inject [OwnerMockRepository] in tests and later replace its
 * implementation with an adapter to only the agreed real API contract.
 */
class OwnerMockViewModel(
    private val repository: OwnerMockRepository,
    // Android Compose tests can exercise the REAL production routing without
    // spending an NTS quota. Null in all production ViewModel factories.
    private val businessVerificationFixture:
        (suspend (String, String, String) -> String)? = null,
    private val registrationSubmissionFixture: (suspend () -> Unit)? = null,
    private val telemetry: Telemetry = AppTelemetry.current,
) : ViewModel() {
    val state: StateFlow<MockOwnerLoadState> = repository.state
    fun retry() = repository.retryLoad()
    fun register(application: MockOwnerApplication) = repository.registerApplication(application)
    private var applicationType: ApplicationType? = null
    private var applicationSubmitted = false
    private val failedImports = mutableSetOf<String>()
    private fun snapshot() = when (val loaded = state.value) {
        is MockOwnerLoadState.Ready -> loaded.snapshot
        is MockOwnerLoadState.Empty -> loaded.snapshot
        else -> null
    }
    private fun startApplication(draft: MockRegistrationDraft) {
        val type = if (draft.kind == com.zerotoone.bottlemap.data.owner.MockApplicationKind.EXISTING_BAR)
            ApplicationType.CLAIM else ApplicationType.NEW
        if (applicationType != type) {
            applicationType = type
            applicationSubmitted = false
            telemetry.log(TelemetryEvent.OwnerApplicationStarted(type))
        }
    }
    fun saveRegistrationDraft(draft: MockRegistrationDraft?) {
        if (draft != null && snapshot()?.registrationDraft == null) {
            applicationType = null; applicationSubmitted = false
        }
        repository.saveRegistrationDraft(draft)
        if (draft == null) { applicationType = null; applicationSubmitted = false }
        else if (draft.resumePageKey != null && draft.resumePageKey != "METHOD") startApplication(draft)
    }
    /** Production registration stays suspend so UI waits for both submission and menu-photo upload. */
    suspend fun verifyBusinessBeforeApplicationLive(
        registrationNumber: String, representativeName: String, openingDate: String,
    ): String = when {
        businessVerificationFixture != null ->
            businessVerificationFixture.invoke(
                registrationNumber, representativeName, openingDate)
        repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository ->
            repository.verifyBusinessBeforeApplicationLive(
                registrationNumber, representativeName, openingDate)
        else -> "matched"
    }

    suspend fun submitRegistrationDraftLive() {
        val draft = snapshot()?.registrationDraft
        if (draft != null) startApplication(draft)
        try {
            if (draft != null) registrationPhoneError(draft)?.let {
                throw com.zerotoone.bottlemap.ui.common.UserInputException(it)
            }
            when {
                registrationSubmissionFixture != null -> registrationSubmissionFixture.invoke()
                repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository ->
                    repository.submitRegistrationDraftLive()
                else -> repository.submitRegistrationDraftForFixture()
            }
            if (!applicationSubmitted) {
                telemetry.log(TelemetryEvent.OwnerApplicationSubmitted(applicationType ?: ApplicationType.NEW))
                applicationSubmitted = true
            }
        } catch (cancelled: kotlinx.coroutines.CancellationException) { throw cancelled }
        catch (error: Exception) {
            telemetry.log(TelemetryEvent.OwnerApplicationFailed(ErrorCode.from(error)))
            throw error
        }
    }

    suspend fun loadExistingOwnerApplicationLive(applicationId: String) {
        if (repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            repository.loadExistingOwnerApplicationLive(applicationId)
        else {
            val current = when (val load = state.value) {
                is MockOwnerLoadState.Ready -> load.snapshot
                is MockOwnerLoadState.Empty -> load.snapshot
                else -> error("신청 내역을 먼저 불러와 주세요.")
            }
            require(current.applications.any { it.applicationId == applicationId })
        }
    }

    suspend fun readBusinessCertificateLive(uri: String):
        com.zerotoone.bottlemap.network.OwnerCertificateOcrDto? =
        if (repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            repository.readBusinessCertificateLive(uri)
        else null

    fun approveForFixture(id: String, bar: MockBar) = repository.approveForFixture(id, bar)
    fun seedExistingCandidateForFixture(bar: MockBar) = repository.seedExistingCandidateForFixture(bar)
    fun submitRegistrationDraftForFixture() = repository.submitRegistrationDraftForFixture()
    fun closeApplicationForFixture(id: String, status: MockApplicationStatus) = repository.closeApplicationForFixture(id, status)
    suspend fun cancelOwnerApplicationLive(id: String) {
        if(repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            repository.cancelOwnerApplicationLive(id)
        else repository.closeApplicationForFixture(id, MockApplicationStatus.CANCELED)
    }
    fun dismissRejectedForFixture(id: String) = repository.dismissRejectedForFixture(id)
    fun saveBar(bar: MockBar) = repository.saveBar(bar)
    suspend fun saveBarLive(bar: MockBar) {
        if(repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            repository.saveBarLive(bar)
        else repository.saveBar(bar)
    }
    fun confirmMenuInformation(barId: String, atEpochMs: Long) = repository.confirmMenuInformation(barId, atEpochMs)
    suspend fun applyOperatingExceptionLive(barId: String, exception: MockOperatingException) {
        if(repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            repository.applyOperatingExceptionLive(barId, exception)
        else repository.applyOperatingException(barId, exception)
    }
    suspend fun cancelOperatingExceptionLive(barId: String, exceptionId: String) {
        if(repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            repository.cancelOperatingExceptionLive(barId)
        else repository.cancelOperatingException(barId, exceptionId)
    }

    fun applyOperatingException(barId: String, exception: MockOperatingException) = repository.applyOperatingException(barId, exception)
    fun cancelOperatingException(barId: String, exceptionId: String) = repository.cancelOperatingException(barId, exceptionId)
    fun selectBar(barId: String) = repository.selectBar(barId)
    fun saveBrand(brand: MockBrand) = repository.saveBrand(brand)
    fun saveProduct(product: MockCatalogProduct) = repository.saveCatalogProduct(product)
    fun saveMenuItem(item: MockBarMenuItem) = repository.saveMenuItem(item)
    fun saveManualMenuItem(
        item: MockBarMenuItem, newProduct: MockCatalogProduct? = null,
        newBrand: MockBrand? = null,
    ) = repository.saveManualMenuItem(item, newProduct, newBrand)
    suspend fun saveManualMenuItemLive(
        item: MockBarMenuItem, newProduct: MockCatalogProduct?, newBrand: MockBrand?,
    ) {
        if(repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            repository.saveManualMenuItemLive(item, newProduct, newBrand)
        else repository.saveManualMenuItem(item, newProduct, newBrand)
    }
    suspend fun setSoldOutLive(itemId: String, soldOut: Boolean) {
        if(repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            repository.setSoldOutLive(itemId, soldOut)
        else repository.setSoldOut(itemId, soldOut)
    }
    suspend fun deleteMenuItemLive(itemId: String) {
        if(repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            repository.deleteMenuItemLive(itemId)
        else repository.deleteMenuItem(itemId)
    }
    suspend fun clearMenuForBarLive(barId: String) {
        if(repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            repository.clearMenuForBarLive(barId)
        else repository.clearMenuForBar(barId)
    }
    suspend fun confirmMenuInformationLive(barId: String) {
        if(repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            repository.confirmMenuInformationLive(barId)
        else repository.confirmMenuInformation(barId, System.currentTimeMillis())
    }
    suspend fun cancelPhotoImportLive(importId: String) {
        if(repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            repository.cancelPhotoImportLive(importId)
        else repository.discardPhotoImport(importId)
    }

    fun setSoldOut(itemId: String, soldOut: Boolean) = repository.setSoldOut(itemId, soldOut)
    fun deleteMenuItem(id: String) = repository.deleteMenuItem(id)
    fun clearMenuForBar(barId: String) = repository.clearMenuForBar(barId)
    suspend fun searchExistingBarCandidatesLive(query: String) {
        if(repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            repository.searchExistingBarCandidatesLive(query)
    }

    suspend fun searchCatalogBrandsLive(query: String) {
        if(repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            repository.searchCatalogBrandsLive(query)
    }

    suspend fun searchCatalogLive(query: String):
        List<com.zerotoone.bottlemap.network.OwnerCatalogProductDto> =
        if(repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            repository.searchCatalogLive(query)
        else emptyList()

    fun usesProductionOwnerApi(): Boolean =
        businessVerificationFixture != null || registrationSubmissionFixture != null ||
            repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository
    fun pendingRepresentativePhotoWarning(): String? =
        (repository as? com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            ?.pendingCoverWarning

    suspend fun submitPhotoImportLive(barId: String, photos: List<MockPhoto>): String {
        if (photos.isNotEmpty()) telemetry.log(TelemetryEvent.MenuImportStarted(
            // Mixed selections are classified by the first selected photo.
            photos.first().telemetrySource, PhotoCount.from(photos.size)))
        return try {
            if (repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
                repository.submitPhotoImportLive(barId, photos)
            else repository.queuePhotoImport(barId, photos)
        } catch (cancelled: kotlinx.coroutines.CancellationException) { throw cancelled }
        catch (error: Exception) {
            telemetry.log(TelemetryEvent.MenuImportFailed(ImportStage.UPLOAD, ErrorCode.from(error)))
            throw error
        }
    }

    suspend fun pollPhotoImportLive(importId: String): MockImportStatus {
        val status = if (repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            repository.pollPhotoImportLive(importId)
        else error("Local fixture must be supplied for Mock polling")
        if (status == MockImportStatus.FAILED && failedImports.add(importId)) {
            telemetry.log(TelemetryEvent.MenuImportFailed(ImportStage.EXTRACTION,
                snapshot()?.imports?.firstOrNull { it.menuImportId == importId }?.failureCode ?: ErrorCode.UNKNOWN))
        }
        return status
    }

    fun photoPublishWarning(): String? =
        (repository as? com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            ?.lastPublishWarning

    fun consumePhotoPublishWarning(): String? =
        (repository as? com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            ?.consumePhotoPublishWarning()

    suspend fun publishPhotoImportLive(importId: String, version: Int): Int? =
        if(repository is com.zerotoone.bottlemap.data.owner.LiveOwnerScreenRepository)
            repository.publishPhotoImportLive(importId, version)
        else repository.publishAddOnly(importId, version)

    fun queuePhotoImport(barId: String, photos: List<MockPhoto>): String =
        repository.queuePhotoImport(barId, photos)
    fun finishPhotoImport(id: String, source: MockPhotoExtractionSource): MockImportStatus =
        repository.finishPhotoImport(id, source)
    fun cancelPhotoImport(id: String) = repository.cancelPhotoImport(id)
    fun discardPhotoImport(id: String) = repository.discardPhotoImport(id)
    fun resetPhotoReview(id: String, version: Int) = repository.resetPhotoReview(id, version)
    fun retryFailedPhotoImport(id: String): String = repository.retryFailedPhotoImport(id)
    fun importPhotos(barId: String, uris: List<String>, source: MockPhotoExtractionSource): String =
        repository.startPhotoImport(barId, uris, source)
    fun review(importId: String, lineId: String, version: Int, decision: MockReviewDecision) =
        repository.decideLine(importId, lineId, version, decision)
    fun publish(importId: String, version: Int): Int = repository.publishAddOnly(importId, version)
    fun preview(barId: String, nowEpochMs: Long): MockPreview? = repository.preview(barId, nowEpochMs)

    class Factory(private val repository: OwnerMockRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(OwnerMockViewModel::class.java))
            return OwnerMockViewModel(repository) as T
        }
    }
}

