package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.*
import org.junit.Assert.*
import org.junit.Test

class OwnerPhotoStage8Test {
    private fun ready(r: OwnerMockRepository) =
        (r.state.value as MockOwnerLoadState.Ready).snapshot

    private fun photo(id: String) = MockPhoto(id, "file:///mock/$id.jpg", MockPhotoKind.MENU_CAPTURE)
    private fun reject(block: () -> Unit) {
        try { block(); fail("Expected rejection") }
        catch (_: IllegalArgumentException) {}
        catch (_: IllegalStateException) {}
    }

    @Test fun twoPhotosDynamicCountsAndDecisionsSurviveRepositoryRecreation() {
        val store = InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())
        val r = LocalOwnerMockRepository(store)
        r.saveBrand(MockBrand("known-brand", "Known"))
        r.saveCatalogProduct(MockCatalogProduct("known-product", "known-brand", "Known 12"))
        r.saveMenuItem(MockBarMenuItem("known-row", "fixture-bar", "known-product",
            listOf(MockMenuOption("known-opt", priceKrw = 12000))))
        val id = r.queuePhotoImport("fixture-bar", listOf(photo("a"),photo("b")))
        r.finishPhotoImport(id,MockPhotoExtractionSource { uri ->
            if(uri.endsWith("a.jpg")) listOf(MockExtractedLine("a","Known 12",
                MockLineKind.PRODUCT,suggestedProductId="known-product",
                options=listOf(MockMenuOption("o1",label="잔",pourMl=30,priceKrw=12000))))
            else listOf(
                MockExtractedLine("b","Unknown item",MockLineKind.PRODUCT,
                    options=listOf(MockMenuOption("o2",priceKrw=17500))),
                MockExtractedLine("c","Notice",MockLineKind.NON_PRODUCT)
            )
        })
        val job = ready(r).imports.single()
        val ids = job.images.flatMap{it.lines.map {line->line.extractedItemId}}
        assertEquals(2,stage8Counts(job,ready(r)).photos)
        assertEquals(3,stage8Counts(job,ready(r)).lines)
        assertEquals(1,stage8Counts(job,ready(r)).existing)
        r.decideLine(id,ids[0],job.reviewVersion,MockReviewDecision(
            MockDecisionKind.SELECT_PRODUCT,productId="known-product"))
        r.decideLine(id,ids[1],job.reviewVersion,MockReviewDecision(
            MockDecisionKind.CREATE_PRODUCT,
            correctedOptions=listOf(job.images[1].lines[0].options[0].copy(priceKrw=18000)),
            newProduct=MockNewProductDraft(name="User confirmed new",brandName="New brand")))
        r.decideLine(id,ids[2],job.reviewVersion,
            MockReviewDecision(MockDecisionKind.CONFIRM_NON_PRODUCT))
        val after=ready(LocalOwnerMockRepository(store)).imports.single()
        assertEquals(ids,after.images.flatMap {it.lines.map{line->line.extractedItemId}})
        assertEquals(0,stage8Counts(after,ready(r)).remaining)
        assertEquals(3,stage8Counts(after,ready(r)).reviewed)
        assertEquals(1,r.publishAddOnly(id,after.reviewVersion))
        val applied=ready(r)
        assertEquals(MockImportStatus.APPLIED,applied.imports.single().status)
        assertEquals(2,applied.menuItems.size)
        assertEquals(12000,applied.menuItems.first{it.productId=="known-product"}.options.single().priceKrw)
        val added=applied.products.first {it.displayName=="User confirmed new"}
        assertEquals(18000,applied.menuItems.first{it.productId==added.productId}.options.single().priceKrw)
    }

    @Test fun incompleteAndInactiveCandidateCannotPublishOrSelect() {
        val r=LocalOwnerMockRepository(InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        r.saveBrand(MockBrand("b","Brand"))
        r.saveCatalogProduct(MockCatalogProduct("inactive","b","Old",isActive=false))
        val id=r.queuePhotoImport("fixture-bar",listOf(photo("p")))
        r.finishPhotoImport(id,MockPhotoExtractionSource {
            listOf(MockExtractedLine("candidate","Old",MockLineKind.PRODUCT,
                suggestedProductId="inactive",
                options=listOf(MockMenuOption("o",priceKrw=19000))))
        })
        val j=ready(r).imports.single()
        val line=j.images.single().lines.single()
        reject{r.decideLine(id,line.extractedItemId,j.reviewVersion,
            MockReviewDecision(MockDecisionKind.SELECT_PRODUCT,"inactive"))}
        reject{r.publishAddOnly(id,j.reviewVersion)}
        assertNull(ready(r).imports.single().images.single().lines.single().decision)
    }

    @Test fun highReviewedPriceIsAllowedAndAbsentSourceBoxNeverInventsCoordinates() {
        val r=LocalOwnerMockRepository(InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val id=r.queuePhotoImport("fixture-bar",listOf(photo("a")))
        r.finishPhotoImport(id,MockPhotoExtractionSource {
            listOf(MockExtractedLine("raw","OCR price overflow",MockLineKind.PRODUCT,
                options=listOf(MockMenuOption("o",label="병",priceKrw=100_000_000))))
        })
        val job=ready(r).imports.single()
        val line=job.images.single().lines.single()
        assertNull(line.sourceBox)
        assertTrue(line.needsPriceEntry)
        assertEquals(0,line.options.single().priceKrw)
        r.decideLine(id,line.extractedItemId,job.reviewVersion,
            MockReviewDecision(MockDecisionKind.CREATE_PRODUCT,
                correctedOptions=listOf(line.options.single().copy(priceKrw=100_000_000)),
                newProduct=MockNewProductDraft(name="Confirmed bottle",
                    brandName="Confirmed brand")))
        assertEquals(1,r.publishAddOnly(id,job.reviewVersion))
        assertEquals(100_000_000,ready(r).menuItems.single().options.single().priceKrw)
        assertNull(ready(r).imports.single().images.single().lines.single().sourceBox)
    }

    @Test fun malformedSourceBoxRejectedBeforeReviewWithoutMutation() {
        val r=LocalOwnerMockRepository(InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val id=r.queuePhotoImport("fixture-bar",listOf(photo("a")))
        reject {r.finishPhotoImport(id,MockPhotoExtractionSource {
            listOf(MockExtractedLine("invalid","raw",MockLineKind.PRODUCT,
                sourceBox=listOf(950,20,100,900),
                options=listOf(MockMenuOption("o",priceKrw=9000))))
        })}
        assertEquals(MockImportStatus.PROCESSING,ready(r).imports.single().status)
    }
}
