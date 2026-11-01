package com.zerotoone.bottlemap.ui.owner

import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.test.assertDoesNotExist
import androidx.compose.ui.test.assertExists
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.zerotoone.bottlemap.data.owner.*
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class OwnerOtherAlcoholCategoryComposeTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    private fun fixture(): LocalOwnerMockRepository {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        r.saveBrand(MockBrand("other-brand", "기타 브랜드"))
        for ((id, name, kind) in listOf(
            Triple("beer-a", "수제 에일", "맥주"),
            Triple("beer-b", "수제 라거", "맥주"),
            Triple("sake-a", "준마이 사케", "사케")
        )) {
            r.saveCatalogProduct(MockCatalogProduct(id, "other-brand", name,
                category = "otherAlcohol", otherAlcoholKind = kind))
            r.saveMenuItem(MockBarMenuItem("bar-$id", "fixture-bar", id,
                listOf(MockMenuOption("option-$id", priceKrw = 14000))))
        }
        return r
    }

    @Test fun ownerGroupsBeerTogetherAndSakeSeparately() {
        val r = fixture()
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerManualMenuScreen(vm.state.collectAsState().value, vm, {}, {}, {})
        } }
        compose.onNodeWithText("맥주", substring = false).assertExists()
        compose.onNodeWithText("사케", substring = false).assertExists()
        compose.onNodeWithText("기타 주류", substring = false).assertDoesNotExist()
        compose.runOnIdle {
            assertEquals(3, (vm.state.value as MockOwnerLoadState.Ready).snapshot.menuItems.size)
        }
    }

    @Test fun customerPreviewUsesTheSameSubtypeGroupLabels() {
        val r = fixture()
        val snapshot = (r.state.value as MockOwnerLoadState.Ready).snapshot
        compose.setContent { MaterialTheme {
            OwnerPreviewV4Menu(snapshot.bars.single(),
                r.preview("fixture-bar", 0L), snapshot.brands, nowEpochMs = 0L)
        } }
        compose.onNodeWithText("맥주", substring = false).assertExists()
        compose.onNodeWithText("사케", substring = false).assertExists()
        compose.onNodeWithText("기타 주류", substring = false).assertDoesNotExist()
    }
}
