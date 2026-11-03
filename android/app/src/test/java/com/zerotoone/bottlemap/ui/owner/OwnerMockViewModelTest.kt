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
    @Test fun ownerFlow5SavesSharedGalleryTagsBasicInfoAndHoursAcrossRestart() {
        val store = InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar())
        val vm = OwnerMockViewModel(LocalOwnerMockRepository(store))
        val original = (vm.state.value as MockOwnerLoadState.Ready).snapshot.bars.single()
        val first = com.zerotoone.bottlemap.data.owner.MockPhoto(
            "cover", "content://bar/first", com.zerotoone.bottlemap.data.owner.MockPhotoKind.BAR_GALLERY)
        val second = first.copy(photoId = "second", uri = "content://bar/second")
        val hours = listOf(com.zerotoone.bottlemap.data.owner.MockWeeklyHours(
            5, closed = false, openMinutes = 19 * 60,
            closeMinutes = 2 * 60, closesNextDay = true))
        vm.saveBar(original.copy(name = "바뀐 매장", description = "한 줄 소개",
            phone = "02-1234-5678", defaultPourMl = 45,
            gallery = listOf(second, first), tags = listOf("칵테일", "위스키"),
            weeklyHours = hours))
        val reloaded = OwnerMockViewModel(LocalOwnerMockRepository(store))
        val preview = reloaded.preview("fixture-bar", 0)!!.bar
        assertEquals("바뀐 매장", preview.name)
        assertEquals("한 줄 소개", preview.description)
        assertEquals(45, preview.defaultPourMl)
        assertEquals(listOf("second", "cover"), preview.gallery.map { it.photoId })
        assertEquals(listOf("칵테일", "위스키"), preview.tags)
        assertEquals(hours, preview.weeklyHours)
    }

    @Test fun failedWriteDoesNotPublishUnsavedBarState() {
        val baseline = OwnerMockFixtures.registeredBar()
        val store = object : com.zerotoone.bottlemap.data.owner.MockOwnerStateStore {
            override fun read() = baseline
            override fun write(snapshot: com.zerotoone.bottlemap.data.owner.MockOwnerSnapshot) {
                throw IllegalStateException("Simulated disk failure")
            }
        }
        val vm = OwnerMockViewModel(LocalOwnerMockRepository(store))
        var rejected = false
        try {
            vm.saveBar((vm.state.value as MockOwnerLoadState.Ready)
                .snapshot.bars.single().copy(name = "실패한 저장"))
        } catch (_: IllegalStateException) {
            rejected = true
        }
        assertTrue(rejected)
        assertEquals("fixture-bar",
            (vm.state.value as MockOwnerLoadState.Ready).snapshot.bars.single().barId)
        assertTrue((vm.state.value as MockOwnerLoadState.Ready).snapshot
            .bars.single().name != "실패한 저장")
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

    @Test fun vmUsesInjectedRepositoryForExistingBarOwnershipFixture() {
        val store = InMemoryMockOwnerStateStore()
        val repository = LocalOwnerMockRepository(store)
        val vm = OwnerMockViewModel(repository)
        vm.seedExistingCandidateForFixture(
            MockBar("candidate-bar", "Mock Candidate", "Mock Address")
        )
        vm.saveRegistrationDraft(com.zerotoone.bottlemap.data.owner.MockRegistrationDraft(
            kind = com.zerotoone.bottlemap.data.owner.MockApplicationKind.EXISTING_BAR,
            existingBarId = "candidate-bar"
        ))
        val id = vm.submitRegistrationDraftForFixture()
        val staged = when(val s=vm.state.value) {
            is MockOwnerLoadState.Ready -> s.snapshot
            else -> error("Expected ready")
        }
        assertTrue(staged.bars.isEmpty())
        vm.approveForFixture(id, staged.existingBarCandidates.single())
        val confirmed = when(val s=OwnerMockViewModel(LocalOwnerMockRepository(store)).state.value) {
            is MockOwnerLoadState.Ready -> s.snapshot
            else -> error("Expected ready")
        }
        assertEquals("candidate-bar", confirmed.bars.single().barId)
    }
}
