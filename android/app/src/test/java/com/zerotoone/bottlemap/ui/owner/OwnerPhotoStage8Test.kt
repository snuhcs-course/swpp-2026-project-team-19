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
        // Two accepted lines, but only one new bar-menu item will be inserted.
        assertEquals(1,stage8ExpectedAddedCount(after,ready(r)))
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

    @Test fun mockExactMatchNeedsExplicitDecisionEvenAfterReviewReset() {
        val r=LocalOwnerMockRepository(InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        r.saveBrand(MockBrand("known-brand","Known"))
        r.saveCatalogProduct(MockCatalogProduct("known-id","known-brand","Known 12"))
        val id=r.queuePhotoImport("fixture-bar",listOf(photo("a")))
        r.finishPhotoImport(id,MockPhotoExtractionSource {
            listOf(MockExtractedLine("a","Known 12",MockLineKind.PRODUCT,
                suggestedProductId="known-id",mockAutoAccepted=true,
                options=listOf(MockMenuOption("o",priceKrw=12000))))
        })
        val job=ready(r).imports.single()
        val line=job.images.single().lines.single()
        assertTrue(line.mockAutoAccepted)
        assertNull(line.decision)
        assertEquals(1,stage8Counts(job,ready(r)).remaining)
        reject {r.publishAddOnly(id,job.reviewVersion)}
        r.decideLine(id,line.extractedItemId,job.reviewVersion,
            MockReviewDecision(MockDecisionKind.SELECT_PRODUCT,productId="known-id",
                correctedOptions=line.options))
        assertEquals(0,stage8Counts(ready(r).imports.single(),ready(r)).remaining)
        r.resetPhotoReview(id,job.reviewVersion)
        assertNull(ready(r).imports.single().images.single().lines.single().decision)
        reject {r.publishAddOnly(id,job.reviewVersion+1)}
    }

    @Test fun editionLengthIsCheckedWhenSavingNewProductDecision() {
        val r=LocalOwnerMockRepository(InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val id=r.queuePhotoImport("fixture-bar",listOf(photo("a")))
        r.finishPhotoImport(id,MockPhotoExtractionSource {
            listOf(MockExtractedLine("a","New product",MockLineKind.PRODUCT,
                options=listOf(MockMenuOption("o",priceKrw=10000))))
        })
        val job=ready(r).imports.single()
        val line=job.images.single().lines.single()
        fun decision(edition:String)=MockReviewDecision(MockDecisionKind.CREATE_PRODUCT,
            correctedOptions=line.options,
            newProduct=MockNewProductDraft(name="New",brandName="New brand",
                editionName=edition))
        reject {r.decideLine(id,line.extractedItemId,job.reviewVersion,decision("x".repeat(151)))}
        reject {r.decideLine(id,line.extractedItemId,job.reviewVersion,decision("  "))}
        assertNull(ready(r).imports.single().images.single().lines.single().decision)
        r.decideLine(id,line.extractedItemId,job.reviewVersion,decision("x".repeat(150)))
        assertNotNull(ready(r).imports.single().images.single().lines.single().decision)
    }

    @Test fun autoProposalsReflectOnlyFinalOwnerConfirmedMatch() {
        val initial=MockExtractedLine("a","Whisky",MockLineKind.PRODUCT,
            suggestedProductId="catalog-original",mockAutoAccepted=true,
            options=listOf(MockMenuOption("o",priceKrw=12000)))
        assertFalse(stage8ConfirmedAutoMatch(initial))
        assertTrue(stage8ConfirmedAutoMatch(initial.copy(
            decision=MockReviewDecision(MockDecisionKind.SELECT_PRODUCT,
                productId="catalog-original"))))
        assertFalse(stage8ConfirmedAutoMatch(initial.copy(
            decision=MockReviewDecision(MockDecisionKind.SELECT_PRODUCT,
                productId="catalog-other"))))
        assertFalse(stage8ConfirmedAutoMatch(initial.copy(
            decision=MockReviewDecision(MockDecisionKind.EXCLUDE))))
    }

    @Test fun previewCountMatchesPublicationForDifferentlyCasedEditions() {
        val r=LocalOwnerMockRepository(InMemoryMockOwnerStateStore(
            OwnerMockFixtures.registeredBar()))
        r.saveBrand(MockBrand("review-brand","Review Brand"))
        val id=r.queuePhotoImport("fixture-bar",listOf(photo("a")))
        r.finishPhotoImport(id,MockPhotoExtractionSource {
            listOf(
                MockExtractedLine("a1","Whisky case 1",MockLineKind.PRODUCT,
                    options=listOf(MockMenuOption("o1",label="잔",pourMl=30,priceKrw=12000))),
                MockExtractedLine("a2","Whisky case 2",MockLineKind.PRODUCT,
                    options=listOf(MockMenuOption("o2",label="잔",pourMl=60,priceKrw=21000)))
            )
        })
        val job=ready(r).imports.single()
        val lines=job.images.single().lines
        listOf("Cask Strength","cask strength").forEachIndexed {i,edition ->
            r.decideLine(id,lines[i].extractedItemId,job.reviewVersion,
                MockReviewDecision(MockDecisionKind.CREATE_PRODUCT,
                    correctedOptions=lines[i].options,
                    newProduct=MockNewProductDraft("Whisky",brandId="review-brand",
                        editionName=edition)))
        }
        assertEquals(2,stage8ExpectedAddedCount(ready(r).imports.single(),ready(r)))
        assertEquals(2,r.publishAddOnly(id,job.reviewVersion))
        assertEquals(2,ready(r).imports.single().publishedAddedCount)
    }

    @Test fun finalExistingRowsAndCorrectedPricesIgnoreOriginalCatalogSuggestions() {
        val r=LocalOwnerMockRepository(InMemoryMockOwnerStateStore(
            OwnerMockFixtures.registeredBar()))
        r.saveBrand(MockBrand("brand","Whisky Brand"))
        r.saveCatalogProduct(MockCatalogProduct("already","brand","Already on bar"))
        r.saveCatalogProduct(MockCatalogProduct("replacement","brand","Other whisky"))
        r.saveMenuItem(MockBarMenuItem("old-row","fixture-bar","already",
            listOf(MockMenuOption("old",label="잔",pourMl=30,priceKrw=12000))))
        val id=r.queuePhotoImport("fixture-bar",listOf(photo("a")))
        r.finishPhotoImport(id,MockPhotoExtractionSource {
            listOf(
                MockExtractedLine("a1","Suggested old but replaced",MockLineKind.PRODUCT,
                    suggestedProductId="already",
                    options=listOf(MockMenuOption("o1",label="잔",pourMl=30,priceKrw=18000))),
                MockExtractedLine("a2","Selected old with corrected price",MockLineKind.PRODUCT,
                    suggestedProductId="already",
                    options=listOf(MockMenuOption("o2",label="잔",pourMl=30,priceKrw=0))),
                MockExtractedLine("a3","Suggested old but excluded",MockLineKind.PRODUCT,
                    suggestedProductId="already",
                    options=listOf(MockMenuOption("o3",label="잔",pourMl=30,priceKrw=9000)))
            )
        })
        val job=ready(r).imports.single()
        val lines=job.images.single().lines
        r.decideLine(id,lines[0].extractedItemId,job.reviewVersion,
            MockReviewDecision(MockDecisionKind.SELECT_PRODUCT,productId="replacement",
                correctedOptions=lines[0].options))
        r.decideLine(id,lines[1].extractedItemId,job.reviewVersion,
            MockReviewDecision(MockDecisionKind.SELECT_PRODUCT,productId="already",
                correctedOptions=listOf(lines[1].options.single().copy(priceKrw=19500))))
        r.decideLine(id,lines[2].extractedItemId,job.reviewVersion,
            MockReviewDecision(MockDecisionKind.EXCLUDE))
        val reviewed=ready(r).imports.single()
        assertEquals(listOf(lines[1].extractedItemId),
            stage8ConfirmedExistingLines(reviewed,ready(r)).map {it.extractedItemId})
        assertEquals(1,stage8RetainedPriceMismatchCount(reviewed,ready(r)))
        assertEquals(1,stage8ExpectedAddedCount(reviewed,ready(r)))
        assertEquals(1,r.publishAddOnly(id,job.reviewVersion))
        assertEquals(12000,ready(r).menuItems.first{it.productId=="already"}
            .options.single().priceKrw)
        assertEquals(1,stage8RetainedPriceMismatchCount(ready(r).imports.single(),ready(r)))
    }

    @Test fun finalExistingRowsAndCorrectedPricesAreEmptyWithoutExistingProducts() {
        val r=LocalOwnerMockRepository(InMemoryMockOwnerStateStore(
            OwnerMockFixtures.registeredBar()))
        val id=r.queuePhotoImport("fixture-bar",listOf(photo("empty-existing")))
        r.finishPhotoImport(id,MockPhotoExtractionSource {
            listOf(MockExtractedLine("line","Unknown whisky",MockLineKind.PRODUCT,
                options=listOf(MockMenuOption("opt",priceKrw=18000))))
        })
        val job=ready(r).imports.single()
        assertEquals(0,stage8Counts(job,ready(r)).existing)
        assertTrue(stage8ConfirmedExistingLines(job,ready(r)).isEmpty())
        assertEquals(0,stage8RetainedPriceMismatchCount(job,ready(r)))
    }

    @Test fun malformedSourceBoxBecomesDurableFailedJobAndCanRetry() {
        val store=InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())
        val r=LocalOwnerMockRepository(store)
        val id=r.queuePhotoImport("fixture-bar",listOf(photo("a")))
        assertEquals(MockImportStatus.FAILED,r.finishPhotoImport(id,MockPhotoExtractionSource {
            listOf(MockExtractedLine("invalid","raw",MockLineKind.PRODUCT,
                sourceBox=listOf(950,20,100,900),
                options=listOf(MockMenuOption("o",priceKrw=9000))))
        }))
        val failed=ready(LocalOwnerMockRepository(store)).imports.single()
        assertEquals(MockImportStatus.FAILED,failed.status)
        assertTrue(failed.failureReason?.contains("검증 실패")==true)
        assertTrue(failed.images.single().lines.isEmpty())
        val retry=r.retryFailedPhotoImport(id)
        assertEquals(MockImportStatus.READY_FOR_REVIEW,
            r.finishPhotoImport(retry,MockPhotoExtractionSource {
                listOf(MockExtractedLine("valid","raw",MockLineKind.PRODUCT,
                    options=listOf(MockMenuOption("o",priceKrw=9000))))
            }))
        assertEquals(MockImportStatus.READY_FOR_REVIEW,ready(r).imports.last().status)
    }

    @Test fun malformedSecondPhotoOrAutoMatchMustFailWholeBatchWithoutLeakingLines() {
        val r=LocalOwnerMockRepository(InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val id=r.queuePhotoImport("fixture-bar",listOf(photo("a"),photo("b")))
        assertEquals(MockImportStatus.FAILED,r.finishPhotoImport(id,MockPhotoExtractionSource { uri ->
            if(uri.endsWith("a.jpg")) listOf(MockExtractedLine("valid","Whisky",MockLineKind.PRODUCT,
                options=listOf(MockMenuOption("a",priceKrw=12000))))
            else listOf(MockExtractedLine("auto","Unknown",MockLineKind.PRODUCT,
                suggestedProductId="unknown",mockAutoAccepted=true,
                options=listOf(MockMenuOption("b",priceKrw=15000))))
        }))
        val failed=ready(r).imports.single()
        assertEquals(MockImportStatus.FAILED,failed.status)
        assertTrue(failed.failureReason?.contains("Invalid mock auto-accepted fixture")==true)
        assertTrue(failed.images.all{it.lines.isEmpty()})
        val another=r.queuePhotoImport("fixture-bar",listOf(photo("c")))
        assertNotEquals(id,another)
    }

    @Test fun correctedNameOverridesMustBeTrimmedOneToTwoHundredCharactersForBothDecisions() {
        val r=LocalOwnerMockRepository(InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        r.saveBrand(MockBrand("known-brand","Known Brand"))
        r.saveCatalogProduct(MockCatalogProduct("known-product","known-brand","Known Whisky"))
        val id=r.queuePhotoImport("fixture-bar",listOf(photo("a")))
        r.finishPhotoImport(id,MockPhotoExtractionSource {
            listOf(
                MockExtractedLine("known","Known Whisky",MockLineKind.PRODUCT,
                    suggestedProductId="known-product",
                    options=listOf(MockMenuOption("o1",priceKrw=15000))),
                MockExtractedLine("new","New Whisky",MockLineKind.PRODUCT,
                    options=listOf(MockMenuOption("o2",priceKrw=20000)))
            )
        })
        val job=ready(r).imports.single()
        val lines=job.images.single().lines
        lines.forEachIndexed { i,line ->
            fun decision(name:String)=if(i==0) MockReviewDecision(
                MockDecisionKind.SELECT_PRODUCT,productId="known-product",
                correctedOptions=line.options,displayNameOverride=name)
            else MockReviewDecision(MockDecisionKind.CREATE_PRODUCT,
                newProduct=MockNewProductDraft(name="New Whisky",brandName="New Brand"),
                correctedOptions=line.options,displayNameOverride=name)
            for(invalid in listOf("  ","x".repeat(201))) {
                reject{r.decideLine(id,line.extractedItemId,job.reviewVersion,decision(invalid))}
                assertNull(ready(r).imports.single().images.single().lines[i].decision)
            }
            val valid="  "+"x".repeat(200)+"  "
            r.decideLine(id,line.extractedItemId,job.reviewVersion,decision(valid))
            assertEquals("x".repeat(200),
                ready(r).imports.single().images.single().lines[i].decision?.displayNameOverride)
        }
        assertEquals(2,r.publishAddOnly(id,job.reviewVersion))
        assertTrue(ready(r).menuItems.all{it.displayNameOverride=="x".repeat(200)})
    }
}
