package com.zerotoone.bottlemap.ui.owner

import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.zerotoone.bottlemap.data.owner.*
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class OwnerPhotoStage7ComposeTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Test fun emptySelectionDisablesAnalysisAndShowsFifteenImageCap() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerMenuPhotoSelectionScreen(vm.state.collectAsState().value, vm, {}, {})
        } }
        compose.onNodeWithTag("stage7-photo-submit").assertIsNotEnabled()
        compose.onNodeWithTag("stage7-photo-add").assertExists()
        compose.onNodeWithText("메뉴판 사진 선택").assertExists()
        compose.onNodeWithText("사진을 최대 15장까지 올릴 수 있어요.").assertExists()
        compose.onNodeWithText("사진 0장 올리기").assertExists()
        compose.onNodeWithText("JPEG/PNG · 사진당 10MB · 전체 60MB").assertDoesNotExist()
        compose.onNodeWithText("새 메뉴만 추가 · 기존 메뉴와 가격 유지").assertDoesNotExist()
    }


    @Test fun failedImportMatchesActionFirstV4ErrorCopyWithoutExtraDiagnostics() {
        val repository = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val importId = repository.queuePhotoImport("fixture-bar", listOf(
            MockPhoto("photo-failed", "file:///mock/bad.jpg", MockPhotoKind.MENU_CAPTURE)))
        repository.finishPhotoImport(importId, MockPhotoExtractionSource { emptyList() })
        val vm = OwnerMockViewModel(repository)
        compose.setContent { MaterialTheme {
            OwnerMenuPhotoJobScreen(vm.state.collectAsState().value, vm, {}, {})
        } }
        compose.onNodeWithTag("stage7-failed-icon").assertExists()
        compose.onNodeWithText("메뉴판을 읽지 못했어요").assertExists()
        compose.onNodeWithText(
            "사진 분석을 완료하지 못했어요.\n메뉴판을 화면에 꽉 채우고, 흔들리지 않게 다시 찍어주세요."
        ).assertExists()
        compose.onNodeWithText("📷 사진 다시 올리기").assertExists()
        compose.onNodeWithText("AI 인식 실패").assertDoesNotExist()
    }

    @Test fun readyImportRemainsUnpublishedAndCanBeCanceledFromJobScreen() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val importId = r.queuePhotoImport("fixture-bar", listOf(
            MockPhoto("photo-1", "file:///mock/A.jpg", MockPhotoKind.MENU_CAPTURE)))
        r.finishPhotoImport(importId, MockPhotoExtractionSource { listOf(
            MockExtractedLine("line-1", "A whisky 12", MockLineKind.PRODUCT,
                options = listOf(MockMenuOption("opt", pourMl = 30, priceKrw = 17000)))
        ) })
        val vm = OwnerMockViewModel(r)
        compose.setContent { MaterialTheme {
            OwnerMenuPhotoJobScreen(vm.state.collectAsState().value, vm, {}, {})
        } }
        compose.onNodeWithText("메뉴 확인 준비").assertExists()
        compose.onNodeWithText("메뉴 등록 작업 취소").performClick()
        compose.onNodeWithText("작업 취소").performClick()
        compose.runOnIdle {
            val state = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals(MockImportStatus.CANCELED, state.imports.single().status)
            assertEquals(0, state.menuItems.size)
            assertFalse(state.imports.single().images.single().lines.isEmpty())
        }
    }
}
