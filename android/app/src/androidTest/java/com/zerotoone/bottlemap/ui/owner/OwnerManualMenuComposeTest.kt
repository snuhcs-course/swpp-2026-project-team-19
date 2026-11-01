package com.zerotoone.bottlemap.ui.owner

import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.test.assertDoesNotExist
import androidx.compose.ui.test.assertExists
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
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
}
