package com.zerotoone.bottlemap.data.owner

import org.junit.Assert.*
import org.junit.Test

class OwnerPhotoStage7Test {
    private fun repo(store: MockOwnerStateStore =
        InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())) =
        LocalOwnerMockRepository(store)

    private fun snap(r: OwnerMockRepository): MockOwnerSnapshot =
        (r.state.value as MockOwnerLoadState.Ready).snapshot

    private fun photo(id: String) =
        MockPhoto(id, "file:///private/mock/$id.jpg", MockPhotoKind.MENU_CAPTURE)

    private fun rejects(block: () -> Unit) {
        try { block(); fail("Expected operation to be rejected") }
        catch (_: IllegalArgumentException) {}
        catch (_: IllegalStateException) {}
    }

    @Test fun queuePersistsImageIdentityAndOrderWithoutTouchingPublishedRows() {
        val store = InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())
        val r = repo(store)
        val existing = MockBarMenuItem("existing", "fixture-bar", "existing-product",
            listOf(MockMenuOption("existing-price", pourMl = 30, priceKrw = 12000)))
        r.saveBrand(MockBrand("existing-brand", "기존 브랜드"))
        r.saveCatalogProduct(MockCatalogProduct("existing-product", "existing-brand", "기존 상품"))
        r.saveMenuItem(existing)
        val photos = listOf(photo("photo-A"), photo("photo-B"))
        val id = r.queuePhotoImport("fixture-bar", photos)
        val job = snap(repo(store)).imports.single()
        assertEquals(id, job.menuImportId)
        assertEquals(MockImportStatus.PROCESSING, job.status)
        assertEquals(listOf("photo-A", "photo-B"), job.images.map { it.imageId })
        assertEquals(listOf(1, 2), job.images.map { it.imageOrder })
        assertEquals(photos.map { it.uri }, job.images.map { it.sourceUri })
        assertEquals(existing, snap(r).menuItems.single())
    }

    @Test fun photoSpecificFixturesStaySeparateAndOverEightDigitPricesRequireManualEntry() {
        val r = repo()
        val id = r.queuePhotoImport("fixture-bar", listOf(photo("A"), photo("B")))
        val lines = mapOf(
            photo("A").uri to listOf(MockExtractedLine("fixture-A", "A 사케",
                MockLineKind.PRODUCT, options = listOf(
                    MockMenuOption("price-A", priceKrw = 12500)))),
            photo("B").uri to listOf(MockExtractedLine("fixture-B", "B 맥주",
                MockLineKind.PRODUCT, options = listOf(
                    MockMenuOption("price-B1", priceKrw = 100_000_000),
                    MockMenuOption("price-B2", priceKrw = Int.MAX_VALUE),
                    MockMenuOption("price-B3", priceKrw = 99_999_999)))),
        )
        assertEquals(MockImportStatus.READY_FOR_REVIEW,
            r.finishPhotoImport(id, MockPhotoExtractionSource { lines[it].orEmpty() }))
        val job = snap(r).imports.single()
        assertEquals(listOf("A 사케", "B 맥주"),
            job.images.map { it.lines.single().sourceText })
        assertEquals(listOf(false, true),
            job.images.map { it.lines.single().needsPriceEntry })
        assertEquals(listOf(0, 0, 99_999_999),
            job.images[1].lines.single().options.map { it.priceKrw })
        assertEquals(listOf("A", "B"), job.images.map { it.imageId })
        assertEquals(emptyList<MockBarMenuItem>(), snap(r).menuItems)
    }

    @Test fun missingFixtureFailsTruthfullyAndRetryUsesNewImportId() {
        val r = repo()
        val oldId = r.queuePhotoImport("fixture-bar", listOf(photo("A")))
        assertEquals(MockImportStatus.FAILED,
            r.finishPhotoImport(oldId, MockPhotoExtractionSource { emptyList() }))
        assertTrue(snap(r).imports.first().failureReason!!.contains("Mock 추출 결과"))
        rejects { r.cancelPhotoImport(oldId) }
        val newId = r.retryFailedPhotoImport(oldId)
        assertTrue(newId != oldId)
        assertEquals(MockImportStatus.PROCESSING, snap(r).imports.last().status)
        assertEquals(snap(r).imports.first().images.map { it.imageId },
            snap(r).imports.last().images.map { it.imageId })
        rejects { r.queuePhotoImport("fixture-bar", listOf(photo("C"))) }
        assertEquals(emptyList<MockBarMenuItem>(), snap(r).menuItems)
    }

    @Test fun activeJobsBlockDirectMenuWritesAndCancelIsIdempotent() {
        val r = repo()
        r.saveBrand(MockBrand("brand-1", "브랜드"))
        r.saveCatalogProduct(MockCatalogProduct("product-1", "brand-1", "맥주"))
        val row = MockBarMenuItem("row", "fixture-bar", "product-1",
            listOf(MockMenuOption("opt", priceKrw = 9000)))
        r.saveMenuItem(row)
        val importId = r.queuePhotoImport("fixture-bar", listOf(photo("A")))
        rejects { r.saveManualMenuItem(row.copy(displayNameOverride = "변경")) }
        rejects { r.setSoldOut("row", true) }
        rejects { r.deleteMenuItem("row") }
        rejects { r.clearMenuForBar("fixture-bar") }
        r.cancelPhotoImport(importId)
        r.cancelPhotoImport(importId)
        assertEquals(MockImportStatus.CANCELED, snap(r).imports.single().status)
        assertEquals(row, snap(r).menuItems.single())
        rejects { r.finishPhotoImport(importId, MockPhotoExtractionSource { emptyList() }) }
        r.setSoldOut("row", true)
        assertTrue(snap(r).menuItems.single().soldOut)
        r.queuePhotoImport("fixture-bar", listOf(photo("B")))
    }

    @Test fun readyJobCanBeCanceledWithoutPublishing() {
        val r = repo()
        val id = r.queuePhotoImport("fixture-bar", listOf(photo("A")))
        r.finishPhotoImport(id, MockPhotoExtractionSource { listOf(
            MockExtractedLine("fixture", "Test", MockLineKind.PRODUCT,
                options = listOf(MockMenuOption("option", priceKrw = 12000)))
        ) })
        rejects { r.clearMenuForBar("fixture-bar") }
        r.cancelPhotoImport(id)
        assertEquals(MockImportStatus.CANCELED, snap(r).imports.single().status)
        assertEquals(0, snap(r).menuItems.size)
    }

    @Test fun photoLimitsRejectZeroAndSixteenAllowFifteen() {
        val r = repo()
        rejects { r.queuePhotoImport("fixture-bar", emptyList()) }
        rejects { r.queuePhotoImport("fixture-bar", (1..16).map { photo("p$it") }) }
        val id = r.queuePhotoImport("fixture-bar", (1..15).map { photo("p$it") })
        assertEquals(15, snap(r).imports.single { it.menuImportId == id }.images.size)
    }
}
