package com.zerotoone.bottlemap.data.owner.review

import com.zerotoone.bottlemap.ui.owner.review.CatalogProduct
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import com.zerotoone.bottlemap.ui.owner.review.ReviewItem
import java.text.Normalizer

/**
 * MOCK ONLY. Serves the BottleMap_Minimal_UX_v18.html review fixtures so every scenario can
 * be reviewed before the API is connected. Nothing here is sent to the server.
 */
class MockPhotoReviewRepository(
    private val scenario: MockPhotoReviewScenario = MockPhotoReviewScenario.BASIC,
) : PhotoReviewRepository {
    /** Last saved draft; the mock keeps it in memory only. */
    var savedDraft: PhotoReviewState? = null
        private set
    var savedDefaultPour: Int? = null
        private set
    var published: PhotoReviewState? = null
        private set

    override suspend fun loadReview(): PhotoReviewState = savedDraft ?: scenario.initialState()

    override suspend fun searchCatalog(query: String): List<CatalogProduct> = searchMockCatalog(query)

    override suspend fun exactMatches(name: String): List<CatalogProduct> {
        val key = norm(name)
        return MOCK_CATALOG.filter { p -> (listOf(p.product.name) + p.aliases).any { norm(it) == key } }
            .map { it.product }
    }

    override suspend fun needsOperatorCheck(item: ReviewItem, product: CatalogProduct): Boolean =
        productConflicts(item.recognizedName.ifBlank { item.name }, product.name)

    override suspend fun saveDefaultPour(ml: Int) {
        savedDefaultPour = ml
    }

    override suspend fun saveDraft(state: PhotoReviewState) {
        savedDraft = state
    }

    override suspend fun publish(state: PhotoReviewState) {
        published = state
        savedDraft = null
    }

    internal data class MockCatalogEntry(val product: CatalogProduct, val aliases: List<String>)

    companion object {
        internal val MOCK_CATALOG = listOf(
            MockCatalogEntry(CatalogProduct("hakushu-dr", "하쿠슈 Distiller’s Reserve"),
                listOf("하쿠슈 DR", "하쿠슈 디스틸러스 리저브", "hakushu dr")),
            MockCatalogEntry(CatalogProduct("hakushu-12", "하쿠슈 12년"), listOf("하쿠슈 12", "Hakushu 12")),
            MockCatalogEntry(CatalogProduct("hakushu-18", "하쿠슈 18년"), listOf("하쿠슈 18", "Hakushu 18")),
            MockCatalogEntry(CatalogProduct("arran-sherry", "아란 셰리 캐스크"), listOf("아란 셰리", "Arran Sherry Cask")),
            MockCatalogEntry(CatalogProduct("arran-port", "아란 포트 캐스크"), listOf("아란 포트", "Arran Port Cask")),
            MockCatalogEntry(CatalogProduct("gld12", "글렌드로낙 12년"), listOf("글렌드로낙 12", "Glendronach 12")),
            MockCatalogEntry(CatalogProduct("gf12", "글렌피딕 12년"), listOf("글렌피딕 12", "Glenfiddich 12")),
            MockCatalogEntry(CatalogProduct("gf15", "글렌피딕 15년"), listOf("글렌피딕 15", "Glenfiddich 15")),
            MockCatalogEntry(CatalogProduct("ard10", "아드벡 10년"), listOf("아드벡 10", "Ardbeg 10")),
            MockCatalogEntry(CatalogProduct("lag16", "라가불린 16년"), listOf("라가불린 16", "Lagavulin 16")),
        )

        fun product(id: String): CatalogProduct = MOCK_CATALOG.first { it.product.productId == id }.product

        internal fun norm(s: String): String =
            Normalizer.normalize(s, Normalizer.Form.NFKC).lowercase().replace(Regex("[’'\\s.\\-]"), "")

        internal fun searchMockCatalog(query: String): List<CatalogProduct> {
            val q = norm(query)
            if (q.isEmpty()) return emptyList()
            return MOCK_CATALOG.filter { p ->
                (listOf(p.product.name) + p.aliases).any { t -> norm(t).contains(q) || q.contains(norm(t)) }
            }.map { it.product }
        }

        /** The prototype's stand-in for the server's age and edition comparison (decision 7). */
        internal fun productConflicts(recognized: String, productName: String): Boolean {
            val raw = recognized.lowercase()
            val target = productName.lowercase()
            fun age(t: String) = Regex("(?:^|\\s)(\\d{1,2})(?:년|\\s*(?:years?|yo|y)\\b)?").find(t)
                ?.groupValues?.get(1)?.toInt()
            fun edition(t: String) = when {
                Regex("셰리|sherry", RegexOption.IGNORE_CASE).containsMatchIn(t) -> "셰리"
                Regex("포트|port", RegexOption.IGNORE_CASE).containsMatchIn(t) -> "포트"
                Regex("distiller.{0,3}s?\\s*reserve|\\bdr\\b", RegexOption.IGNORE_CASE).containsMatchIn(t) -> "DR"
                else -> null
            }
            val ageA = age(raw)
            val ageB = age(target)
            val e1 = edition(raw)
            val e2 = edition(target)
            return (ageA != null && ageA != ageB) || (e1 != null && e1 != e2)
        }
    }
}
