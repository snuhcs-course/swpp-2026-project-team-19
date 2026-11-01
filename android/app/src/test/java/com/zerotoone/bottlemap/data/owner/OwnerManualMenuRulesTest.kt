package com.zerotoone.bottlemap.data.owner

import org.junit.Assert.*
import org.junit.Test

class OwnerManualMenuRulesTest {
    private val brand = MockBrand("brand-lagavulin", "라가불린")
    private val ten = MockCatalogProduct("product-10", brand.brandId, "라가불린 10년")
    private val sixteen = MockCatalogProduct("product-16", brand.brandId, "라가불린 16년")
    private fun option(id: String, ml: Int?, price: Int, bottle: Boolean = false) =
        MockMenuOption(id, label = if (bottle) "Bottle" else null, pourMl = ml, priceKrw = price)
    private fun repo(store: MockOwnerStateStore = InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())) =
        LocalOwnerMockRepository(store)
    private fun snapshot(r: LocalOwnerMockRepository): MockOwnerSnapshot =
        (r.state.value as MockOwnerLoadState.Ready).snapshot
    private fun rejects(f: () -> Unit) {
        var rejected = false
        try { f() } catch (_: IllegalArgumentException) { rejected = true }
        assertTrue("Expected invalid direct menu mutation to be rejected", rejected)
    }

    @Test fun ownerPriceInputStopsAtEightDigitsIncludingPasteAndImeInput() {
        assertEquals("12345678", ownerPriceInput("123456789"))
        // A ninth digit inserted at the start or middle must be fully ignored.
        assertEquals("12345678", ownerPriceInput("12345678", "912345678"))
        assertEquals("12345678", ownerPriceInput("12345678", "123945678"))
        assertEquals("12345678", ownerPriceInput("12345678", "123456789"))
        assertEquals("12345678", ownerPriceInput("", "123456789"))
        assertEquals("1234567", ownerPriceInput("12345678", "1234567"))
        assertEquals("99999999", ownerPriceInput("99,999,999원"))
        assertEquals("12345678", ownerPriceInput("a1 b2,c3d4e5f6g7h8j9"))
        assertEquals("", ownerPriceInput("no digits"))
        assertTrue(validMockMenuOption(MockMenuOption("max", pourMl = 30,
            priceKrw = MAX_OWNER_MENU_PRICE_KRW)))
        // The photo-import pipeline keeps its legacy positive Int invariant.
        assertTrue(validMockMenuOption(MockMenuOption("over", pourMl = 30,
            priceKrw = 100_000_000)))
        assertNotNull(manualMenuOptionError(listOf(
            MockMenuOption("over", pourMl = 30, priceKrw = 100_000_000)), "whisky"))
    }

    @Test fun replacementLocalCategoryAcceptsSingleCocktailPriceAndRejectsWrongShape() {
        val r = repo()
        val local = MockCatalogProduct("local-unverified-changing", "local-brand-category",
            "Original whisky", category = "whisky", catalogMatched = false)
        val brand = MockBrand(local.brandId, "기타")
        r.saveManualMenuItem(MockBarMenuItem("change", "fixture-bar", local.productId,
            listOf(option("ml30", 30, 12000))), local, brand)
        val changed = local.copy(displayName = "새 칵테일", category = "cocktail")
        r.saveManualMenuItem(MockBarMenuItem("change", "fixture-bar", local.productId,
            listOf(option("single", null, 15000))), changed, brand)
        assertEquals("cocktail", snapshot(r).products.single().category)
        assertNull(snapshot(r).menuItems.single().options.single().pourMl)
        rejects {
            r.saveManualMenuItem(MockBarMenuItem("change", "fixture-bar", local.productId,
                listOf(option("ml99", 99, 15000), option("ml30-new", 30, 13000))),
                changed, brand)
        }
        assertEquals("cocktail", snapshot(r).products.single().category)
    }

    @Test fun manualPourLimitMatchesSharedImportInvariant() {
        val tooLarge = option("big", 32768, 10000)
        assertNotNull(manualMenuOptionError(listOf(tooLarge), "whisky"))
        assertFalse(validMockMenuOption(tooLarge))
        val boundary = option("max", 32767, 10000)
        assertNull(manualMenuOptionError(listOf(boundary), "whisky"))
        assertTrue(validMockMenuOption(boundary))
    }

    @Test fun importSupportsLegacyHighPricesAndFourOptionsWhileManualCannotCreateThem() {
        val r = repo()
        r.saveBrand(brand)
        r.saveCatalogProduct(ten)
        val imported = (1..4).map { index ->
            option("legacy-$index", index * 15, if (index == 4) 100_000_000 else 1000 * index)
        }
        r.saveMenuItem(MockBarMenuItem("legacy-row", "fixture-bar", ten.productId, imported))
        assertEquals(4, snapshot(r).menuItems.single().options.size)
        assertNotNull(manualMenuOptionError(imported, "whisky"))
        // Editing first three fields does not delete/import-rewrite the fourth option.
        val editFirstThree = imported.take(3).mapIndexed { index, o ->
            if (index == 0) o.copy(priceKrw = 3300) else o
        } + imported.drop(3)
        r.saveManualMenuItem(MockBarMenuItem("legacy-row", "fixture-bar",
            ten.productId, editFirstThree))
        assertEquals(editFirstThree, snapshot(r).menuItems.single().options)
        rejects {
            r.saveManualMenuItem(MockBarMenuItem("legacy-row", "fixture-bar",
                ten.productId, imported + option("fifth", 75, 2000)))
        }
    }

    @Test fun importedCocktailExtraOptionsAreRetainedWhileManualEditsSinglePrice() {
        val r = repo()
        val product = MockCatalogProduct("product-imported-cocktail", "brand-cocktail",
            "수제 칵테일", category = "cocktail")
        r.saveBrand(MockBrand(product.brandId, "칵테일"))
        r.saveCatalogProduct(product)
        val options = (1..4).map {
            MockMenuOption("import-cocktail-$it", label = "serving-$it", priceKrw = 4000 * it)
        }
        r.saveMenuItem(MockBarMenuItem("cocktail-menu", "fixture-bar", product.productId, options))
        val edited = listOf(options.first().copy(priceKrw = 6000)) + options.drop(1)
        r.saveManualMenuItem(MockBarMenuItem(
            "cocktail-menu", "fixture-bar", product.productId, edited))
        assertEquals(edited, snapshot(r).menuItems.single().options)
        assertNotNull(manualMenuOptionError(options, "cocktail"))
    }

    @Test fun changingCustomerVisibleMenuUpdatesFreshnessWithoutTouchingVerification() {
        val r = repo()
        r.saveManualMenuItem(MockBarMenuItem("menu-10", "fixture-bar", ten.productId,
            listOf(option("pour", 30, 10000))), ten, brand)
        val barBefore = snapshot(r).bars.single()
        r.setSoldOut("menu-10", true)
        val sold = snapshot(r).bars.single()
        assertNotNull(sold.lastMenuPublishedAtEpochMs)
        assertTrue(sold.lastMenuPublishedAtEpochMs!! >= barBefore.lastMenuPublishedAtEpochMs!!)
        assertEquals(barBefore.lastVerifiedAtEpochMs, sold.lastVerifiedAtEpochMs)
        r.setSoldOut("menu-10", false)
        assertEquals(1, r.preview("fixture-bar", 0L)!!.visibleMenu.size)
        r.deleteMenuItem("menu-10")
        val deleted = snapshot(r).bars.single()
        assertNotNull(deleted.lastMenuPublishedAtEpochMs)
        assertTrue(deleted.lastMenuPublishedAtEpochMs!! >= sold.lastMenuPublishedAtEpochMs!!)
        r.saveManualMenuItem(MockBarMenuItem("menu-again", "fixture-bar", ten.productId,
            listOf(option("pour-again", 45, 12000))))
        r.clearMenuForBar("fixture-bar")
        val reset = snapshot(r).bars.single()
        assertNotNull(reset.lastMenuPublishedAtEpochMs)
        assertEquals(deleted.lastVerifiedAtEpochMs, reset.lastVerifiedAtEpochMs)
        assertTrue(reset.lastMenuPublishedAtEpochMs!! >= deleted.lastMenuPublishedAtEpochMs!!)
        assertTrue(snapshot(r).menuItems.isEmpty())
    }

    @Test fun sameBrandDifferentCatalogIdsRemainDifferentProducts() {
        val store = InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())
        val r = repo(store)
        r.saveManualMenuItem(MockBarMenuItem("menu10", "fixture-bar", ten.productId,
            listOf(option("small", 30, 16000), option("full", null, 180000, true))),
            newProduct = ten, newBrand = brand)
        r.saveManualMenuItem(MockBarMenuItem("menu16", "fixture-bar", sixteen.productId,
            listOf(option("big", 45, 27000))),
            newProduct = sixteen, newBrand = brand)
        assertEquals(2, snapshot(r).menuItems.size)
        assertEquals(2, snapshot(r).products.size)
        assertEquals(1, snapshot(r).brands.size)
        assertEquals(2, r.preview("fixture-bar", 0L)!!.visibleMenu.size)
        assertEquals(2, snapshot(repo(store)).menuItems.size)
        rejects {
            r.saveManualMenuItem(MockBarMenuItem("duplicate", "fixture-bar", ten.productId,
                listOf(option("wrong", 60, 26000))))
        }
        assertEquals(2, snapshot(r).menuItems.size)
    }

    @Test fun duplicateOptionsAndInvalidPricesDoNotWriteAnyProductOrMenu() {
        val r = repo()
        val original = snapshot(r)
        rejects {
            r.saveManualMenuItem(MockBarMenuItem("new", "fixture-bar", ten.productId,
                listOf(option("a", 30, 16000), option("b", 30, 20000))),
                newProduct = ten, newBrand = brand)
        }
        rejects {
            r.saveManualMenuItem(MockBarMenuItem("new", "fixture-bar", ten.productId,
                listOf(option("a", 30, 16000), option("b", 60, 20000),
                    option("c", 90, 28000), option("d", 120, 35000))),
                newProduct = ten, newBrand = brand)
        }
        rejects {
            r.saveManualMenuItem(MockBarMenuItem("new", "fixture-bar", ten.productId,
                listOf(option("a", 30, 0))), newProduct = ten, newBrand = brand)
        }
        assertEquals(original, snapshot(r))
    }

    @Test fun unverifiedManualItemIsNotPretendedToBeCatalogMatched() {
        val r = repo()
        val local = MockCatalogProduct("local-unverified-custom-1", "local-brand-1",
            "수제 하이볼", category = "otherAlcohol", catalogMatched = false,
            otherAlcoholKind = "하이볼")
        r.saveManualMenuItem(MockBarMenuItem("local-menu-1", "fixture-bar", local.productId,
            listOf(option("local-serving-1", null, 15000))),
            newProduct = local, newBrand = MockBrand(local.brandId, "기타 주류"))
        assertFalse(snapshot(r).products.single().catalogMatched)
        assertEquals("하이볼", snapshot(r).products.single().otherAlcoholKind)
        r.setSoldOut("local-menu-1", true)
        assertTrue(snapshot(r).menuItems.single().soldOut)
        assertTrue(r.preview("fixture-bar", 0L)!!.visibleMenu.isEmpty())
        r.setSoldOut("local-menu-1", false)
        assertEquals(1, r.preview("fixture-bar", 0L)!!.visibleMenu.size)
        r.deleteMenuItem("local-menu-1")
        assertTrue(snapshot(r).menuItems.isEmpty())
        assertEquals(1, snapshot(r).products.size)
    }

    @Test fun discountsEditsAndFullResetPropagateThroughSameCustomerPreview() {
        val r = repo()
        val discounted = MockMenuOption("pour30", pourMl = 30, priceKrw = 16000,
            discount = MockDiscount(12000, 1000L, 3000L))
        val bottle = option("bottle", null, 200000, bottle = true)
        r.saveManualMenuItem(MockBarMenuItem("menu-10", "fixture-bar", ten.productId,
            listOf(discounted, bottle)), ten, brand)
        assertEquals(12000, r.preview("fixture-bar", 2000L)!!.visibleMenu.single()
            .options.first().displayPrice(2000L))
        assertEquals(16000, r.preview("fixture-bar", 3000L)!!.visibleMenu.single()
            .options.first().displayPrice(3000L))
        r.saveManualMenuItem(MockBarMenuItem("menu-10", "fixture-bar", ten.productId,
            listOf(option("pour30", 30, 18000), bottle)))
        assertEquals(18000, r.preview("fixture-bar", 2000L)!!.visibleMenu.single()
            .options.first().priceKrw)
        assertEquals(2, snapshot(r).menuItems.single().options.size)
        r.clearMenuForBar("fixture-bar")
        assertTrue(snapshot(r).menuItems.isEmpty())
        assertTrue(r.preview("fixture-bar", 2000L)!!.visibleMenu.isEmpty())
        // Reset clears a bar's listings, not the shared catalog product.
        assertEquals(ten, snapshot(r).products.single())
    }

    @Test fun ownerMenuLabelOverrideRetainsCanonicalCatalogIdentityAndSearch() {
        val r = repo()
        r.saveManualMenuItem(MockBarMenuItem("m10", "fixture-bar", ten.productId,
            listOf(option("small", 30, 16000)),
            displayNameOverride = "라가불린 10년 · 시그니처"), newProduct = ten, newBrand = brand)
        val snap = snapshot(r)
        val row = snap.menuItems.single()
        assertEquals(ten.productId, row.productId)
        assertEquals("라가불린 10년 · 시그니처", row.displayNameOverride)
        assertEquals("라가불린 10년", snap.products.single().displayName)
        assertTrue(manualMenuMatches(row, ten, brand.name, "시그니처"))
        assertEquals(row, r.preview("fixture-bar", 0L)!!.visibleMenu.single())
    }

    @Test fun searchingUsesBrandAndDisplayTextWithoutMergingDifferentAges() {
        val row10 = MockBarMenuItem("m10", "fixture-bar", ten.productId,
            listOf(option("opt10", 30, 16000)))
        assertTrue(manualMenuMatches(row10, ten, "라가불린", "라가"))
        assertTrue(manualMenuMatches(row10, ten, "라가불린", "10년"))
        assertFalse(manualMenuMatches(row10, ten, "라가불린", "16년"))
        assertEquals("10년", manualMenuShortName(ten, "라가불린"))
        assertEquals("16년", manualMenuShortName(sixteen, "라가불린"))
        assertNull(existingBarProductMenu(listOf(row10), "fixture-bar", sixteen.productId))
    }
    @Test fun importedLocalizedServingLabelsAreValidAndRemainIntactOnUnrelatedEdit() {
        val r = repo()
        r.saveBrand(brand)
        r.saveCatalogProduct(ten)
        val imported = listOf(
            MockMenuOption("ko-bottle", label = "병", pourMl = null, priceKrw = 100_000_000),
            MockMenuOption("ko-glass", label = "잔", pourMl = 30, priceKrw = 17_000),
            MockMenuOption("unspecified", label = null, pourMl = null, priceKrw = 25_000),
        )
        r.saveMenuItem(MockBarMenuItem("localized", "fixture-bar", ten.productId, imported))
        assertNull(manualMenuOptionError(imported, "whisky", imported))
        r.saveManualMenuItem(MockBarMenuItem("localized", "fixture-bar", ten.productId,
            imported, displayNameOverride = "새 메뉴 이름"))
        assertEquals(imported, snapshot(r).menuItems.single().options)
        assertEquals("새 메뉴 이름", snapshot(r).menuItems.single().displayNameOverride)
        rejects {
            r.saveManualMenuItem(MockBarMenuItem("localized", "fixture-bar", ten.productId,
                imported.toMutableList().also { it[0] = it[0].copy(priceKrw = 100_000_001) }))
        }
        assertEquals(imported, snapshot(r).menuItems.single().options)
    }

    @Test fun activePhotoReviewBlocksAllManualMutationPathsAndTerminalJobsUnlockThem() {
        val existing = MockBarMenuItem("existing", "fixture-bar", ten.productId,
            listOf(option("pour", 30, 13000)))
        val base = OwnerMockFixtures.registeredBar().copy(
            brands = listOf(brand), products = listOf(ten), menuItems = listOf(existing))
        for (status in listOf(MockImportStatus.PROCESSING, MockImportStatus.READY_FOR_REVIEW)) {
            val s = base.copy(imports = listOf(MockMenuImport("job-$status", "fixture-bar",
                status, 1, emptyList())))
            val r = repo(InMemoryMockOwnerStateStore(s))
            rejects { r.saveManualMenuItem(existing.copy(displayNameOverride = "changed")) }
            rejects { r.saveMenuItem(existing.copy(soldOut = true)) }
            rejects { r.deleteMenuItem(existing.barMenuItemId) }
            rejects { r.clearMenuForBar("fixture-bar") }
            rejects { r.setSoldOut(existing.barMenuItemId, true) }
            assertEquals(s, snapshot(r))
            assertEquals(1, r.preview("fixture-bar", 0L)!!.visibleMenu.size)
        }
        for (status in listOf(MockImportStatus.FAILED, MockImportStatus.APPLIED)) {
            val r = repo(InMemoryMockOwnerStateStore(base.copy(imports = listOf(
                MockMenuImport("done-$status", "fixture-bar", status, 1, emptyList())))))
            r.saveManualMenuItem(existing.copy(displayNameOverride = "allowed"))
            assertEquals("allowed", snapshot(r).menuItems.single().displayNameOverride)
        }
    }

    @Test fun elevenImportedOptionsCanBeReadButNotResavedWithoutExplicitReduction() {
        val r = repo()
        r.saveBrand(brand)
        r.saveCatalogProduct(ten)
        val imported = (1..11).map { option("existing-$it", it * 10, 1000 * it) }
        r.saveMenuItem(MockBarMenuItem("many", "fixture-bar", ten.productId, imported))
        assertEquals(11, r.preview("fixture-bar", 0L)!!.visibleMenu.single().options.size)
        rejects {
            r.saveManualMenuItem(MockBarMenuItem("many", "fixture-bar", ten.productId,
                imported, displayNameOverride = "changed"))
        }
        assertEquals(imported, snapshot(r).menuItems.single().options)
    }

}
