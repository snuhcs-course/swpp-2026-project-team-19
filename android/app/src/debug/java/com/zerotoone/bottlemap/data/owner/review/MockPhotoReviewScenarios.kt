package com.zerotoone.bottlemap.data.owner.review

import com.zerotoone.bottlemap.ui.owner.review.MergedLine
import com.zerotoone.bottlemap.ui.owner.review.OperatorReason
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import com.zerotoone.bottlemap.ui.owner.review.PriceChoice
import com.zerotoone.bottlemap.ui.owner.review.RecognizedOffer
import com.zerotoone.bottlemap.ui.owner.review.ReviewItem
import com.zerotoone.bottlemap.ui.owner.review.ReviewItemType
import com.zerotoone.bottlemap.ui.owner.review.ReviewMatch
import com.zerotoone.bottlemap.ui.owner.review.ReviewOption
import com.zerotoone.bottlemap.ui.owner.review.VolumeSource
import com.zerotoone.bottlemap.data.owner.review.MockPhotoReviewRepository.Companion.product

/**
 * MOCK ONLY. The review scenarios of BottleMap_Minimal_UX_v18.html (sidebar of flow 02),
 * each as the review state it starts from. Developers pick one with
 * `adb shell am start ... --es bm_ux_review <id>` in a debug build, and the Compose tests
 * use them directly. The app UI has no scenario picker.
 */
enum class MockPhotoReviewScenario(val id: String, val title: String, val focusItemId: String?) {
    BASIC("basic", "기본 검수 · 확인할 메뉴 5개", null),
    MULTI_ISSUE("multi-issue", "상품 + 가격 동시 검수", "hakushu"),
    AMBIGUOUS("ambiguous", "메뉴 확인 · 맞아요/아니에요", "hakushu"),
    MANUAL_NAME("manual-name", "새 메뉴명 수정 · X / 저장", "bookers"),
    CANDIDATES("candidates", "여러 후보 · 선택 후 확인", "arran"),
    CATALOG_FOUND("catalog-found", "카탈로그 검색 · 선택 후 확인", "hakushu"),
    CATALOG_EMPTY("catalog-empty", "검색 결과 없음 · 새로 등록", "hakushu"),
    SOURCE_NO_BOX("source-no-box", "사진 위치 정보 없음", "arran"),
    LINKED_NAME("linked-name", "메뉴 이름 수정 · 자동 매칭", "glen12"),
    NEW("new", "새 위스키 · 확인/수정", "bookers"),
    UNLINKED("unlinked", "미매칭 · 매장 메뉴만 게시", "bookers"),
    RENAMED_MATCH("renamed-match", "이름 변경 · 운영자 재확인", "glen12"),
    EDITION_CONFLICT("edition-conflict", "에디션 불일치 · 운영자 확인", "arran"),
    MERGED_LINES("merged-lines", "같은 위스키 병합 · 여러 줄", "glen12"),
    MERGED_CONFLICT("merged-conflict", "같은 용량 · 서로 다른 가격", "glen12"),
    ZERO_OPTION("zero-option", "옵션 0개 · 가격 입력", "glen15"),
    BAD_INPUTS("bad-inputs", "숫자 입력 검증", "glen12"),
    RECLASSIFY("reclassify", "분류 변경 · 옵션 보존", "glen12"),
    MISSING_PRICE("missing-price", "가격 누락", "glen15"),
    DEFAULT_POUR("default-pour", "매장 기본 용량 적용", "glen12"),
    NO_DEFAULT("no-default", "매장 기본 용량 없음", "glen12"),
    WHISKY_OPTIONS("whisky-options", "위스키 용량별 가격", "glen12"),
    OTHER("other", "그 외 메뉴 · 가격만", "gin"),
    OTHER_TYPO("other-typo", "그 외 메뉴 · 이름 검수", "gin"),
    OTHER_PRICE("other-price", "그 외 메뉴 · 가격 누락", "gin"),
    EXCLUDE("exclude", "게시 제외 · 복원", "ardbeg"),
    DRAFT("draft", "나중에 하기 → 메뉴 관리", null),
    READY("ready", "모든 검수 완료", null);

