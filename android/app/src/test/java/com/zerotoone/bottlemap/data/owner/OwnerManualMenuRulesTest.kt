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
}
