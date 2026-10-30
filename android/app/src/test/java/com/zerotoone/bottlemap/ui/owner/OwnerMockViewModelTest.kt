package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.InMemoryMockOwnerStateStore
import com.zerotoone.bottlemap.data.owner.LocalOwnerMockRepository
import com.zerotoone.bottlemap.data.owner.MockBar
import com.zerotoone.bottlemap.data.owner.MockOwnerLoadState
import com.zerotoone.bottlemap.data.owner.OwnerMockFixtures
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
}