    fun initialState(): PhotoReviewState {
        val base = PhotoReviewState(items = seedItems())
        return when (this) {
            BASIC, AMBIGUOUS, CANDIDATES, LINKED_NAME, NEW, UNLINKED, MISSING_PRICE, DEFAULT_POUR, DRAFT -> base
            MULTI_ISSUE -> base.edit("hakushu") { it.copy(price = 0.0) }
            MANUAL_NAME -> base.edit("bookers") { it.copy(reviewNameDraft = null, nameSaved = false, nameEditMode = true) }
            CATALOG_FOUND -> base.edit("hakushu") {
                it.copy(searchMode = true, searchDraft = "하쿠슈 12",
                    searchResults = MockPhotoReviewRepository.searchMockCatalog("하쿠슈 12"))
            }
            CATALOG_EMPTY -> base.edit("hakushu") {
                it.copy(searchMode = true, searchDraft = "하쿠슈 XX 시음", searchResults = emptyList())
            }
            SOURCE_NO_BOX -> base.edit("arran") { it.copy(hasSourceBox = false, photoIndex = 4) }
            RENAMED_MATCH -> base.edit("glen12") {
                it.copy(name = "글렌피딕 15", nameSaved = true, operatorPending = true,
                    operatorReason = OperatorReason.CHANGED, linkedProductId = "gf15", linkedProductName = "글렌피딕 15년")
            }
            EDITION_CONFLICT -> base.edit("arran") { it.copy(selectedCandidateId = "arran-port") }
            MERGED_LINES -> base.edit("glen12", ::mergedLine)
            MERGED_CONFLICT -> base.edit("glen12") {
                mergedLine(it).copy(
                    options = emptyList(),
                    mergeSources = listOf(MergedLine(2, "글렌피딕 12", "GLENFIDDICH 12 30ml 14,000",
                        listOf(RecognizedOffer(volumeMl = 30, priceKrw = 14000)))),
                    conflictPrices = listOf(12000.0, 14000.0),
                    conflictChoice = null,
                )
            }
            ZERO_OPTION -> base.edit("glen15") {
                it.copy(primaryHasOption = false, price = 0.0, volume = 0.0, recognizedOffers = emptyList(),
                    raw = "GLENFIDDICH 15 (가격 없음)")
            }
            BAD_INPUTS -> base.edit("glen12") { it.copy(volume = 22.5) }
            RECLASSIFY -> base.edit("glen12") { it.copy(options = listOf(ReviewOption(45.0, 18000.0))) }
            NO_DEFAULT -> base.copy(defaultPour = 0.0, items = base.items.map {
                if (it.volumeSource == VolumeSource.DEFAULT) it.copy(volume = 0.0) else it
            })
            WHISKY_OPTIONS -> base.edit("glen12") {
                it.copy(
                    options = listOf(ReviewOption(45.0, 18000.0), ReviewOption(0.0, 210000.0, bottle = true)),
                    raw = "GLENFIDDICH 12 · 30ml 12,000 / 45ml 18,000 / Bottle 210,000",
                    recognizedOffers = listOf(RecognizedOffer(30, priceKrw = 12000), RecognizedOffer(45, priceKrw = 18000),
                        RecognizedOffer(bottle = true, priceKrw = 210000)),
                )
            }
            OTHER -> base.copy(show = base.show.copy(other = true))
            OTHER_TYPO -> base.edit("gin") { it.copy(typo = true, nameConfirmed = false, nameSaved = false) }
                .let { it.copy(show = it.show.copy(other = true)) }
            OTHER_PRICE -> base.edit("gin") { it.copy(price = 0.0) }
            EXCLUDE -> base.edit("ardbeg") { it.copy(excluded = true) }
            READY -> base.copy(items = base.items.map { resolveAll(it, base.defaultPour) })
        }
    }

