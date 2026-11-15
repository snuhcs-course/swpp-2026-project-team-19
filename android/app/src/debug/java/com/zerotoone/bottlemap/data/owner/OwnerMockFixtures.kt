package com.zerotoone.bottlemap.data.owner

/** Explicit fixtures: initial installation is always Empty, not a fabricated registered bar. */
object OwnerMockFixtures {
    fun empty() = MockOwnerSnapshot()
    fun registeredBar(): MockOwnerSnapshot {
        val bar = MockBar(barId = "fixture-bar", name = "테스트 매장", address = "테스트 주소")
        return MockOwnerSnapshot(bars = listOf(bar), selectedBarId = bar.barId)
    }
    fun imageFixtures(byUri: Map<String, List<MockExtractedLine>>): MockPhotoExtractionSource =
        MockPhotoExtractionSource { uri -> byUri[uri].orEmpty() }
}
