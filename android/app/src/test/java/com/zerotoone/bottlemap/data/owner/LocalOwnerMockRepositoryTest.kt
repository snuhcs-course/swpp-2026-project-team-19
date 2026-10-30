package com.zerotoone.bottlemap.data.owner

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalOwnerMockRepositoryTest {
    private fun repo(store: MockOwnerStateStore = InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())) =
        LocalOwnerMockRepository(store)

    private fun ready(r: OwnerMockRepository): MockOwnerSnapshot = when (val state = r.state.value) {
        is MockOwnerLoadState.Ready -> state.snapshot
        is MockOwnerLoadState.Empty -> state.snapshot
        else -> error("Expected loaded mock state: $state")
    }

    private fun catalog(r: OwnerMockRepository) {
        r.saveBrand(MockBrand("brand-1", "Brand A"))
        r.saveCatalogProduct(MockCatalogProduct("product-12", "brand-1", "Bottle 12", ageYears = 12))
        r.saveCatalogProduct(MockCatalogProduct("product-16", "brand-1", "Bottle 16", ageYears = 16))
    }

    private fun serving(id: String, ml: Int, price: Int) =
        MockMenuOption(id, pourMl = ml, priceKrw = price)

    private fun rejects(operation: () -> Unit) {
        var failed = false
        try {
            operation()
        } catch (_: IllegalArgumentException) {
            failed = true
        } catch (_: IllegalStateException) {
            failed = true
        }
        assertTrue("Expected invalid mock operation to fail", failed)
    }

    @Test fun emptyDefaultAndRetryOfStorageErrorAreExplicit() {
        val empty = repo(InMemoryMockOwnerStateStore())
        assertTrue(empty.state.value is MockOwnerLoadState.Empty)
        assertTrue(ready(empty).bars.isEmpty())
        var fail = true
        val store = object : MockOwnerStateStore {
            override fun read(): MockOwnerSnapshot? {
                if (fail) error("mock disk unavailable")
                return MockOwnerSnapshot()
            }
            override fun write(snapshot: MockOwnerSnapshot) = Unit
        }
        val subject = repo(store)
        assertTrue(subject.state.value is MockOwnerLoadState.Error)
        fail = false
        subject.retryLoad()
        assertTrue(subject.state.value is MockOwnerLoadState.Empty)
    }

    @Test fun registerApproveForFixtureAndRestorationUseSameStore() {
        val store = InMemoryMockOwnerStateStore()
        val r = repo(store)
        r.registerApplication(
            MockOwnerApplication("application-a", MockApplicationKind.NEW_BAR,
                MockApplicationStatus.PENDING, proposedBarName = "Test Bar")
        )
        assertEquals(1, ready(r).applications.size)
        assertTrue(ready(r).bars.isEmpty())
        r.approveForFixture("application-a", MockBar("bar-a", "Test Bar", "Mock address"))
        assertEquals("bar-a", ready(r).selectedBarId)
        assertEquals(MockApplicationStatus.APPROVED, ready(r).applications.single().status)
        val secondInstance = repo(store) // simulates restored repository after process death
        assertEquals("bar-a", ready(secondInstance).bars.single().barId)
        assertEquals(1, ready(secondInstance).applications.size)
    }

    @Test fun sameProductSupportsManyServingOptionsButNotDuplicateMenuProduct() {
        val r = repo()
        catalog(r)
        r.saveMenuItem(MockBarMenuItem("menu-1", "fixture-bar", "product-12",
            listOf(serving("option-15", 15, 9000), serving("option-30", 30, 15000))))
        assertEquals(1, ready(r).menuItems.size)
        assertEquals(2, ready(r).menuItems.single().options.size)
        rejects { r.saveMenuItem(MockBarMenuItem("menu-2", "fixture-bar", "product-12",
            listOf(serving("option-50", 50, 19000)))) }
        rejects { r.saveMenuItem(MockBarMenuItem("menu-3", "fixture-bar", "product-16",
            listOf(serving("a", 30, 19000), serving("b", 30, 19000)))) }
        r.saveMenuItem(MockBarMenuItem("menu-4", "fixture-bar", "product-16",
            listOf(serving("16-a", 30, 21000))))
        assertEquals(2, ready(r).menuItems.size)
        assertEquals(2, ready(r).menuItems.map { it.productId }.distinct().size)
    }

    @Test fun previewShowsSameStoreStateAndHidesSoldOutWithoutDeletingIt() {
        val r = repo()
        catalog(r)
        val option = serving("option-a", 30, 20000).copy(
            discount = MockDiscount(discountedPriceKrw = 15000, startAtEpochMs = 100, endAtEpochMs = 300))
        r.saveMenuItem(MockBarMenuItem("menu-1", "fixture-bar", "product-12", listOf(option)))
        assertEquals(15000, r.preview("fixture-bar", 200)!!.displayedPrice(option))
        assertEquals(20000, r.preview("fixture-bar", 300)!!.displayedPrice(option))
        assertEquals(1, r.preview("fixture-bar", 200)!!.visibleMenu.size)
        r.setSoldOut("menu-1", true)
        assertTrue(r.preview("fixture-bar", 200)!!.visibleMenu.isEmpty())
        assertEquals(1, ready(r).menuItems.size) // owner still sees sold-out row
        r.setSoldOut("menu-1", false)
        assertEquals(1, r.preview("fixture-bar", 200)!!.visibleMenu.size)
    }

    @Test fun photoSpecificExtractionReviewAndAddOnlyPublishAreConsistent() {
        val store = InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())
        val r = repo(store)
        catalog(r)
        r.saveMenuItem(MockBarMenuItem("existing", "fixture-bar", "product-12",
            listOf(serving("old", 30, 12000))))
        val fixture = OwnerMockFixtures.imageFixtures(mapOf(
            "content://test/photo-a" to listOf(MockExtractedLine(
                extractedItemId = "ignored-by-repo", sourceText = "Bottle 12 30ml 24000",
                kind = MockLineKind.PRODUCT, suggestedProductId = "product-12",
                candidateProductIds = listOf("product-12"),
                options = listOf(serving("original-a", 30, 24000)))),
            "content://test/photo-b" to listOf(MockExtractedLine(
                extractedItemId = "ignored-by-repo", sourceText = "Bottle 16 15ml 16000",
                kind = MockLineKind.PRODUCT, candidateProductIds = listOf("product-16"),
                options = listOf(serving("original-b", 15, 16000)))),
        ))
        val id = r.startPhotoImport("fixture-bar", listOf("content://test/photo-a", "content://test/photo-b"), fixture)
        val job = ready(r).imports.single()
        assertEquals(2, job.images.size)
        assertEquals(1, job.images[0].lines.size)
        assertEquals(1, job.images[1].lines.size)
        assertFalse(job.images[0].lines.single().extractedItemId == job.images[1].lines.single().extractedItemId)
        rejects { r.publishAddOnly(id, job.reviewVersion) }
        rejects { r.decideLine(id, job.images[0].lines.single().extractedItemId, 2,
            MockReviewDecision(MockDecisionKind.SELECT_PRODUCT, "product-12")) }
        job.images.forEachIndexed { index, image ->
            r.decideLine(id, image.lines.single().extractedItemId, job.reviewVersion,
                MockReviewDecision(MockDecisionKind.SELECT_PRODUCT,
                    if (index == 0) "product-12" else "product-16"))
        }
        val second = repo(store)
        assertEquals(2, ready(second).imports.single().images.flatMap { it.lines }.count { it.decision != null })
        assertEquals(1, second.publishAddOnly(id, job.reviewVersion))
        val updated = ready(second)
        assertEquals(2, updated.menuItems.size)
        assertEquals(12000, updated.menuItems.first { it.productId == "product-12" }.options.single().priceKrw)
        assertEquals(16000, updated.menuItems.first { it.productId == "product-16" }.options.single().priceKrw)
        assertEquals(2, second.preview("fixture-bar", 250)!!.visibleMenu.size)
        rejects { second.publishAddOnly(id, job.reviewVersion) }
    }

    @Test fun unrecognisedPhotoHasNoInventedLinesAndEmptyPublishIsValid() {
        val r = repo()
        val id = r.startPhotoImport("fixture-bar", listOf("content://test/random"),
            OwnerMockFixtures.imageFixtures(emptyMap()))
        val job = ready(r).imports.single()
        assertTrue(job.images.single().lines.isEmpty())
        assertEquals(0, r.publishAddOnly(id, job.reviewVersion))
        assertTrue(r.preview("fixture-bar", 0)!!.visibleMenu.isEmpty())
    }

    @Test fun conflictingTwoPhotoPricesForOneOptionAreRejectedAtomically() {
        val r = repo()
        catalog(r)
        val source = OwnerMockFixtures.imageFixtures(mapOf(
            "content://a" to listOf(MockExtractedLine("a", "first", MockLineKind.PRODUCT,
                options = listOf(serving("a", 30, 10000)))),
            "content://b" to listOf(MockExtractedLine("b", "second", MockLineKind.PRODUCT,
                options = listOf(serving("b", 30, 12000)))),
        ))
        val id = r.startPhotoImport("fixture-bar", listOf("content://a", "content://b"), source)
        val job = ready(r).imports.single()
        job.images.flatMap { it.lines }.forEach { line ->
            r.decideLine(id, line.extractedItemId, 1,
                MockReviewDecision(MockDecisionKind.SELECT_PRODUCT, "product-12"))
        }
        rejects { r.publishAddOnly(id, 1) }
        assertTrue(ready(r).menuItems.isEmpty())
        assertEquals(MockImportStatus.READY_FOR_REVIEW, ready(r).imports.single().status)
    }

    @Test fun unfinishedRegistrationDraftSurvivesRestartAndSubmittedClaimIsSeparate() {
        val store = InMemoryMockOwnerStateStore()
        val first = repo(store)
        val draft = MockRegistrationDraft(
            proposedBarName = "Mock Demo Bar",
            representativeName = "Test Only",
            applicantGallery = listOf(MockPhoto("cover", "content://mock/cover", MockPhotoKind.REGISTRATION_ATTACHMENT)),
            initialMenuPhotos = listOf(MockPhoto("menu-pic", "content://mock/menu", MockPhotoKind.MENU_CAPTURE)),
        )
        first.saveRegistrationDraft(draft)
        val restored = repo(store)
        assertEquals(draft, ready(restored).registrationDraft)
        val applicationId = restored.submitRegistrationDraftForFixture()
        val snap = ready(restored)
        assertTrue(applicationId.startsWith("local-application-"))
        assertEquals(null, snap.registrationDraft)
        assertEquals(MockApplicationStatus.PENDING, snap.applications.single().status)
        assertEquals(2, snap.applications.single().registrationPhotos.size)
        assertTrue(snap.bars.isEmpty()) // approval is not simulated automatically
    }

    @Test fun cancelAndRejectApplicationStaySeparateFromApproval() {
        val r = repo(InMemoryMockOwnerStateStore())
        r.registerApplication(MockOwnerApplication("a", MockApplicationKind.NEW_BAR,
            MockApplicationStatus.PENDING, "A"))
        r.closeApplicationForFixture("a", MockApplicationStatus.REJECTED)
        assertEquals(MockApplicationStatus.REJECTED, ready(r).applications.single().status)
        rejects { r.closeApplicationForFixture("a", MockApplicationStatus.CANCELED) }
        assertTrue(ready(r).bars.isEmpty())
    }

    @Test fun deleteAndClearMenuAreVisibleImmediatelyInCustomerPreview() {
        val r = repo()
        catalog(r)
        r.saveMenuItem(MockBarMenuItem("one", "fixture-bar", "product-12",
            listOf(serving("one-option", 15, 7000))))
        r.saveMenuItem(MockBarMenuItem("two", "fixture-bar", "product-16",
            listOf(serving("two-option", 30, 16000))))
        r.deleteMenuItem("one")
        assertEquals(1, r.preview("fixture-bar", 0)!!.visibleMenu.size)
        r.clearMenuForBar("fixture-bar")
        assertTrue(ready(r).menuItems.isEmpty())
        assertTrue(r.preview("fixture-bar", 0)!!.visibleMenu.isEmpty())
    }

    @Test fun existingBarApplicationUsesExistingBarId() {
        val r = repo()
        r.registerApplication(MockOwnerApplication("claim", MockApplicationKind.EXISTING_BAR,
            MockApplicationStatus.PENDING, "테스트 매장", barId = "fixture-bar"))
        r.approveForFixture("claim", MockBar("fixture-bar", "테스트 매장", "테스트 주소"))
        assertEquals(1, ready(r).bars.size)
        assertEquals(MockApplicationStatus.APPROVED, ready(r).applications.single().status)
    }


    @Test fun invalidDiscountCannotBeStoredViaCorrectedReviewOptions() {
        val r = repo()
        catalog(r)
        val source = OwnerMockFixtures.imageFixtures(mapOf(
            "content://discount" to listOf(MockExtractedLine(
                "extracted", "Whisky 12 30ml", MockLineKind.PRODUCT,
                options = listOf(serving("original", 30, 10000))
            ))
        ))
        val id = r.startPhotoImport("fixture-bar", listOf("content://discount"), source)
        val lineId = ready(r).imports.single().images.single().lines.single().extractedItemId
        for (discount in listOf(
            MockDiscount(20000, 100, 300), // discount above list price
            MockDiscount(8000, 300, 100),  // reversed interval
            MockDiscount(8000, 100, 100),  // zero-length interval
        )) {
            rejects {
                r.decideLine(id, lineId, 1, MockReviewDecision(
                    MockDecisionKind.SELECT_PRODUCT, "product-12",
                    listOf(serving("corrected", 30, 10000).copy(discount = discount))
                ))
            }
        }
        assertEquals(null, ready(r).imports.single().images.single().lines.single().decision)
        assertTrue(ready(r).menuItems.isEmpty())

        val valid = serving("corrected", 30, 10000).copy(
            discount = MockDiscount(8000, 100, 300)
        )
        r.decideLine(id, lineId, 1, MockReviewDecision(
            MockDecisionKind.SELECT_PRODUCT, "product-12", listOf(valid)
        ))
        assertEquals(1, r.publishAddOnly(id, 1))
        val published = ready(r).menuItems.single().options.single()
        assertEquals(8000, r.preview("fixture-bar", 200)!!.displayedPrice(published))
        assertEquals(10000, r.preview("fixture-bar", 300)!!.displayedPrice(published))
    }

    @Test fun invalidExtractedOptionCannotBypassPublishValidation() {
        val r = repo()
        catalog(r)
        val source = OwnerMockFixtures.imageFixtures(mapOf(
            "content://bad-option" to listOf(MockExtractedLine(
                "extracted", "Whisky 12", MockLineKind.PRODUCT,
                options = listOf(serving("original", 30, 10000).copy(
                    discount = MockDiscount(20000, 100, 300)
                ))
            ))
        ))
        val id = r.startPhotoImport("fixture-bar", listOf("content://bad-option"), source)
        val lineId = ready(r).imports.single().images.single().lines.single().extractedItemId
        r.decideLine(id, lineId, 1, MockReviewDecision(MockDecisionKind.SELECT_PRODUCT, "product-12"))
        rejects { r.publishAddOnly(id, 1) }
        assertEquals(MockImportStatus.READY_FOR_REVIEW, ready(r).imports.single().status)
        assertTrue(ready(r).menuItems.isEmpty())
    }

    @Test fun failedWriteDoesNotExposeUnpersistedMutation() {
        val store = object : MockOwnerStateStore {
            override fun read() = OwnerMockFixtures.registeredBar()
            override fun write(snapshot: MockOwnerSnapshot) { error("mock disk full") }
        }
        val r = repo(store)
        rejects { r.selectBar("fixture-bar") }
        assertEquals("fixture-bar", ready(r).selectedBarId)
    }
}
