package com.zerotoone.bottlemap.ui.owner

import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.mutableLongStateOf
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
import androidx.compose.ui.test.performTextReplacement
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

    @Test fun importedNullableServingKeepsItsIdentityWhenApplyingExistingDiscount() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        r.saveBrand(MockBrand("nullable-brand", "브랜드"))
        r.saveCatalogProduct(MockCatalogProduct("nullable-product", "nullable-brand", "상품"))
        val original = MockMenuOption("nullable-option", label = null, pourMl = null,
            priceKrw = 20000, discount = MockDiscount(17000, 1000L, 100000L))
        r.saveMenuItem(MockBarMenuItem("nullable-row", "fixture-bar",
            "nullable-product", listOf(original)))
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-row-nullable-row").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithText("할인").performClick()
        compose.onNodeWithTag("manual-menu-promo-apply").performScrollTo().performClick()
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            assertEquals(original, r.preview("fixture-bar", 0L)!!.visibleMenu.single()
                .options.single())
        }
    }

    @Test fun unchangedLongCatalogMenuNameCanBeSavedWithoutTruncation() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val longName = "라".repeat(120)
        r.saveBrand(MockBrand("long-brand", "브랜드"))
        r.saveCatalogProduct(MockCatalogProduct("long-product", "long-brand", longName))
        val original = MockBarMenuItem("long-row", "fixture-bar", "long-product",
            listOf(MockMenuOption("long-option", pourMl = 30, priceKrw = 11000)))
        r.saveMenuItem(original)
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-row-long-row").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            assertEquals(original, r.preview("fixture-bar", 0L)!!.visibleMenu.single())
        }
    }

    @Test fun highPricedImportedDiscountRemainsUntouchedOnUnrelatedMenuEdit() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        r.saveBrand(MockBrand("high-brand", "브랜드"))
        r.saveCatalogProduct(MockCatalogProduct("high-product", "high-brand", "상품"))
        val original = MockMenuOption("high-option", pourMl = 30,
            priceKrw = 150_000_000,
            discount = MockDiscount(120_000_000, 1000L, 100000L))
        r.saveMenuItem(MockBarMenuItem("high-row", "fixture-bar",
            "high-product", listOf(original)))
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-row-high-row").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            assertEquals(original, r.preview("fixture-bar", 0L)!!.visibleMenu.single()
                .options.single())
        }
    }

    @Test fun existingOtherAlcoholWithoutSubtypeCanSaveUnrelatedNameAndPriceEdit() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val product = MockCatalogProduct("product-other", "brand-other", "수제 주류",
            category = "otherAlcohol", otherAlcoholKind = null)
        val original = MockMenuOption("other-option", label = "병", pourMl = null,
            priceKrw = 18000)
        r.saveBrand(MockBrand("brand-other", "기타 브랜드"))
        r.saveCatalogProduct(product)
        r.saveMenuItem(MockBarMenuItem("menu-other", "fixture-bar", product.productId,
            listOf(original)))
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithText("기타 주류", substring = false).performScrollTo().performClick()
        compose.onNodeWithTag("manual-menu-row-menu-other").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithTag("manual-menu-name").performTextReplacement("수제 주류 수정")
        compose.onNodeWithTag("manual-menu-price-0").performScrollTo()
            .performTextReplacement("19000")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            val snap = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals(null, snap.products.single().otherAlcoholKind)
            assertEquals("otherAlcohol", snap.products.single().category)
            assertEquals("병", snap.menuItems.single().options.single().label)
            assertEquals(19000, snap.menuItems.single().options.single().priceKrw)
            assertEquals("수제 주류 수정", snap.menuItems.single().displayNameOverride)
        }
    }

    @Test fun uncheckingImportedBottleRequiresPourAndDoesNotOverwriteOriginal() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        r.saveBrand(MockBrand("bottle-brand", "브랜드"))
        r.saveCatalogProduct(MockCatalogProduct("bottle-product", "bottle-brand", "병 상품"))
        val saved = MockMenuOption("bottle-original", label = "병", pourMl = null, priceKrw = 22000)
        r.saveMenuItem(MockBarMenuItem("bottle-row", "fixture-bar", "bottle-product", listOf(saved)))
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-row-bottle-row").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithText("Bottle 판매").performScrollTo().performClick()
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.onNodeWithText("용량을 입력하거나 Bottle 판매를 선택해 주세요.").assertExists()
        compose.runOnIdle {
            assertEquals(saved, vm.preview("fixture-bar", 0L)!!.visibleMenu.single().options.single())
        }
        compose.onNodeWithTag("manual-menu-ml-0").performScrollTo().performTextReplacement("45")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            val savedOption = vm.preview("fixture-bar", 0L)!!.visibleMenu.single().options.single()
            assertEquals("bottle-original", savedOption.optionId)
            assertEquals(45, savedOption.pourMl)
            assertEquals(null, savedOption.label)
        }
    }

    @Test fun localWhiskyToCocktailClearsHiddenWhiskyPour() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val product = MockCatalogProduct("local-unverified-whisky", "local-brand-type",
            "시음 위스키", category = "whisky", catalogMatched = false)
        r.saveManualMenuItem(MockBarMenuItem("local-type-row", "fixture-bar",
            product.productId, listOf(MockMenuOption("one-serving", pourMl = 30, priceKrw = 11000))),
            product, MockBrand(product.brandId, "브랜드"))
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-row-local-type-row").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithText("위스키", substring = false).performClick()
        compose.onNodeWithText("칵테일", substring = false).performClick()
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            val snap = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals("cocktail", snap.products.single().category)
            assertEquals(null, snap.menuItems.single().options.single().pourMl)
            assertEquals(null, snap.menuItems.single().options.single().label)
            assertEquals("one-serving", snap.menuItems.single().options.single().optionId)
        }
    }

    @Test fun exactDigitlessCatalogItemIsExplicitlyConfirmedInsteadOfDuplicated() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        r.saveBrand(MockBrand("brand-cocktail", "바 칵테일"))
        r.saveCatalogProduct(MockCatalogProduct("canonical-gin-tonic", "brand-cocktail",
            "진토닉", category = "cocktail"))
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-add").performClick()
        compose.onNodeWithText("위스키", substring = false).performClick()
        compose.onNodeWithText("칵테일", substring = false).performClick()
        compose.onNodeWithTag("manual-menu-name").performTextReplacement("진")
        compose.onNodeWithText("“진토닉”이 맞나요?").assertDoesNotExist()
        compose.onNodeWithTag("manual-menu-name").performTextReplacement("진토닉")
        compose.onNodeWithText("“진토닉”이 맞나요?").assertExists()
        compose.onNodeWithText("맞아요").performClick()
        compose.onNodeWithTag("manual-menu-price-0").performScrollTo().performTextReplacement("14000")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            val snap = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals(1, snap.menuItems.size)
            assertEquals("canonical-gin-tonic", snap.menuItems.single().productId)
            assertEquals(1, snap.products.size)
        }
    }

    @Test fun switchingPromotionOptionDiscardsOnlyUnappliedPriceEdits() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        r.saveBrand(MockBrand("promo-brand", "라가불린"))
        r.saveCatalogProduct(MockCatalogProduct("promo-product", "promo-brand", "위스키 12년"))
        val now = System.currentTimeMillis()
        val start = now - 86_400_000L
        val end = now + 86_400_000L
        val first = MockMenuOption("promo-first", pourMl = 30, priceKrw = 13000,
            discount = MockDiscount(11000, start, end))
        val second = MockMenuOption("promo-second", pourMl = 45, priceKrw = 25000,
            discount = MockDiscount(21000, start, end))
        r.saveMenuItem(MockBarMenuItem("promo-row", "fixture-bar", "promo-product",
            listOf(first, second)))
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-row-promo-row").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithText("할인").performClick()
        // Edit first option but intentionally do not press Apply.
        compose.onNodeWithTag("manual-menu-discount-price").performTextReplacement("8000")
        compose.onNodeWithText("30ml · 13000원").performClick()
        compose.onNodeWithText("45ml · 25000원").performClick()
        compose.onNodeWithTag("manual-menu-discount-price").assertTextEquals("21000")
        compose.onNodeWithTag("manual-menu-discount-price").performTextReplacement("19000")
        compose.onNodeWithTag("manual-menu-promo-apply").performScrollTo().performClick()
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            val saved = vm.preview("fixture-bar", now)!!.visibleMenu.single().options
            assertEquals(first.discount, saved.first().discount)
            assertEquals(19000, saved[1].discount!!.discountedPriceKrw)
            assertEquals(start, saved[1].discount!!.startAtEpochMs)
            assertEquals(end, saved[1].discount!!.endAtEpochMs)
        }
    }

    @Test fun ownerListRefreshesDiscountBadgeAndPriceAtStartAndEndWithoutNavigation() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        r.saveBrand(MockBrand("timed-brand", "브랜드"))
        r.saveCatalogProduct(MockCatalogProduct("timed-product", "timed-brand",
            "시간 위스키", category = "whisky"))
        r.saveMenuItem(MockBarMenuItem("timed-row", "fixture-bar", "timed-product",
            listOf(MockMenuOption("timed-pour", pourMl = 30, priceKrw = 10000,
                discount = MockDiscount(5000, 1_000L, 2_000L)))))
        val vm = OwnerMockViewModel(r)
        val clock = mutableLongStateOf(999L)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {},
                nowEpochMs = clock.longValue)
        } }
        compose.onNodeWithTag("manual-menu-row-timed-row").assertExists()
        compose.onNodeWithText("10,000원").assertExists()
        compose.onNodeWithText("5,000원").assertDoesNotExist()
        compose.runOnIdle { clock.longValue = 1_000L }
        compose.onNodeWithText("5,000원").assertExists()
        compose.onNodeWithText("할인").assertExists()
        compose.runOnIdle { clock.longValue = 2_000L }
        compose.onNodeWithText("10,000원").assertExists()
        compose.onNodeWithText("5,000원").assertDoesNotExist()
        compose.runOnIdle {
            assertEquals(1, vm.preview("fixture-bar", 1_000L)!!.visibleMenu.size)
        }
    }

    @Test fun addingConfirmedLongCatalogNamePreservesCanonicalProductId() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val longName = "한정판 위스키 27년" + " 스페셜 에디션".repeat(12)
        require(longName.length in 81..200)
        r.saveBrand(MockBrand("long-confirmed-brand", "한정판 브랜드"))
        r.saveCatalogProduct(MockCatalogProduct(
            "long-confirmed-product", "long-confirmed-brand", longName,
            category = "whisky"))
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-add").performClick()
        compose.onNodeWithTag("manual-menu-name").performTextInput("한정판 위스키 27년")
        compose.onNodeWithText("맞아요").performClick()
        compose.onNodeWithTag("manual-menu-name").assertTextEquals(longName)
        compose.onNodeWithTag("manual-menu-ml-0").performTextInput("30")
        compose.onNodeWithTag("manual-menu-price-0").performTextInput("29000")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            val snapshot = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals(1, snapshot.menuItems.size)
            assertEquals("long-confirmed-product", snapshot.menuItems.single().productId)
            assertEquals(1, snapshot.products.size)
            assertEquals(longName, snapshot.products.single().displayName)
        }
    }

    @Test fun deletedUnverifiedLocalProductCanBeExplicitlyReaddedWithOriginalMenuId() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val product = MockCatalogProduct("local-unverified-readd", "local-brand-readd",
            "동네 수제 위스키 17년", category = "whisky", catalogMatched = false)
        r.saveManualMenuItem(MockBarMenuItem("stable-readd-row", "fixture-bar",
            product.productId, listOf(MockMenuOption("old-opt", pourMl = 30, priceKrw = 13000))),
            product, MockBrand(product.brandId, "기타 브랜드"))
        r.deleteMenuItem("stable-readd-row")
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-add").performClick()
        compose.onNodeWithTag("manual-menu-name").performTextInput("동네 수제 위스키 17년")
        compose.onNodeWithText("“동네 수제 위스키 17년”이 맞나요?").assertExists()
        compose.onNodeWithText("맞아요").performClick()
        compose.onNodeWithTag("manual-menu-ml-0").performTextInput("45")
        compose.onNodeWithTag("manual-menu-price-0").performTextInput("15000")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            val snap = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals(1, snap.products.size)
            assertEquals(1, snap.brands.size)
            assertEquals("local-unverified-readd", snap.menuItems.single().productId)
            assertEquals("stable-readd-row", snap.menuItems.single().barMenuItemId)
        }
    }

    @Test fun editingSharedLocalMenuNameDoesNotChangeAnotherBarsCatalogProduct() {
        val fixture = OwnerMockFixtures.registeredBar()
        val r = LocalOwnerMockRepository(InMemoryMockOwnerStateStore(fixture.copy(
            bars = fixture.bars + MockBar("other-bar", "다른 바", "서울"))))
        val product = MockCatalogProduct("local-unverified-both", "local-shared-brand",
            "우리 위스키 18년", category = "whisky", catalogMatched = false)
        r.saveManualMenuItem(MockBarMenuItem("shared-own", "fixture-bar", product.productId,
            listOf(MockMenuOption("our-opt", pourMl = 30, priceKrw = 14000))),
            product, MockBrand(product.brandId, "기타 브랜드"))
        r.saveManualMenuItem(MockBarMenuItem("shared-other", "other-bar", product.productId,
            listOf(MockMenuOption("other-opt", pourMl = 30, priceKrw = 16000))))
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-row-shared-own").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithTag("manual-menu-name").performTextReplacement("우리 바 위스키 18년")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            val snap = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals("우리 위스키 18년", snap.products.single().displayName)
            assertEquals("우리 바 위스키 18년",
                snap.menuItems.single { it.barId == "fixture-bar" }.displayNameOverride)
            assertEquals(null,
                snap.menuItems.single { it.barId == "other-bar" }.displayNameOverride)
            assertEquals(16000, r.preview("other-bar", 0L)!!.visibleMenu.single()
                .options.single().priceKrw)
        }
    }

    @Test fun addingTwoUnverifiedWhiskiesReusesOneFallbackBrand() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        for ((name, price) in listOf("작은 수제 위스키 21년" to "13000",
                                   "또 다른 수제 위스키 22년" to "15000")) {
            compose.onNodeWithTag("manual-menu-add").performClick()
            compose.onNodeWithTag("manual-menu-name").performTextReplacement(name)
            compose.onNodeWithTag("manual-menu-ml-0").performTextInput("30")
            compose.onNodeWithTag("manual-menu-price-0").performTextInput(price)
            compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        }
        compose.runOnIdle {
            val snap = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals(2, snap.menuItems.size)
            assertEquals(2, snap.products.size)
            assertEquals(1, snap.brands.size)
            assertEquals("기타 브랜드", snap.brands.single().name)
            assertEquals(1, snap.products.map { it.brandId }.distinct().size)
        }
    }

    @Test fun confirmedOtherAlcoholCatalogSubtypeCannotSilentlyChange() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        r.saveBrand(MockBrand("catalog-kind-brand", "기타 브랜드"))
        val product = MockCatalogProduct("catalog-kind-product", "catalog-kind-brand",
            "정식 리큐르", category = "otherAlcohol", otherAlcoholKind = "리큐르")
        r.saveCatalogProduct(product)
        val original = MockBarMenuItem("catalog-kind-row", "fixture-bar", product.productId,
            listOf(MockMenuOption("catalog-kind-option", label = "병", pourMl = null,
                priceKrw = 24000)))
        r.saveMenuItem(original)
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithText("기타 주류", substring = false).performScrollTo().performClick()
        compose.onNodeWithTag("manual-menu-row-catalog-kind-row").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithTag("manual-menu-alcohol-kind").performTextReplacement("맥주")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.onNodeWithText("카탈로그 상품의 주류 종류는 변경할 수 없어요.").assertExists()
        compose.runOnIdle {
            val snap = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals("리큐르", snap.products.single().otherAlcoholKind)
            assertEquals(original, snap.menuItems.single())
        }
        compose.onNodeWithTag("manual-menu-alcohol-kind").performTextReplacement("리큐르")
        compose.onNodeWithTag("manual-menu-name").performTextReplacement("정식 리큐르 추천")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            val snap = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals("리큐르", snap.products.single().otherAlcoholKind)
            assertEquals("정식 리큐르 추천", snap.menuItems.single().displayNameOverride)
        }
    }

    @Test fun importedKoreanBottleLabelWithPourSurvivesUnrelatedEditButNotPourChange() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        r.saveBrand(MockBrand("poured-bottle-brand", "브랜드"))
        r.saveCatalogProduct(MockCatalogProduct("poured-bottle-product", "poured-bottle-brand",
            "병 위스키 12년", category = "whisky"))
        val option = MockMenuOption("poured-bottle-option", label = "병",
            pourMl = 750, priceKrw = 74000)
        r.saveMenuItem(MockBarMenuItem("poured-bottle-row", "fixture-bar",
            "poured-bottle-product", listOf(option)))
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-row-poured-bottle-row").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithTag("manual-menu-name").performTextReplacement("병 위스키 12년 추천")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            assertEquals(option, vm.preview("fixture-bar", 0L)!!.visibleMenu.single()
                .options.single())
        }
        compose.onNodeWithTag("manual-menu-row-poured-bottle-row").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithTag("manual-menu-ml-0").performScrollTo().performTextReplacement("700")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            val changed = vm.preview("fixture-bar", 0L)!!.visibleMenu.single().options.single()
            assertEquals(option.optionId, changed.optionId)
            assertEquals(700, changed.pourMl)
            assertEquals(null, changed.label)
        }
    }

    @Test fun linkedOtherAlcoholCatalogPrefillsSubtypeAndRejectsMismatchedInput() {
        val repository = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        repository.saveBrand(MockBrand("linked-kind-brand", "기타 브랜드"))
        val product = MockCatalogProduct("linked-kind-product", "linked-kind-brand",
            "공식 리큐르", category = "otherAlcohol", otherAlcoholKind = "리큐르")
        repository.saveCatalogProduct(product)
        val vm = OwnerMockViewModel(repository)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-add").performClick()
        compose.onNodeWithText("위스키", substring = false).performClick()
        compose.onNodeWithText("기타 주류", substring = false).performClick()
        compose.onNodeWithTag("manual-menu-name").performTextReplacement("공식 리큐르")
        compose.onNodeWithText("맞아요").performClick()
        compose.onNodeWithTag("manual-menu-alcohol-kind").assertTextEquals("리큐르")
        compose.onNodeWithTag("manual-menu-price-0").performScrollTo()
            .performTextReplacement("17000")
        compose.onNodeWithTag("manual-menu-alcohol-kind").performTextReplacement("맥주")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.onNodeWithText("카탈로그 상품의 주류 종류는 변경할 수 없어요.").assertExists()
        compose.runOnIdle {
            val state = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals(0, state.menuItems.size)
            assertEquals("리큐르", state.products.single().otherAlcoholKind)
        }
        compose.onNodeWithTag("manual-menu-alcohol-kind").performTextReplacement("리큐르")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            val state = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals("linked-kind-product", state.menuItems.single().productId)
            assertEquals("리큐르", state.products.single().otherAlcoholKind)
            assertEquals(1, state.products.size)
        }
    }

    @Test fun failedStockAndResetWritesShowListErrorAndKeepPublishedMenu() {
        val store = object : MockOwnerStateStore {
            var saved = OwnerMockFixtures.registeredBar()
            var rejectWrites = false
            override fun read(): MockOwnerSnapshot? = saved
            override fun write(snapshot: MockOwnerSnapshot) {
                if (rejectWrites) throw IllegalStateException("테스트 저장 오류")
                saved = snapshot
            }
        }
        val repo = LocalOwnerMockRepository(store)
        repo.saveBrand(MockBrand("failure-brand", "테스트 브랜드"))
        repo.saveCatalogProduct(MockCatalogProduct("failure-product", "failure-brand",
            "실패 검증 위스키", category = "whisky"))
        repo.saveMenuItem(MockBarMenuItem("failure-row", "fixture-bar", "failure-product",
            listOf(MockMenuOption("failure-option", pourMl = 30, priceKrw = 14000))))
        val vm = OwnerMockViewModel(repo)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.runOnIdle { store.rejectWrites = true }
        compose.onNodeWithTag("manual-menu-row-failure-row").performClick()
        compose.onNodeWithTag("manual-menu-row-stock").performClick()
        compose.onNodeWithText("상태 변경").performClick()
        compose.onNodeWithText("테스트 저장 오류").assertExists()
        compose.runOnIdle {
            assertEquals(false, store.saved.menuItems.single().soldOut)
            assertEquals(false, (vm.state.value as MockOwnerLoadState.Ready)
                .snapshot.menuItems.single().soldOut)
        }
        compose.onNodeWithText("취소").performClick()
        compose.onNodeWithTag("manual-menu-reset").performScrollTo().performClick()
        compose.onNodeWithText("초기화", substring = false).performClick()
        compose.onNodeWithText("테스트 저장 오류").assertExists()
        compose.runOnIdle { assertEquals(1, store.saved.menuItems.size) }
        compose.runOnIdle { store.rejectWrites = false }
        compose.onNodeWithText("초기화", substring = false).performClick()
        compose.onNodeWithText("테스트 저장 오류").assertDoesNotExist()
        compose.runOnIdle { assertEquals(0, store.saved.menuItems.size) }
    }

    @Test fun renamedConfirmedCatalogProductKeepsCanonicalIdAndBarDisplayOverride() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val catalog = MockCatalogProduct("catalog-ginger-highball", "catalog-cocktail-brand",
            "진저 하이볼", category = "cocktail")
        r.saveBrand(MockBrand(catalog.brandId, "칵테일 브랜드"))
        r.saveCatalogProduct(catalog)
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-add").performClick()
        compose.onNodeWithText("위스키", substring = false).performClick()
        compose.onNodeWithText("칵테일", substring = false).performClick()
        compose.onNodeWithTag("manual-menu-name").performTextReplacement("진저 하이볼")
        compose.onNodeWithText("“진저 하이볼”이 맞나요?").assertExists()
        compose.onNodeWithText("맞아요").performClick()
        compose.onNodeWithTag("manual-menu-name")
            .performTextReplacement("우리 매장 진저 하이볼")
        compose.onNodeWithTag("manual-menu-price-0").performScrollTo()
            .performTextReplacement("15000")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            val snap = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals(1, snap.products.size)
            assertEquals(catalog.productId, snap.menuItems.single().productId)
            assertEquals("우리 매장 진저 하이볼",
                snap.menuItems.single().displayNameOverride)
            assertEquals("진저 하이볼", snap.products.single().displayName)
            assertEquals(true, snap.products.single().catalogMatched)
            assertEquals(15000, snap.menuItems.single().options.single().priceKrw)
        }
        // Non-whisky categories are collapsed by default after saving.
        compose.onNodeWithText("칵테일", substring = false).performScrollTo().performClick()
        compose.onNodeWithTag("manual-menu-row-" +
            (vm.state.value as MockOwnerLoadState.Ready).snapshot.menuItems.single().barMenuItemId)
            .performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithTag("manual-menu-name")
            .assertTextEquals("우리 매장 진저 하이볼")
    }

    @Test fun activeLocalDuplicateOffersExistingItemAndDoesNotCreateAnotherProduct() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val product = MockCatalogProduct("local-unverified-active-duplicate",
            "active-duplicate-brand", "소규모 위스키 17년",
            category = "whisky", catalogMatched = false)
        r.saveManualMenuItem(MockBarMenuItem("active-duplicate-row", "fixture-bar",
            product.productId, listOf(MockMenuOption("active-duplicate-option",
                pourMl = 30, priceKrw = 12000))),
            product, MockBrand(product.brandId, "기타 브랜드"))
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-add").performClick()
        compose.onNodeWithTag("manual-menu-name")
            .performTextReplacement("소규모 위스키 17년")
        compose.onNodeWithText("“소규모 위스키 17년”이 맞나요?").assertExists()
        // An accidental Save without confirming cannot create a second local ID.
        compose.onNodeWithTag("manual-menu-ml-0").performTextReplacement("45")
        compose.onNodeWithTag("manual-menu-price-0").performTextReplacement("16000")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.onNodeWithText(
            "이미 등록한 상품이에요. 기존 메뉴에서 용량·가격을 수정해 주세요.").assertExists()
        compose.runOnIdle {
            val snap = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals(1, snap.products.size)
            assertEquals(1, snap.menuItems.size)
        }
        compose.onNodeWithText("맞아요").performClick()
        compose.onNodeWithText("기존 메뉴에서 용량·가격 수정").performClick()
        compose.onNodeWithTag("manual-menu-price-0").performScrollTo()
            .performTextReplacement("17000")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            val snap = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals(1, snap.products.size)
            assertEquals(1, snap.menuItems.size)
            assertEquals(product.productId, snap.menuItems.single().productId)
            assertEquals("active-duplicate-row", snap.menuItems.single().barMenuItemId)
            assertEquals(17000, snap.menuItems.single().options.single().priceKrw)
        }
    }

    @Test fun readdingDeletedUnsharedLocalProductPersistsNameAndOtherAlcoholSubtype() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val product = MockCatalogProduct("local-unverified-deleted-subtype",
            "deleted-subtype-brand", "직접 등록한 리큐르",
            category = "otherAlcohol", catalogMatched = false,
            otherAlcoholKind = "리큐르")
        r.saveManualMenuItem(MockBarMenuItem("deleted-subtype-row", "fixture-bar",
            product.productId, listOf(MockMenuOption("original-subtype-option",
                priceKrw = 18000))),
            product, MockBrand(product.brandId, "기타 브랜드"))
        r.deleteMenuItem("deleted-subtype-row")
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-add").performClick()
        compose.onNodeWithText("위스키", substring = false).performClick()
        compose.onNodeWithText("기타 주류", substring = false).performClick()
        compose.onNodeWithTag("manual-menu-name")
            .performTextReplacement("직접 등록한 리큐르")
        compose.onNodeWithText("“직접 등록한 리큐르”이 맞나요?").assertExists()
        compose.onNodeWithText("맞아요").performClick()
        compose.onNodeWithTag("manual-menu-alcohol-kind").assertTextEquals("리큐르")
        compose.onNodeWithTag("manual-menu-name")
            .performTextReplacement("우리 가게 시그니처 리큐르")
        compose.onNodeWithTag("manual-menu-alcohol-kind")
            .performTextReplacement("시그니처 리큐르")
        compose.onNodeWithTag("manual-menu-price-0").performScrollTo()
            .performTextReplacement("21000")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            val snap = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals(1, snap.products.size)
            assertEquals(product.productId, snap.products.single().productId)
            assertEquals("우리 가게 시그니처 리큐르", snap.products.single().displayName)
            assertEquals("시그니처 리큐르", snap.products.single().otherAlcoholKind)
            assertEquals(null, snap.menuItems.single().displayNameOverride)
            assertEquals("deleted-subtype-row", snap.menuItems.single().barMenuItemId)
            assertEquals(21000, snap.menuItems.single().options.single().priceKrw)
        }
        compose.onNodeWithText("기타 주류", substring = false).performScrollTo().performClick()
        compose.onNodeWithTag("manual-menu-row-deleted-subtype-row").performClick()
        compose.onNodeWithTag("manual-menu-row-edit").performClick()
        compose.onNodeWithTag("manual-menu-name")
            .assertTextEquals("우리 가게 시그니처 리큐르")
        compose.onNodeWithTag("manual-menu-alcohol-kind")
            .assertTextEquals("시그니처 리큐르")
    }

    @Test fun readdingDeletedSharedLocalProductOnlyChangesThisBarsDisplayName() {
        val fixture = OwnerMockFixtures.registeredBar()
        val r = LocalOwnerMockRepository(InMemoryMockOwnerStateStore(fixture.copy(
            bars = fixture.bars + MockBar("other-bar", "다른 매장", "서울"))))
        val product = MockCatalogProduct("local-unverified-deleted-shared",
            "deleted-shared-brand", "공유 수제 리큐르",
            category = "otherAlcohol", catalogMatched = false,
            otherAlcoholKind = "리큐르")
        r.saveManualMenuItem(MockBarMenuItem("deleted-shared-row", "fixture-bar",
            product.productId, listOf(MockMenuOption("deleted-shared-option",
                priceKrw = 18000))),
            product, MockBrand(product.brandId, "기타 브랜드"))
        r.saveManualMenuItem(MockBarMenuItem("other-bar-shared-row", "other-bar",
            product.productId, listOf(MockMenuOption("other-bar-shared-option",
                priceKrw = 19000))))
        r.deleteMenuItem("deleted-shared-row")
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithTag("manual-menu-add").performClick()
        compose.onNodeWithText("위스키", substring = false).performClick()
        compose.onNodeWithText("기타 주류", substring = false).performClick()
        compose.onNodeWithTag("manual-menu-name")
            .performTextReplacement("공유 수제 리큐르")
        compose.onNodeWithText("맞아요").performClick()
        compose.onNodeWithTag("manual-menu-name")
            .performTextReplacement("우리 매장 수제 리큐르")
        compose.onNodeWithTag("manual-menu-alcohol-kind")
            .performTextReplacement("다른 종류")
        compose.onNodeWithTag("manual-menu-price-0").performScrollTo()
            .performTextReplacement("20000")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.onNodeWithText("다른 매장에서도 사용하는 상품의 종류는 변경할 수 없어요.")
            .assertExists()
        compose.runOnIdle {
            val snap = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals(1, snap.menuItems.size)
            assertEquals("리큐르", snap.products.single().otherAlcoholKind)
        }
        compose.onNodeWithTag("manual-menu-alcohol-kind")
            .performTextReplacement("리큐르")
        compose.onNodeWithTag("manual-menu-save").performScrollTo().performClick()
        compose.runOnIdle {
            val snap = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals(1, snap.products.size)
            assertEquals("공유 수제 리큐르", snap.products.single().displayName)
            assertEquals("리큐르", snap.products.single().otherAlcoholKind)
            assertEquals("우리 매장 수제 리큐르",
                snap.menuItems.single { it.barId == "fixture-bar" }.displayNameOverride)
            assertEquals(null,
                snap.menuItems.single { it.barId == "other-bar" }.displayNameOverride)
            assertEquals("deleted-shared-row",
                snap.menuItems.single { it.barId == "fixture-bar" }.barMenuItemId)
            assertEquals(19000,
                r.preview("other-bar", 0L)!!.visibleMenu.single().options.single().priceKrw)
        }
    }

}