    companion object {
        fun fromId(id: String?): MockPhotoReviewScenario? = entries.firstOrNull { it.id == id }

        /** The ten lines of the v18 fixture photo set. */
        fun seedItems(): List<ReviewItem> = listOf(
            ReviewItem(id = "glendronach", name = "글렌드로낙 12", price = 15000.0, oldPrice = 12000.0,
                photoPrice = 15000.0, linkedProductId = "gld12", linkedProductName = "글렌드로낙 12년",
                raw = "GLENDRONACH 12     15,000", photoIndex = 1, required = true),
            ReviewItem(id = "hakushu", name = "하쿠슈 DR", price = 19000.0, match = ReviewMatch.AMBIGUOUS,
                matchConfirmed = false, candidates = listOf(product("hakushu-dr")),
                raw = "HAKUSHU DR     19,000", photoIndex = 1, required = true),
            ReviewItem(id = "arran", name = "아란 셰리 캐스크", price = 17000.0, match = ReviewMatch.CANDIDATE,
                matchConfirmed = false, candidates = listOf(product("arran-sherry"), product("arran-port")),
                raw = "ARRAN SHERRY CASK     17,000", photoIndex = 2, required = true),
            ReviewItem(id = "bookers", name = "부커스 25.1E", price = 30000.0, match = ReviewMatch.NEW,
                newConfirmed = false, newProductName = "부커스 25.1E",
                raw = "BOOKERS 25.1E     30,000", photoIndex = 2, required = true),
            ReviewItem(id = "glen15", name = "글렌피딕 15", price = 0.0, linkedProductId = "gf15",
                linkedProductName = "글렌피딕 15년", raw = "GLENFIDDICH 15     [금액 없음]", photoIndex = 3,
                required = true),
            ReviewItem(id = "ardbeg", name = "아드벡 10", price = 15000.0, linkedProductId = "ard10",
                linkedProductName = "아드벡 10년", raw = "ARDBEG 10     15,000", photoIndex = 3),
            ReviewItem(id = "glen12", name = "글렌피딕 12", price = 12000.0, volume = 30.0,
                volumeSource = VolumeSource.DEFAULT, linkedProductId = "gf12", linkedProductName = "글렌피딕 12년",
                raw = "GLENFIDDICH 12     12,000", photoIndex = 3),
            otherItem("gin", "진토닉", 12000.0, "GIN TONIC     12,000"),
            otherItem("highball", "하이볼", 10000.0, "HIGHBALL     10,000"),
            otherItem("cola", "콜라", 4000.0, "COKE     4,000"),
        )

        private fun otherItem(id: String, name: String, price: Double, raw: String) = ReviewItem(
            id = id, name = name, type = ReviewItemType.OTHER, match = ReviewMatch.NONE, price = price,
            volume = Double.NaN, raw = raw,
        )

        private fun mergedLine(x: ReviewItem) = x.copy(
            options = listOf(ReviewOption(0.0, 180000.0, bottle = true)),
            mergeSources = listOf(MergedLine(2, "글렌피딕 12", "GLENFIDDICH 12 BOTTLE 180,000",
                listOf(RecognizedOffer(bottle = true, priceKrw = 180000)))),
            recognizedOffers = listOf(RecognizedOffer(volumeMl = 30, priceKrw = 12000)),
            expanded = false,
        )

        /** The prototype's "모든 검수 완료" fixture: every open decision answered. */
        private fun resolveAll(x: ReviewItem, defaultPour: Double): ReviewItem {
            if (x.excluded) return x
            var y = x
            if (y.type == ReviewItemType.WHISKY) {
                if (y.match == ReviewMatch.AMBIGUOUS || y.match == ReviewMatch.CANDIDATE) y = y.copy(matchConfirmed = true)
                if (y.match == ReviewMatch.NEW) y = y.copy(newConfirmed = true)
                y = y.copy(nameSaved = true)
                if (y.oldPrice != null && y.photoPrice != null && y.oldPrice != y.photoPrice &&
                    y.priceChoice == PriceChoice.NONE
                ) y = y.copy(priceChoice = PriceChoice.PHOTO, price = y.photoPrice!!)
                if (y.conflictPrices.isNotEmpty() && y.conflictChoice == null) {
                    y = y.copy(conflictChoice = y.conflictPrices[0], price = y.conflictPrices[0])
                }
                if (!y.bottle && !(y.volume > 0)) y = y.copy(volume = if (defaultPour > 0) defaultPour else 30.0)
                y = y.copy(options = y.options.map { o ->
                    o.copy(volume = if (!o.bottle && !(o.volume > 0)) 45.0 else o.volume,
                        price = if (!(o.price > 0)) 18000.0 else o.price)
                })
            }
            if (!(y.price > 0)) y = y.copy(price = 15000.0)
            return y.copy(nameConfirmed = true)
        }

        private fun PhotoReviewState.edit(id: String, change: (ReviewItem) -> ReviewItem) =
            copy(items = items.map { if (it.id == id) change(it) else it })
    }
}
