package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.InMemoryMockOwnerStateStore
import com.zerotoone.bottlemap.data.owner.LocalOwnerMockRepository
import com.zerotoone.bottlemap.data.owner.MockBar
import com.zerotoone.bottlemap.data.owner.MockOwnerLoadState
import com.zerotoone.bottlemap.data.owner.OwnerMockFixtures
import com.zerotoone.bottlemap.data.owner.MockBrand
import com.zerotoone.bottlemap.data.owner.MockCatalogProduct
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OwnerMockViewModelTest {
    @Test fun injectedRepositorySharesStateWithPreviewAndRestoredInstance() {
        val store = InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())
        val repo = LocalOwnerMockRepository(store)
        val vm = OwnerMockViewModel(repo)
        val initial = vm.state.value as MockOwnerLoadState.Ready
        assertEquals("fixture-bar", initial.snapshot.selectedBarId)
        vm.saveBar(MockBar("fixture-bar", "변경된 매장", "테스트 주소",
            description = "Mock only", tags = listOf("조용한 바", "위스키")))
        assertEquals("변경된 매장", vm.preview("fixture-bar", 0)!!.bar.name)
        val next = OwnerMockViewModel(LocalOwnerMockRepository(store))
        assertEquals("변경된 매장",
            (next.state.value as MockOwnerLoadState.Ready).snapshot.bars.single().name)
        assertTrue(next.preview("fixture-bar", 0)!!.bar.tags.contains("위스키"))
    }
    @Test fun viewModelCanSaveFirstBrandBeforeProductInEmptySnapshot() {
        val repository = LocalOwnerMockRepository(InMemoryMockOwnerStateStore())
        val vm = OwnerMockViewModel(repository)
        assertTrue(vm.state.value is MockOwnerLoadState.Empty)
        vm.saveBrand(MockBrand("brand-a", "Example Brand"))
        vm.saveProduct(MockCatalogProduct("product-a", "brand-a", "Example Product"))
        val snapshot = when (val state = vm.state.value) {
            is MockOwnerLoadState.Empty -> state.snapshot
            is MockOwnerLoadState.Ready -> state.snapshot
            else -> error("Unexpected state")
        }
        assertEquals(1, snapshot.brands.size)
        assertEquals("brand-a", snapshot.products.single().brandId)
        assertTrue(snapshot.bars.isEmpty())
    }
}
