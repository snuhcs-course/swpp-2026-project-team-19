package com.zerotoone.bottlemap.ui.owner

import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.longClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.zerotoone.bottlemap.data.owner.*
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


    @Test fun nextPreviousAlwaysUseNewAndPriceScreensAndNeverDeadEndInCandidateUI() {
        val list=listOf(
            MockExtractedLine("hakushu","하쿠슈DR",MockLineKind.PRODUCT,
                suggestedProductId="demo-canonical",
                options=listOf(MockMenuOption("h1",label="잔",pourMl=30,priceKrw=19000))),
            MockExtractedLine("signatory","시그나토리 쿨일라13",MockLineKind.PRODUCT,
                options=listOf(MockMenuOption("s1",label="잔",pourMl=30,priceKrw=20000))),
            MockExtractedLine("bookers","부커스",MockLineKind.PRODUCT,
                suggestedProductId="demo-canonical",
                options=listOf(MockMenuOption("b1",label="잔",priceKrw=0))),
            MockExtractedLine("lagavulin","라가불린 16년",MockLineKind.PRODUCT,
                suggestedProductId="demo-canonical",
                options=listOf(MockMenuOption("l1",label="잔",pourMl=30,priceKrw=22000)))
        )
        showLines(list)
        compose.onNodeWithText("이 메뉴가 맞나요?").assertExists()
        compose.onNodeWithText("‹ 이전").assertDoesNotExist()
        compose.onNodeWithText("다음 ›").performClick()
        compose.onNodeWithText("새로 등록할게요").assertExists()
        compose.onNodeWithText("이 메뉴가 맞나요?").assertDoesNotExist()
        compose.onNodeWithText("다음 ›").performClick()
        compose.onNodeWithText("가격을 못 읽었어요").assertExists()
        compose.onNodeWithText("이 메뉴가 맞나요?").assertDoesNotExist()
        compose.onNodeWithText("‹ 이전").performClick()
        compose.onNodeWithText("새로 등록할게요").assertExists()
        compose.onNodeWithText("‹ 이전").performClick()
        compose.onNodeWithText("이 메뉴가 맞나요?").assertExists()
        compose.onNodeWithText("‹ 이전").assertDoesNotExist()
    }

    @Test fun allReviewTypesHaveCompactTopExclusionAndCatalogDoesNot() {
        showLine(MockExtractedLine("raw", "하쿠슈DR", MockLineKind.PRODUCT,
            suggestedProductId="demo-canonical",
            options=listOf(MockMenuOption("o",label="잔",pourMl=30,priceKrw=19000))))
        compose.onNodeWithText("이번 줄 제외").assertExists()
        compose.onNodeWithText("다른 메뉴예요").performClick()
        compose.onNodeWithText("이번 줄 제외").assertDoesNotExist()
    }

    @Test fun singleReviewPageHidesBothPreviousAndNext() {
        showLine(MockExtractedLine("single","하쿠슈DR",MockLineKind.PRODUCT,
            suggestedProductId="demo-canonical",
            options=listOf(MockMenuOption("one",label="잔",pourMl=30,priceKrw=19000))))
        compose.onNodeWithText("‹ 이전").assertDoesNotExist()
        compose.onNodeWithText("다음 ›").assertDoesNotExist()
    }

    @Test fun finalReviewPageHidesNextButRetainsPrevious() {
        showLines(listOf(
            MockExtractedLine("one","하쿠슈DR",MockLineKind.PRODUCT,
                suggestedProductId="demo-canonical",
                options=listOf(MockMenuOption("o1",label="잔",pourMl=30,priceKrw=19000))),
            MockExtractedLine("two","러셀",MockLineKind.PRODUCT,
                candidateProductIds=listOf("demo-canonical"),
                options=listOf(MockMenuOption("o2",label="잔",pourMl=30,priceKrw=15000)))
        ))
        compose.onNodeWithText("다음 ›").performClick()
        compose.onNodeWithText("‹ 이전").assertExists()
        compose.onNodeWithText("다음 ›").assertDoesNotExist()
    }

}
