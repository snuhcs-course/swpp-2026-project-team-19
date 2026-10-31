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
        assertTrue(ready(second).hasPublishedInitialReview("fixture-bar"))
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
            proposedBarAddress = "테스트 주소",
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


    @Test fun registrationDraftPreservesNormalizedBusinessNumberAcrossSubmissionAndRestart() {
        val store = InMemoryMockOwnerStateStore()
        val r = repo(store)
        r.saveRegistrationDraft(MockRegistrationDraft(
            proposedBarName = "Mock Bar", proposedBarAddress = "Sample Road 12", businessNumberDigits = " 123-45-67890 "
        ))
        val id = r.submitRegistrationDraftForFixture()
        assertEquals("local-application-1", id)
        val restored = repo(store)
        assertEquals("1234567890", ready(restored).applications.single().businessNumberDigits)
        assertEquals(null, ready(restored).registrationDraft)
    }

    @Test fun generatedApplicationIdDoesNotCollideWithPreviouslyRegisteredFixtures() {
        val store = InMemoryMockOwnerStateStore()
        val r = repo(store)
        r.registerApplication(MockOwnerApplication("local-application-1",
            MockApplicationKind.NEW_BAR, MockApplicationStatus.PENDING, "Old application 1"))
        r.registerApplication(MockOwnerApplication("local-application-2",
            MockApplicationKind.NEW_BAR, MockApplicationStatus.PENDING, "Old application 2"))
        r.saveRegistrationDraft(MockRegistrationDraft(proposedBarName = "New application", proposedBarAddress = "Sample Road 21"))
        val id = r.submitRegistrationDraftForFixture()
        assertEquals("local-application-3", id)
        assertEquals(3, ready(r).applications.map { it.applicationId }.distinct().size)
        assertEquals(4L, ready(r).nextLocalId)
        r.closeApplicationForFixture(id, MockApplicationStatus.CANCELED)
        val restored = ready(repo(store))
        assertEquals(MockApplicationStatus.PENDING,
            restored.applications.first { it.applicationId == "local-application-1" }.status)
        assertEquals(MockApplicationStatus.PENDING,
            restored.applications.first { it.applicationId == "local-application-2" }.status)
        assertEquals(MockApplicationStatus.CANCELED,
            restored.applications.first { it.applicationId == id }.status)
    }

    @Test fun invalidCustomOperatingExceptionHoursAreRejectedAndValidHoursPersist() {
        val r = repo()
        val bar = ready(r).bars.single()
        val base = MockOperatingException(
            "temporary", MockExceptionKind.CUSTOM_HOURS, 100L, 100L,
            openMinutes = 1080, closeMinutes = 1380,
        )
        for (invalid in listOf(
            base.copy(openMinutes = null),
            base.copy(closeMinutes = null),
            base.copy(openMinutes = -1),
            base.copy(closeMinutes = 1500),
            base.copy(fromEpochDay = 101),
        )) {
            rejects { r.saveBar(bar.copy(exceptions = listOf(invalid))) }
        }
        assertTrue(ready(r).bars.single().exceptions.isEmpty())
        r.saveBar(bar.copy(exceptions = listOf(
            base, MockOperatingException("vacation", MockExceptionKind.VACATION, 110L, 114L)
        )))
        val stored = ready(r).bars.single().exceptions
        assertEquals(2, stored.size)
        assertEquals(1080, stored.first().openMinutes)
    }

    @Test fun directMenuEntryRejectsBlankOptionId() {
        val r = repo()
        catalog(r)
        rejects {
            r.saveMenuItem(MockBarMenuItem("menu-blank", "fixture-bar", "product-12",
                listOf(serving("", 30, 12000))))
        }
        assertTrue(ready(r).menuItems.isEmpty())
        r.saveMenuItem(MockBarMenuItem("menu-good", "fixture-bar", "product-12",
            listOf(serving("option-30", 30, 12000))))
        assertEquals("option-30", ready(r).menuItems.single().options.single().optionId)
    }

    @Test fun identicalServingListPriceWithConflictingDiscountsRequiresReview() {
        val r = repo()
        catalog(r)
        val fixture = OwnerMockFixtures.imageFixtures(mapOf(
            "content://photoA" to listOf(MockExtractedLine(
                "a", "Bottle 12 30ml", MockLineKind.PRODUCT,
                options = listOf(serving("a", 30, 10000).copy(
                    discount = MockDiscount(8000, 100, 200))))),
            "content://photoB" to listOf(MockExtractedLine(
                "b", "Bottle 12 30ml", MockLineKind.PRODUCT,
                options = listOf(serving("b", 30, 10000).copy(
                    discount = MockDiscount(7000, 100, 200))))),
        ))
        val id = r.startPhotoImport("fixture-bar", listOf("content://photoA", "content://photoB"), fixture)
        ready(r).imports.single().images.flatMap { it.lines }.forEach { line ->
            r.decideLine(id, line.extractedItemId, 1,
                MockReviewDecision(MockDecisionKind.SELECT_PRODUCT, "product-12"))
        }
        rejects { r.publishAddOnly(id, 1) }
        assertTrue(ready(r).menuItems.isEmpty())
        assertEquals(MockImportStatus.READY_FOR_REVIEW, ready(r).imports.single().status)
    }

    @Test fun identicalServingPriceAndDiscountAcrossPhotosDeduplicatesDeterministically() {
        val r = repo()
        catalog(r)
        val identicalDiscount = MockDiscount(8000, 100, 200)
        val fixture = OwnerMockFixtures.imageFixtures(mapOf(
            "content://photoA" to listOf(MockExtractedLine("a", "Whisky 12", MockLineKind.PRODUCT,
                options = listOf(serving("a", 30, 10000).copy(discount = identicalDiscount)))),
            "content://photoB" to listOf(MockExtractedLine("b", "Whisky 12", MockLineKind.PRODUCT,
                options = listOf(serving("b", 30, 10000).copy(discount = identicalDiscount)))),
        ))
        val id = r.startPhotoImport("fixture-bar", listOf("content://photoA", "content://photoB"), fixture)
        ready(r).imports.single().images.flatMap { it.lines }.forEach { line ->
            r.decideLine(id, line.extractedItemId, 1,
                MockReviewDecision(MockDecisionKind.SELECT_PRODUCT, "product-12"))
        }
        assertEquals(1, r.publishAddOnly(id, 1))
        assertEquals(1, ready(r).menuItems.single().options.size)
        assertEquals(8000, r.preview("fixture-bar", 150)!!.displayedPrice(
            ready(r).menuItems.single().options.single()
        ))
    }


    @Test fun newBarAddressSurvivesDraftAndSubmissionRestoration() {
        val store = InMemoryMockOwnerStateStore()
        val r = repo(store)
        val draft = MockRegistrationDraft(
            kind = MockApplicationKind.NEW_BAR,
            proposedBarName = "New Mock Bar",
            proposedBarAddress = "  Sample Road 33  ",
        )
        r.saveRegistrationDraft(draft)
        assertEquals(draft, ready(repo(store)).registrationDraft)
        r.submitRegistrationDraftForFixture()
        val submitted = ready(repo(store)).applications.single()
        assertEquals("Sample Road 33", submitted.proposedBarAddress)
        assertEquals("New Mock Bar", submitted.proposedBarName)
        assertEquals(null, submitted.barId)
    }

    @Test fun existingBarClaimDoesNotRequireNewProposedBarName() {
        val store = InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())
        val r = repo(store)
        r.saveRegistrationDraft(MockRegistrationDraft(
            kind = MockApplicationKind.EXISTING_BAR,
            existingBarId = "fixture-bar",
            proposedBarName = "",
        ))
        val id = r.submitRegistrationDraftForFixture()
        val application = ready(repo(store)).applications.single()
        assertEquals(id, application.applicationId)
        assertEquals("fixture-bar", application.barId)
        assertEquals("테스트 매장", application.proposedBarName)
        assertEquals(null, application.proposedBarAddress)
        assertEquals(1, ready(r).bars.size)
        r.approveForFixture(id, ready(r).bars.single())
        assertEquals(1, ready(r).bars.size)
    }

    @Test fun newBarRequiresNameAndExistingClaimRequiresValidBar() {
        val r = repo()
        r.saveRegistrationDraft(MockRegistrationDraft(
            kind = MockApplicationKind.NEW_BAR,
            proposedBarName = " "
        ))
        rejects { r.submitRegistrationDraftForFixture() }
        r.saveRegistrationDraft(MockRegistrationDraft(
            kind = MockApplicationKind.NEW_BAR,
            proposedBarName = "New Bar Without Address",
        ))
        rejects { r.submitRegistrationDraftForFixture() }
        r.saveRegistrationDraft(MockRegistrationDraft(
            kind = MockApplicationKind.EXISTING_BAR,
            existingBarId = "missing-bar"
        ))
        rejects { r.submitRegistrationDraftForFixture() }
        assertTrue(ready(r).applications.isEmpty())
    }

    @Test fun photoPublishSkipsManualMenuAndServingOptionIds() {
        val r = repo()
        catalog(r)
        val fixture = OwnerMockFixtures.imageFixtures(mapOf(
            "content://image-for-16" to listOf(MockExtractedLine(
                "line", "Bottle 16", MockLineKind.PRODUCT,
                options = listOf(serving("from-photo", 30, 17000))
            ))
        ))
        val id = r.startPhotoImport(
            "fixture-bar", listOf("content://image-for-16"), fixture
        )
        val nextId = ready(r).nextLocalId
        // Exactly the IDs that naive publish would generate from the nextLocalId
        // and its immediate successor are occupied by a manually added product.
        val manualMenuId = "local-menu-$nextId"
        val manualOptionId = "local-serving-${nextId + 2}"
        r.saveMenuItem(MockBarMenuItem(
            manualMenuId, "fixture-bar", "product-12",
            listOf(serving(manualOptionId, 30, 12000))
        ))
        val lineId = ready(r).imports.single().images.single().lines.single().extractedItemId
        r.decideLine(id, lineId, 1,
            MockReviewDecision(MockDecisionKind.SELECT_PRODUCT, "product-16"))
        assertEquals(1, r.publishAddOnly(id, 1))
        val items = ready(r).menuItems
        assertEquals(2, items.size)
        assertEquals(2, items.map { it.barMenuItemId }.distinct().size)
        assertEquals(2, items.flatMap { it.options }.map { it.optionId }.distinct().size)
        val addedMenu = items.single { it.productId == "product-16" }
        assertTrue(addedMenu.barMenuItemId != manualMenuId)
        assertTrue(addedMenu.options.single().optionId != manualOptionId)
        r.setSoldOut(addedMenu.barMenuItemId, true)
        assertEquals(false, ready(r).menuItems.single { it.productId == "product-12" }.soldOut)
        assertEquals(true, ready(r).menuItems.single { it.productId == "product-16" }.soldOut)
        r.deleteMenuItem(addedMenu.barMenuItemId)
        assertEquals(manualMenuId, ready(r).menuItems.single().barMenuItemId)
    }


    @Test fun preseededImportIdCannotBeReusedByAnotherBar() {
        val preexisting = MockMenuImport(
            menuImportId = "local-import-1",
            barId = "fixture-bar",
            status = MockImportStatus.APPLIED,
            reviewVersion = 1,
            images = emptyList(),
        )
        val snapshot = OwnerMockFixtures.registeredBar().copy(
            bars = OwnerMockFixtures.registeredBar().bars +
                MockBar("second-bar", "Second Test Bar", "Second test address"),
            imports = listOf(preexisting),
            nextLocalId = 1L,
        )
        val store = InMemoryMockOwnerStateStore(snapshot)
        val r = repo(store)
        val fixture = OwnerMockFixtures.imageFixtures(mapOf(
            "content://second-bar/photo" to listOf(MockExtractedLine(
                "sample", "Bottle 12", MockLineKind.PRODUCT,
                options = listOf(serving("unassigned", 30, 12000))
            ))
        ))
        val newId = r.startPhotoImport("second-bar", listOf("content://second-bar/photo"), fixture)
        assertEquals("local-import-2", newId)
        assertEquals(2, ready(r).imports.map { it.menuImportId }.distinct().size)
        assertEquals("fixture-bar", ready(r).imports.first().barId)
        val restored = repo(store)
        val job = ready(restored).imports.single { it.menuImportId == newId }
        assertEquals("second-bar", job.barId)
        assertEquals(MockImportStatus.READY_FOR_REVIEW, job.status)
        assertEquals(1, job.images.single().lines.size)
        assertTrue(ready(restored).nextLocalId > 2)
    }

    @Test fun savingBarRejectsBlankAndTooLongAddressesWithoutChangingPreview() {
        val r = repo()
        val original = ready(r).bars.single()
        for (bad in listOf("", "  ", "x".repeat(501))) {
            rejects { r.saveBar(original.copy(address = bad)) }
        }
        assertEquals(original.address, r.preview(original.barId, 0)!!.bar.address)
        r.saveBar(original.copy(address = "x".repeat(500)))
        assertEquals(500, r.preview(original.barId, 0)!!.bar.address.length)
    }

    @Test fun savingBarPersistsExactlyTheTrimmedAddressThatPassedValidation() {
        val store = InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())
        val repository = repo(store)
        val original = ready(repository).bars.single()
        // A 500-character address padded with spaces must be stored as 500 characters.
        val padded = "  " + "x".repeat(500) + "  "
        repository.saveBar(original.copy(address = padded))
        val persisted = ready(repo(store)).bars.single().address
        assertEquals("x".repeat(500), persisted)
        assertEquals(500, persisted.length)
        assertEquals(persisted, repository.preview(original.barId, 0)!!.bar.address)

        repository.saveBar(original.copy(address = "  Sample Road 12   "))
        assertEquals("Sample Road 12", ready(repo(store)).bars.single().address)
        assertEquals("Sample Road 12", repository.preview(original.barId, 0)!!.bar.address)

        rejects { repository.saveBar(original.copy(address = "  " + "x".repeat(501) + "  ")) }
        assertEquals("Sample Road 12", ready(repo(store)).bars.single().address)
    }

    @Test fun mockOptionsRejectServingVolumeAboveCurrentReviewContractLimit() {
        val r = repo()
        catalog(r)
        for (volume in listOf(-1, 0, 32768, 50000)) {
            rejects {
                r.saveMenuItem(MockBarMenuItem(
                    "menu-invalid", "fixture-bar", "product-12",
                    listOf(serving("option-invalid", volume, 10000))
                ))
            }
        }
        val source = OwnerMockFixtures.imageFixtures(mapOf(
            "content://test/volume" to listOf(MockExtractedLine(
                "source", "Bottle 12 30ml", MockLineKind.PRODUCT,
                options = listOf(serving("source", 30, 10000))
            ))
        ))
        val id = r.startPhotoImport("fixture-bar", listOf("content://test/volume"), source)
        val line = ready(r).imports.single().images.single().lines.single().extractedItemId
        rejects {
            r.decideLine(id, line, 1, MockReviewDecision(
                MockDecisionKind.SELECT_PRODUCT, "product-12",
                correctedOptions = listOf(serving("corrected", 50000, 10000))
            ))
        }
        assertEquals(null, ready(r).imports.single().images.single().lines.single().decision)
        r.decideLine(id, line, 1, MockReviewDecision(
            MockDecisionKind.SELECT_PRODUCT, "product-12",
            correctedOptions = listOf(serving("corrected", 32767, 10000))
        ))
        assertEquals(1, r.publishAddOnly(id, 1))
        assertEquals(32767, ready(r).menuItems.single().options.single().pourMl)
    }

    @Test fun uncorrectedInvalidExtractedVolumeCannotBePublished() {
        val r = repo()
        catalog(r)
        val source = OwnerMockFixtures.imageFixtures(mapOf(
            "content://test/invalid-raw-volume" to listOf(MockExtractedLine(
                "raw", "Bottle 12 50000ml", MockLineKind.PRODUCT,
                options = listOf(serving("raw", 50000, 10000))
            ))
        ))
        val id = r.startPhotoImport(
            "fixture-bar", listOf("content://test/invalid-raw-volume"), source
        )
        val line = ready(r).imports.single().images.single().lines.single().extractedItemId
        r.decideLine(id, line, 1, MockReviewDecision(MockDecisionKind.SELECT_PRODUCT, "product-12"))
        rejects { r.publishAddOnly(id, 1) }
        assertTrue(ready(r).menuItems.isEmpty())
        assertEquals(MockImportStatus.READY_FOR_REVIEW, ready(r).imports.single().status)
    }


    @Test fun emptyAppOnboardingRetainsPhonesAndPhotoOrderAcrossRepositoryRecreation() {
        val store = InMemoryMockOwnerStateStore()
        val first = repo(store)
        assertTrue(first.state.value is MockOwnerLoadState.Empty)
        val certificate = MockPhoto("certificate", "content://test/certificate", MockPhotoKind.REGISTRATION_ATTACHMENT)
        val cover = MockPhoto("cover", "content://test/cover", MockPhotoKind.BAR_GALLERY)
        val menu1 = MockPhoto("menu-1", "content://test/menu1", MockPhotoKind.MENU_CAPTURE)
        val menu2 = MockPhoto("menu-2", "content://test/menu2", MockPhotoKind.MENU_CAPTURE)
        val draft = MockRegistrationDraft(
            proposedBarName = "등록 테스트", proposedBarAddress = "서울시 테스트",
            businessNumberDigits = "1234567890", representativeName = "테스트 대표",
            openingDateIso = "2024-01-01", certificatePhoto = certificate,
            storePhone = "050712345678", contactPhone = "0212345678",
            applicantGallery = listOf(cover), initialMenuPhotos = listOf(menu1, menu2),
        )
        first.saveRegistrationDraft(draft)
        val restored = repo(store)
        assertEquals(draft, ready(restored).registrationDraft)
        val id = restored.submitRegistrationDraftForFixture()
        val application = ready(repo(store)).applications.single()
        assertEquals(id, application.applicationId)
        assertEquals(MockApplicationStatus.PENDING, application.status)
        assertEquals("050712345678", application.storePhone)
        assertEquals("0212345678", application.contactPhone)
        assertEquals(listOf(certificate, cover, menu1, menu2), application.registrationPhotos)
        assertTrue(ready(restored).bars.isEmpty())
        assertTrue(ready(restored).menuItems.isEmpty())
        assertEquals(null, restored.preview("mock-bar", 0))
        rejects { restored.submitRegistrationDraftForFixture() } // cannot submit the same draft twice
    }

    @Test fun approvalPreservesPhotosWithoutPublishingMenuUntilManualReview() {
        val store = InMemoryMockOwnerStateStore()
        val repository = repo(store)
        repository.saveRegistrationDraft(MockRegistrationDraft(
            proposedBarName = "Test Owner Bar", proposedBarAddress = "Test Road",
            initialMenuPhotos = listOf(
                MockPhoto("a", "content://test/menuA", MockPhotoKind.MENU_CAPTURE),
                MockPhoto("b", "content://test/menuB", MockPhotoKind.MENU_CAPTURE),
            )
        ))
        val appId = repository.submitRegistrationDraftForFixture()
        val application = ready(repository).applications.single()
        val bar = MockBar("bar-approved", application.proposedBarName, application.proposedBarAddress!!)
        repository.approveForFixture(appId, bar)
        val urls = application.registrationPhotos
            .filter { it.kind == MockPhotoKind.MENU_CAPTURE }.map { it.uri }
        val importId = repository.startPhotoImport(bar.barId, urls, OwnerMockFixtures.imageFixtures(emptyMap()))
        val restored = repo(store)
        val snapshot = ready(restored)
        assertEquals(MockApplicationStatus.APPROVED, snapshot.applications.single().status)
        assertEquals(bar.barId, snapshot.selectedBarId)
        assertEquals(listOf("content://test/menuA", "content://test/menuB"),
            snapshot.imports.single { it.menuImportId == importId }.images.map { it.sourceUri })
        assertEquals(MockImportStatus.READY_FOR_REVIEW, snapshot.imports.single().status)
        assertTrue(restored.preview(bar.barId, 0)!!.visibleMenu.isEmpty())
        assertTrue(snapshot.menuItems.isEmpty())
        assertFalse(snapshot.hasPublishedInitialReview(bar.barId))
    }

    @Test fun canceledAndRejectedMockApplicationsNeverCreatePublicBars() {
        for(status in listOf(MockApplicationStatus.CANCELED, MockApplicationStatus.REJECTED)) {
            val subject = repo(InMemoryMockOwnerStateStore())
            subject.saveRegistrationDraft(MockRegistrationDraft(
                proposedBarName = "Bar", proposedBarAddress = "Address"
            ))
            val id = subject.submitRegistrationDraftForFixture()
            subject.closeApplicationForFixture(id, status)
            assertEquals(status, ready(subject).applications.single().status)
            assertTrue(ready(subject).bars.isEmpty())
            assertTrue(ready(subject).menuItems.isEmpty())
        }
    }

    @Test fun previouslyRegisteredPublicCandidateIsNotOwnedUntilApproval() {
        val store = InMemoryMockOwnerStateStore()
        val repository = repo(store)
        repository.seedExistingCandidateForFixture(MockBar("public-bar", "Known Public Bar", "Public Street"))
        val before = ready(repository)
        assertTrue(before.bars.isEmpty())
        assertFalse(before.openSingleBarManager())
        repository.saveRegistrationDraft(MockRegistrationDraft(
            kind = MockApplicationKind.EXISTING_BAR, existingBarId = "public-bar",
            representativeName = "Test Owner", businessNumberDigits = "1234567890"
        ))
        val appId = repository.submitRegistrationDraftForFixture()
        val waiting = ready(repository)
        assertEquals("public-bar", waiting.applications.single().barId)
        assertTrue(waiting.bars.isEmpty())
        repository.approveForFixture(appId,waiting.existingBarCandidates.single())
        val approved = ready(repo(store))
        assertEquals(1, approved.bars.size)
        assertTrue(approved.existingBarCandidates.isEmpty())
        assertTrue(approved.openSingleBarManager())
        assertTrue(approved.menuItems.isEmpty())
    }

    @Test fun singleBarRoutingRequiresExactlyOneBarWithoutPendingOrActiveDraft() {
        val empty = MockOwnerSnapshot()
        assertFalse(empty.openSingleBarManager())
        val single = OwnerMockFixtures.registeredBar()
        assertTrue(single.openSingleBarManager())
        assertFalse(single.copy(bars = single.bars + MockBar("b2", "B", "Address B")).openSingleBarManager())
        assertFalse(single.copy(registrationDraft = MockRegistrationDraft()).openSingleBarManager())
        assertFalse(single.copy(applications = listOf(MockOwnerApplication(
            "pending-1", MockApplicationKind.EXISTING_BAR,
            MockApplicationStatus.PENDING, "Test", barId = "fixture-bar"
        ))).openSingleBarManager())
    }

    @Test fun registrationResumeCheckpointAndMenuOrderSurviveRepositoryRestart() {
        val store = InMemoryMockOwnerStateStore()
        val owner = repo(store)
        val draft = MockRegistrationDraft(
            proposedBarName = "Sample", storePhone = "0212345678",
            resumePageKey = "MENUS",
            initialMenuPhotos = listOf(
                MockPhoto("p1", "content://picker/a", MockPhotoKind.MENU_CAPTURE),
                MockPhoto("p2", "content://picker/b", MockPhotoKind.MENU_CAPTURE)
            )
        )
        owner.saveRegistrationDraft(draft)
        val reopened = ready(repo(store)).registrationDraft!!
        assertEquals("MENUS", reopened.resumePageKey)
        assertEquals(listOf("content://picker/a", "content://picker/b"),
            reopened.initialMenuPhotos.map { it.uri })
        // Picker appends/removes by copying the same persisted draft; no step reset.
        owner.saveRegistrationDraft(reopened.copy(initialMenuPhotos =
            reopened.initialMenuPhotos.drop(1)))
        val afterRemove = ready(repo(store)).registrationDraft!!
        assertEquals("MENUS", afterRemove.resumePageKey)
        assertEquals(listOf("content://picker/b"), afterRemove.initialMenuPhotos.map { it.uri })
    }

    @Test fun v4AddressDetailAndPhoneArePreservedOnSubmit() {
        val r = repo(InMemoryMockOwnerStateStore())
        r.saveRegistrationDraft(MockRegistrationDraft(
            proposedBarName = "V4 Test", proposedBarAddress = "서울 관악구 봉천로",
            proposedBarAddressDetail = "2층", businessNumberDigits = "1234567891",
            representativeName = "김민준", openingDateIso = "2019-05-14",
            storePhone = "025551234", contactPhone = "01012345678"
        ))
        val id = r.submitRegistrationDraftForFixture()
        val application = ready(r).applications.single { it.applicationId == id }
        assertEquals("서울 관악구 봉천로 2층", application.proposedBarAddress)
        assertEquals("025551234", application.storePhone)
        assertEquals("01012345678", application.contactPhone)
        assertEquals(MockApplicationStatus.PENDING, application.status)
        assertTrue(ready(r).menuItems.isEmpty())
    }

    @Test fun v4SubmissionRejectsCombinedAddressLongerThanApiLimit() {
        val r = repo(InMemoryMockOwnerStateStore())
        r.saveRegistrationDraft(MockRegistrationDraft(
            proposedBarName = "Long address",
            proposedBarAddress = "x".repeat(499),
            proposedBarAddressDetail = "2층"
        ))
        rejects { r.submitRegistrationDraftForFixture() }
        assertTrue(ready(r).applications.isEmpty())
        assertTrue(ready(r).registrationDraft != null)
        r.saveRegistrationDraft(ready(r).registrationDraft!!.copy(proposedBarAddressDetail = ""))
        assertTrue(r.submitRegistrationDraftForFixture().isNotBlank())
    }

    @Test fun v4DuplicatePendingSubmissionBlockedEvenWithFreshDraft() {
        val r = repo(InMemoryMockOwnerStateStore())
        val draft = MockRegistrationDraft(
            proposedBarName = "Duplicate Pending Bar", proposedBarAddress = "Mock Address",
            businessNumberDigits = "123-45-67891"
        )
        r.saveRegistrationDraft(draft)
        r.submitRegistrationDraftForFixture()
        r.saveRegistrationDraft(draft.copy(
            proposedBarName = "Same Business, Different Name",
            businessNumberDigits = "1234567891"
        ))
        rejects { r.submitRegistrationDraftForFixture() }
        assertEquals(1, ready(r).applications.count { it.status == MockApplicationStatus.PENDING })
    }

    @Test fun newBarApplicationsWithDifferentBusinessNumbersMayShareName() {
        val r = repo(InMemoryMockOwnerStateStore())
        val first = MockRegistrationDraft(
            proposedBarName = "Shared Name", proposedBarAddress = "First Address",
            businessNumberDigits = "1234567891"
        )
        r.saveRegistrationDraft(first)
        r.submitRegistrationDraftForFixture()
        r.saveRegistrationDraft(first.copy(
            proposedBarAddress = "Second Address", businessNumberDigits = "2345678910"
        ))
        r.submitRegistrationDraftForFixture()
        assertEquals(2, ready(r).applications.count { it.status == MockApplicationStatus.PENDING })
    }

    @Test fun ownedBarAndNewRegistrationDraftRemainInSnapshotTogether() {
        val store = InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())
        val r = repo(store)
        val pendingDraft = MockRegistrationDraft(
            proposedBarName = "New Bar", businessNumberDigits = "1234567891",
            resumePageKey = "MENUS"
        )
        r.saveRegistrationDraft(pendingDraft)
        val restored = ready(repo(store))
        assertEquals(1, restored.bars.size)
        assertEquals(pendingDraft, restored.registrationDraft)
    }

    @Test fun v4RejectedCardCanBeDismissedWithoutDeletingHistory() {
        val store = InMemoryMockOwnerStateStore()
        val r = repo(store)
        r.saveRegistrationDraft(MockRegistrationDraft(
            proposedBarName = "Rejected Bar", proposedBarAddress = "Mock Address"
        ))
        val id = r.submitRegistrationDraftForFixture()
        r.closeApplicationForFixture(id, MockApplicationStatus.REJECTED)
        assertTrue(ready(r).applications.single().rejectionReason!!.isNotBlank())
        r.dismissRejectedForFixture(id)
        val restored = ready(repo(store))
        assertTrue(id in restored.dismissedApplicationIds)
        assertEquals(MockApplicationStatus.REJECTED, restored.applications.single().status)
        rejects { r.dismissRejectedForFixture("unknown") }
    }

    @Test fun v4VisibleRejectedApplicationPreventsSingleBarDirectRedirect() {
        val bar = OwnerMockFixtures.registeredBar()
        val rejected = MockOwnerApplication(
            "rejected-v4", MockApplicationKind.NEW_BAR, MockApplicationStatus.REJECTED,
            "Rejected applicant"
        )
        val both = bar.copy(applications = listOf(rejected))
        assertFalse(both.openSingleBarManager())
        assertTrue(both.copy(dismissedApplicationIds = setOf("rejected-v4")).openSingleBarManager())
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
