package com.zerotoone.bottlemap.ui.owner

import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.longClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.zerotoone.bottlemap.data.owner.*
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class OwnerPhotoStage8ComposeTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    private fun showLine(line: MockExtractedLine) = showLines(listOf(line))
    private fun showLines(lines: List<MockExtractedLine>) {
        val repository = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        repository.saveBrand(MockBrand("demo-brand", "Suntory"))
        repository.saveCatalogProduct(
            MockCatalogProduct("demo-canonical", "demo-brand",
                "Hakushu Distiller's Reserve"))
        val importId = repository.queuePhotoImport("fixture-bar",
            listOf(MockPhoto("p1", "file:///mock/p1.png", MockPhotoKind.MENU_CAPTURE)))
        repository.finishPhotoImport(importId, MockPhotoExtractionSource { lines })
        val vm = OwnerMockViewModel(repository)
        compose.setContent { MaterialTheme {
            OwnerPhotoStage8Screen(vm.state.collectAsState().value,vm,{}, {})
        } }
        compose.onNodeWithText("${lines.size}줄 확인 시작").performClick()
    }

    @Test fun pdf87MatchingCandidateRecordsDecisionWithoutExtraOptionPage() {
        showLine(MockExtractedLine("raw", "하쿠슈DR", MockLineKind.PRODUCT,
            suggestedProductId="demo-canonical",
            options=listOf(MockMenuOption("o",label="잔",pourMl=30,priceKrw=19000))))
        compose.onNodeWithText("이 메뉴가 맞나요?").assertExists()
        compose.onNodeWithText("원본 사진 보기").assertExists()
        compose.onNodeWithText("위스키가 아니에요").assertExists()
        compose.onNodeWithText("다른 메뉴예요").assertExists()
        compose.onNodeWithText("맞아요").performClick()
        compose.onNodeWithText("메뉴 게시").assertExists()
    }

    @Test fun pdf89NewProductFormHasDistilleryAgeAndNamePreview() {
        showLine(MockExtractedLine("raw", "시그나토리 쿨일라13", MockLineKind.PRODUCT,
            options=listOf(MockMenuOption("o",label="잔",pourMl=30,priceKrw=20000))))
        compose.onNodeWithText("새로 등록할게요").assertExists()
        compose.onNodeWithText("병입사").assertExists()
        compose.onNodeWithText("증류소").assertExists()
        compose.onNodeWithText("숙성 연수").assertExists()
        compose.onNodeWithText("시리즈 (선택)").assertExists()
        compose.onNodeWithText("등록될 이름").assertExists()
    }
    @Test fun pdf91CatalogSearchHasCountAndFixedNewProductEntry() {
        showLine(MockExtractedLine("new", "알려지지 않은 위스키", MockLineKind.PRODUCT,
            suggestedProductId="demo-canonical",
            options=listOf(MockMenuOption("o",label="잔",pourMl=30,priceKrw=20000))))
        compose.onNodeWithText("다른 메뉴예요").performClick()
        compose.onNodeWithText("카탈로그에서 찾은 메뉴 0개").assertExists()
        compose.onNodeWithText("찾는 메뉴가 없어요, 새로 등록").performClick()
        compose.onNodeWithText("새로 등록할게요").assertExists()
    }

    @Test fun pdf90MissingPriceCanBeReviewedWithoutInventingPrice() {
        showLine(MockExtractedLine("bookers", "부커스", MockLineKind.PRODUCT,
            suggestedProductId="demo-canonical",
            options=listOf(MockMenuOption("o",label="30ml",pourMl=30,priceKrw=0))))
        compose.onNodeWithText("가격을 못 읽었어요").assertExists()
        compose.onNodeWithText("저장").assertExists()
        compose.onNodeWithText("이번 줄 제외").assertExists()
    }

    @Test fun pdf92PartialReviewAllowsResumeWithoutPublishing() {
        showLine(MockExtractedLine("raw", "위스키 미확인", MockLineKind.PRODUCT,
            options=listOf(MockMenuOption("o",label="잔",pourMl=30,priceKrw=14000))))
        compose.onNodeWithText("←").performClick()
        compose.onNodeWithText("1줄 확인").performTouchInput {longClick()}
        compose.onNodeWithText("1줄 남았어요").assertExists()
        compose.onNodeWithText("1줄 이어서 확인").assertExists()
    }


    @Test fun squareHomeIconAlignsWithSourceLabelBaseline() {
        showLine(MockExtractedLine("home-line","하쿠슈DR",MockLineKind.PRODUCT,
            suggestedProductId="demo-canonical",
            options=listOf(MockMenuOption("home-option",label="잔",pourMl=30,priceKrw=19000))))
        val home=compose.onNodeWithTag("stage8-review-home").getUnclippedBoundsInRoot()
        val label=compose.onNodeWithTag("stage8-source-line-label").getUnclippedBoundsInRoot()
        assert(kotlin.math.abs(home.width.value-home.height.value)<1f)
        assert(kotlin.math.abs(home.bottom.value-label.bottom.value)<4f)
    }

    @Test fun reviewScreenHasNoManualPagingFooterAndUsesHeaderHome() {
        showLines(listOf(
            MockExtractedLine("hakushu","하쿠슈DR",MockLineKind.PRODUCT,
                suggestedProductId="demo-canonical",
                options=listOf(MockMenuOption("h1",label="잔",pourMl=30,priceKrw=19000))),
            MockExtractedLine("signatory","시그나토리",MockLineKind.PRODUCT,
                options=listOf(MockMenuOption("s1",label="잔",pourMl=30,priceKrw=20000)))
        ))
        compose.onNodeWithText("이 메뉴가 맞나요?").assertExists()
        compose.onNodeWithTag("stage8-review-home").assertExists()
        compose.onNodeWithText("나중에 하기").assertDoesNotExist()
        compose.onNodeWithText("‹ 이전").assertDoesNotExist()
        compose.onNodeWithText("다음 ›").assertDoesNotExist()
        compose.onNodeWithText("맞아요").assertExists()
        compose.onNodeWithText("다른 메뉴예요").assertExists()
    }

    @Test fun allReviewTypesHaveCompactTopExclusionAndCatalogDoesNot() {
        showLine(MockExtractedLine("raw", "하쿠슈DR", MockLineKind.PRODUCT,
            suggestedProductId="demo-canonical",
            options=listOf(MockMenuOption("o",label="잔",pourMl=30,priceKrw=19000))))
        compose.onNodeWithText("이번 줄 제외").assertExists()
        compose.onNodeWithText("다른 메뉴예요").performClick()
        compose.onNodeWithText("이번 줄 제외").assertDoesNotExist()
    }

    @Test fun priceAndNewReviewPagesOfferHeaderHomeWithoutPaging() {
        showLine(MockExtractedLine("new-product","시그나토리",MockLineKind.PRODUCT,
            options=listOf(MockMenuOption("o",label="잔",pourMl=30,priceKrw=19000))))
        compose.onNodeWithText("새로 등록할게요").assertExists()
        compose.onNodeWithTag("stage8-review-home").assertExists()
        compose.onNodeWithText("다음 ›").assertDoesNotExist()
        compose.onNodeWithText("‹ 이전").assertDoesNotExist()
    }

    @Test fun summaryAlwaysOpensFirstUnreviewedHakushuRatherThanSecondLine() {
        showLines(listOf(
            MockExtractedLine("h","하쿠슈DR",MockLineKind.PRODUCT,
                suggestedProductId="demo-canonical",
                options=listOf(MockMenuOption("h1",label="잔",pourMl=30,priceKrw=19000))),
            MockExtractedLine("s","시그나토리 쿨일라 13",MockLineKind.PRODUCT,
                options=listOf(MockMenuOption("s1",label="잔",pourMl=30,priceKrw=20000)))
        ))
        compose.onNodeWithText("하쿠슈DR",substring=true).assertExists()
        compose.onNodeWithText("이 메뉴가 맞나요?").assertExists()
        compose.onNodeWithText("새로 등록할게요").assertDoesNotExist()
    }

    @Test fun headerHomeReturnsWithoutDecidingCurrentLine() {
        val repository=LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        repository.saveBrand(MockBrand("b","브랜드"))
        repository.saveCatalogProduct(MockCatalogProduct("p","b","첫 상품"))
        val id=repository.queuePhotoImport("fixture-bar",listOf(
            MockPhoto("ph","file:///mock/ph.jpg",MockPhotoKind.MENU_CAPTURE)))
        repository.finishPhotoImport(id,MockPhotoExtractionSource {listOf(
            MockExtractedLine("line","첫 상품",MockLineKind.PRODUCT,
                suggestedProductId="p",options=listOf(
                    MockMenuOption("o",label="잔",pourMl=30,priceKrw=19000)))
        )})
        val vm=OwnerMockViewModel(repository)
        var later=false
        compose.setContent{MaterialTheme {
            OwnerPhotoStage8Screen(vm.state.collectAsState().value,vm,{}, {later=true})
        }}
        compose.onNodeWithText("1줄 확인 시작").performClick()
        compose.onNodeWithTag("stage8-review-home").performClick()
        compose.runOnIdle {
            assert(later)
            val snap=(vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals(null,snap.imports.last().images.single().lines.single().decision)
        }
    }

}
