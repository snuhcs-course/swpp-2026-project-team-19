package com.zerotoone.bottlemap.ui.owner

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
import com.zerotoone.bottlemap.data.owner.MockPreview
import com.zerotoone.bottlemap.data.owner.MockReviewDecision
import com.zerotoone.bottlemap.data.owner.OwnerMockRepository
import kotlinx.coroutines.flow.StateFlow

/**
 * Shared mock-data ViewModel. Inject [OwnerMockRepository] in tests and later replace its
 * implementation with an adapter to only the agreed real API contract.
 */
class OwnerMockViewModel(private val repository: OwnerMockRepository) : ViewModel() {
    val state: StateFlow<MockOwnerLoadState> = repository.state
    fun retry() = repository.retryLoad()
    fun register(application: MockOwnerApplication) = repository.registerApplication(application)
    fun saveRegistrationDraft(draft: MockRegistrationDraft?) = repository.saveRegistrationDraft(draft)
    fun approveForFixture(id: String, bar: MockBar) = repository.approveForFixture(id, bar)
    fun seedExistingCandidateForFixture(bar: MockBar) = repository.seedExistingCandidateForFixture(bar)
    fun submitRegistrationDraftForFixture() = repository.submitRegistrationDraftForFixture()
    fun closeApplicationForFixture(id: String, status: MockApplicationStatus) = repository.closeApplicationForFixture(id, status)
    fun dismissRejectedForFixture(id: String) = repository.dismissRejectedForFixture(id)
    fun saveBar(bar: MockBar) = repository.saveBar(bar)
    fun confirmMenuInformation(barId: String, atEpochMs: Long) = repository.confirmMenuInformation(barId, atEpochMs)
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
    fun setSoldOut(itemId: String, soldOut: Boolean) = repository.setSoldOut(itemId, soldOut)
    fun deleteMenuItem(id: String) = repository.deleteMenuItem(id)
    fun clearMenuForBar(barId: String) = repository.clearMenuForBar(barId)
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
