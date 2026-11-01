package com.zerotoone.bottlemap.ui.owner

import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsFocused
import androidx.compose.ui.test.assertIsNotFocused
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.click
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.zerotoone.bottlemap.data.owner.*
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class OwnerManualMenuComposeTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    private fun fixture(): OwnerMockViewModel {
        val repo = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        repo.saveBrand(MockBrand("brand-lagavulin", "라가불린"))
        repo.saveCatalogProduct(MockCatalogProduct("prod-10", "brand-lagavulin", "라가불린 10년"))
        repo.saveCatalogProduct(MockCatalogProduct("prod-16", "brand-lagavulin", "라가불린 16년"))
        repo.saveMenuItem(MockBarMenuItem("bar-10", "fixture-bar", "prod-10",
            listOf(MockMenuOption("opt30", pourMl = 30, priceKrw = 13000),
                MockMenuOption("optBottle", label = "Bottle", priceKrw = 200000))))
        return OwnerMockViewModel(repo)
    }

    @Test fun selectedRowKeepsFixedHeightAndEditReturnsToUnselectedList() {
        val vm = fixture()
        compose.setContent {
            MaterialTheme {
                OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
            }
        }
        val row = compose.onNodeWithTag("manual-menu-row-bar-10")
        val before = row.fetchSemanticsNode().boundsInRoot.height
        row.performClick()
        val after = compose.onNodeWithTag("manual-menu-row-bar-10")
            .fetchSemanticsNode().boundsInRoot.height
        assertEquals(before, after, 0.1f)
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.onNodeWithTag("manual-menu-row-edit").assertDoesNotExist()
        compose.runOnIdle {
            assertEquals(2, vm.preview("fixture-bar", 0L)!!.visibleMenu.single().options.size)
        }
    }

    @Test fun manuallyAddedCatalogItemImmediatelyAppearsInCustomerMockPreview() {
        val vm = OwnerMockViewModel(LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())))
        compose.setContent {
            MaterialTheme {
                OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
            }
        }
        compose.onNodeWithTag("manual-menu-add").performClick()
        compose.onNodeWithTag("manual-menu-name").performTextInput("라가불린 10년")
        compose.onNodeWithText("맞아요").performClick()
        compose.onNodeWithTag("manual-menu-ml-0").performTextInput("30")
        compose.onNodeWithTag("manual-menu-price-0").performTextInput("15000")
        // Bottle checkbox and price option IDs are separate from the catalog ID.
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            val preview = vm.preview("fixture-bar", 0L)!!
            assertEquals(1, preview.visibleMenu.size)
            assertEquals("mock-lagavulin-10", preview.visibleMenu.single().productId)
            assertEquals(15000, preview.visibleMenu.single().options.single().priceKrw)
        }
    }

    @Test fun decliningSuggestionKeepsManualItemCatalogUnverified() {
        val vm = OwnerMockViewModel(LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())))
        compose.setContent {
            MaterialTheme {
                OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
            }
        }
        compose.onNodeWithTag("manual-menu-add").performClick()
        compose.onNodeWithTag("manual-menu-name").performTextInput("라가불린 10년")
        compose.onNodeWithText("아니에요").performClick()
        compose.onNodeWithTag("manual-menu-ml-0").performTextInput("30")
        compose.onNodeWithTag("manual-menu-price-0").performTextInput("12000")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            val snap = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            val product = snap.products.single()
            assertEquals(false, product.catalogMatched)
            assertEquals(true, product.productId.startsWith("local-unverified-"))
            assertEquals(1, vm.preview("fixture-bar", 0L)!!.visibleMenu.size)
        }
    }

    @Test fun discountedAndRegularOptionsKeepPriceRightEdgeAligned() {
        val repo = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val now = System.currentTimeMillis()
        repo.saveBrand(MockBrand("brand-l", "라가불린"))
        repo.saveCatalogProduct(MockCatalogProduct("prod-l", "brand-l", "라가불린 10년"))
        repo.saveMenuItem(MockBarMenuItem("menu-l", "fixture-bar", "prod-l",
            listOf(MockMenuOption("pour30", pourMl = 30, priceKrw = 10000,
                    discount = MockDiscount(5000, now - 100000L, now + 100000L)),
                MockMenuOption("pour45", pourMl = 45, priceKrw = 20000))))
        val vm = OwnerMockViewModel(repo)
        compose.setContent {
            MaterialTheme {
                OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
            }
        }
        val discounted = compose.onNodeWithText("5,000원").fetchSemanticsNode().boundsInRoot.right
        val normal = compose.onNodeWithText("20,000원").fetchSemanticsNode().boundsInRoot.right
        assertEquals(normal, discounted, 1f)
    }

    @Test fun activeDiscountShownInOwnerPriceAndEditorOptionHeader() {
        val repo = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val now = System.currentTimeMillis()
        repo.saveBrand(MockBrand("brand-l", "라가불린"))
        repo.saveCatalogProduct(MockCatalogProduct("product-l", "brand-l", "라가불린 10년"))
        repo.saveMenuItem(MockBarMenuItem("discounted", "fixture-bar", "product-l",
            listOf(MockMenuOption("opt30", pourMl = 30, priceKrw = 10000,
                discount = MockDiscount(5000, now - 100000L, now + 100000L)))))
        val vm = OwnerMockViewModel(repo)
        compose.setContent {
            MaterialTheme {
                OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
            }
        }
        compose.onNodeWithText("할인").assertExists()
        compose.onNodeWithText("5,000원").assertExists()
        compose.onNodeWithTag("manual-menu-row-discounted").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithText("할인 · 5000원").assertExists()
    }

    @Test fun scheduledDiscountHiddenInCustomerMenuBeforeItStarts() {
        val repo = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val now = System.currentTimeMillis()
        repo.saveBrand(MockBrand("brand-scheduled", "라가불린"))
        repo.saveCatalogProduct(MockCatalogProduct(
            "product-scheduled", "brand-scheduled", "라가불린 10년"))
        repo.saveMenuItem(MockBarMenuItem("scheduled", "fixture-bar", "product-scheduled",
            listOf(MockMenuOption("scheduled30", pourMl = 30, priceKrw = 10000,
                discount = MockDiscount(5000,
                    now + 86_400_000L, now + 259_200_000L)))))
        val preview = repo.preview("fixture-bar", now)!!
        compose.setContent {
            MaterialTheme {
                OwnerPreviewV4Menu(preview.bar, preview,
                    listOf(MockBrand("brand-scheduled", "라가불린")), now)
            }
        }
        compose.onNodeWithText("할인").assertDoesNotExist()
        // Both the badge and discounted price appear only during the discount period.
        compose.onNodeWithText("10,000원").assertExists()
        compose.onNodeWithText("5,000원").assertDoesNotExist()
    }

    @Test fun customerSharesPriceDesignWithoutOwnerStockBadgesOrSoldOutProducts() {
        val repo = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val now = System.currentTimeMillis()
        repo.saveBrand(MockBrand("brand-l", "라가불린"))
        repo.saveCatalogProduct(MockCatalogProduct("ten", "brand-l", "라가불린 10년"))
        repo.saveCatalogProduct(MockCatalogProduct("sixteen", "brand-l", "라가불린 16년"))
        repo.saveMenuItem(MockBarMenuItem("visible", "fixture-bar", "ten",
            listOf(MockMenuOption("p30", pourMl = 30, priceKrw = 10000,
                discount = MockDiscount(5000, now - 100000L, now + 100000L)))))
        repo.saveMenuItem(MockBarMenuItem("sold", "fixture-bar", "sixteen",
            listOf(MockMenuOption("p40", pourMl = 40, priceKrw = 15000)), soldOut = true))
        val preview = repo.preview("fixture-bar", now)!!
        assertEquals(1, preview.visibleMenu.size)
        compose.setContent {
            MaterialTheme {
                OwnerPreviewV4Menu(preview.bar, preview,
                    listOf(MockBrand("brand-l", "라가불린")), now)
            }
        }
        compose.onNodeWithText("할인").assertExists()
        compose.onNodeWithText("5,000원").assertExists()
        compose.onNodeWithText("16년").assertDoesNotExist()
        compose.onNodeWithText("판매 중").assertDoesNotExist()
        compose.onNodeWithText("품절").assertDoesNotExist()
    }

    @Test fun editorPriceFieldRefocusesAfterTappingOutsideInput() {
        val vm = OwnerMockViewModel(LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())))
        compose.setContent {
            MaterialTheme {
                OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
            }
        }
        compose.onNodeWithTag("manual-menu-add").performClick()
        compose.onNodeWithTag("manual-menu-price-0").performClick()
        compose.onNodeWithTag("manual-menu-price-0").assertIsFocused()
        compose.onNodeWithText("용량별 가격").performTouchInput { click() }
        compose.onNodeWithTag("manual-menu-price-0").assertIsNotFocused()
        compose.onNodeWithTag("manual-menu-price-0").performClick()
        compose.onNodeWithTag("manual-menu-price-0").assertIsFocused()
    }

    @Test fun regularAndDiscountPriceInputRejectNinthDigitAndUseVacationCalendar() {
        val vm = OwnerMockViewModel(LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())))
        compose.setContent {
            MaterialTheme {
                OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
            }
        }
        compose.onNodeWithTag("manual-menu-add").performClick()
        compose.onNodeWithTag("manual-menu-price-0").performTextInput("123456789")
        compose.onNodeWithTag("manual-menu-price-0").assertTextEquals("12345678")
        compose.onNodeWithText("할인").performClick()
        compose.onNodeWithTag("manual-menu-discount-price").performTextInput("999999999")
        compose.onNodeWithTag("manual-menu-discount-price").assertTextEquals("99999999")
        compose.onNodeWithTag("manual-menu-start-date").performScrollTo().performClick()
        compose.onNodeWithText("시작 선택").assertExists()
        compose.onNodeWithText("종료 선택").assertExists()
    }

    @Test fun backFromDiscountEditorDiscardsUnappliedPrice() {
        val vm = fixture()
        compose.setContent {
            MaterialTheme {
                OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
            }
        }
        compose.onNodeWithTag("manual-menu-row-bar-10").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithText("할인").performClick()
        compose.onNodeWithTag("manual-menu-discount-price").performTextInput("3000")
        compose.onNodeWithContentDescription("뒤로가기").performClick()
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            val saved = vm.preview("fixture-bar", System.currentTimeMillis())!!
                .visibleMenu.single().options
            assertEquals(null, saved.first().discount)
            assertEquals(2, saved.size)
        }
    }

    @Test fun editingImportedSameDayDiscountDoesNotRoundOrLoseExactTimestamps() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val now = System.currentTimeMillis()
        val discount = MockDiscount(5000, now - 100000L, now + 100000L)
        r.saveBrand(MockBrand("brand-exact", "라가불린"))
        r.saveCatalogProduct(MockCatalogProduct("prod-exact", "brand-exact", "라가불린 10년"))
        r.saveMenuItem(MockBarMenuItem("menu-exact", "fixture-bar", "prod-exact",
            listOf(MockMenuOption("exact30", pourMl = 30, priceKrw = 10000,
                discount = discount))))
        val vm = OwnerMockViewModel(r)
        compose.setContent {
            MaterialTheme {
                OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
            }
        }
        compose.onNodeWithTag("manual-menu-row-menu-exact").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            assertEquals(discount, r.preview("fixture-bar", now)!!.visibleMenu.single()
                .options.single().discount)
        }
    }

    @Test fun editingFirstThreeImportedOptionsKeepsFourthOptionIntact() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        r.saveBrand(MockBrand("brand-import", "라가불린"))
        r.saveCatalogProduct(MockCatalogProduct("prod-import", "brand-import", "라가불린 10년"))
        val four = (1..4).map { i ->
            MockMenuOption("import-$i", pourMl = 15 * i, priceKrw = 1000 * i)
        }
        r.saveMenuItem(MockBarMenuItem("menu-import", "fixture-bar", "prod-import", four))
        val vm = OwnerMockViewModel(r)
        compose.setContent {
            MaterialTheme {
                OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
            }
        }
        compose.onNodeWithTag("manual-menu-row-menu-import").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            assertEquals(four, r.preview("fixture-bar", 0)!!.visibleMenu.single().options)
        }
    }

    @Test fun soldOutConfirmationRemovesCustomerOnlyAndKeepsOwnerMenu() {
        val vm = fixture()
        compose.setContent {
            MaterialTheme {
                OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
            }
        }
        compose.onNodeWithTag("manual-menu-row-bar-10").performClick()
        compose.onNodeWithTag("manual-menu-row-stock").performClick()
        compose.onNodeWithText("상태 변경").performClick()
        compose.runOnIdle {
            assertEquals(0, vm.preview("fixture-bar", 0L)!!.visibleMenu.size)
            val state = vm.state.value as MockOwnerLoadState.Ready
            assertEquals(1, state.snapshot.menuItems.size)
            assertEquals(true, state.snapshot.menuItems.single().soldOut)
        }
        compose.onNodeWithText("품절", substring = true).assertExists()
    }
    @Test fun importedLocalizedBottleAndHighPriceRemainUnchangedAfterSaving() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        r.saveBrand(MockBrand("brand-local", "라가불린"))
        r.saveCatalogProduct(MockCatalogProduct("product-local", "brand-local", "라가불린 12년"))
        val original = listOf(
            MockMenuOption("bottle-ko", label = "병", pourMl = null, priceKrw = 100_000_000),
            MockMenuOption("glass-ko", label = "잔", pourMl = 30, priceKrw = 20_000),
            MockMenuOption("other", label = null, pourMl = null, priceKrw = 12_000))
        r.saveMenuItem(MockBarMenuItem("menu-local", "fixture-bar", "product-local", original))
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-row-menu-local").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            assertEquals(original, r.preview("fixture-bar", 0)!!.visibleMenu.single().options)
        }
    }

    @Test fun categoryToggleDoesNotDestroyWhiskyOptions() {
        val vm = fixture()
        val initial = vm.preview("fixture-bar", 0)!!.visibleMenu.single().options
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-row-bar-10").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithText("위스키", substring = false).performClick()
        compose.onNodeWithText("칵테일", substring = false).performClick()
        compose.onNodeWithText("칵테일", substring = false).performClick()
        compose.onNodeWithText("위스키", substring = false).performClick()
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            assertEquals(initial, vm.preview("fixture-bar", 0)!!.visibleMenu.single().options)
        }
    }

    @Test fun otherCatalogCategoriesAreVisibleAndSearchableInOwnerMenu() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        for (cat in listOf("gin", "brandy", "rum", "wine")) {
            r.saveBrand(MockBrand("brand-$cat", cat))
            r.saveCatalogProduct(MockCatalogProduct("product-$cat", "brand-$cat",
                "상품 $cat", category = cat))
            r.saveMenuItem(MockBarMenuItem("menu-$cat", "fixture-bar", "product-$cat",
                listOf(MockMenuOption("option-$cat", label = "병", priceKrw = 22000))))
        }
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        for (cat in listOf("gin", "brandy", "rum", "wine")) {
            compose.onNodeWithText(cat, substring = false).performScrollTo().performClick()
            compose.onNodeWithTag("manual-menu-row-menu-$cat").assertExists()
        }
        compose.runOnIdle { assertEquals(4, vm.preview("fixture-bar", 0)!!.visibleMenu.size) }
    }

    @Test fun activeImportAllowsViewingButBlocksDirectActions() {
        val original = MockBarMenuItem("listed", "fixture-bar", "prod-a",
            listOf(MockMenuOption("pour-a", pourMl = 30, priceKrw = 13000)))
        val base = OwnerMockFixtures.registeredBar().copy(
            brands = listOf(MockBrand("brand-a", "브랜드")),
            products = listOf(MockCatalogProduct("prod-a", "brand-a", "상품 A")),
            menuItems = listOf(original),
            imports = listOf(MockMenuImport("job-1", "fixture-bar",
                MockImportStatus.READY_FOR_REVIEW, 1, emptyList())))
        val store = InMemoryMockOwnerStateStore(base)
        val r = LocalOwnerMockRepository(store)
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithText("추가할 메뉴 확인하기").assertExists()
        compose.onNodeWithTag("manual-menu-add").performClick()
        compose.onNodeWithText("메뉴 직접 추가").assertDoesNotExist()
        compose.onNodeWithTag("manual-menu-row-listed").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithText("메뉴 수정").assertDoesNotExist()
        compose.onNodeWithTag("manual-menu-reset").performScrollTo().performClick()
        compose.onNodeWithText("전체 메뉴를 초기화할까요?").assertDoesNotExist()
        compose.runOnIdle { assertEquals(original, r.preview("fixture-bar", 0)!!.visibleMenu.single()) }
    }

}
