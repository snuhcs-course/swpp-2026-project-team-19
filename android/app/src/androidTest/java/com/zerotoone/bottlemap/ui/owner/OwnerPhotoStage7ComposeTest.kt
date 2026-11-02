package com.zerotoone.bottlemap.ui.owner

import androidx.activity.ComponentActivity
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.longClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.zerotoone.bottlemap.data.owner.*
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
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
        compose.onNodeWithText("메뉴판 순서대로 올려주세요.").assertExists()
        compose.onNodeWithText("한 장에 한 면씩, 글자와 가격이 잘리지 않게").assertExists()
        compose.onNodeWithText("빛 반사 없이 정면에서").assertExists()
        compose.onNodeWithText("JPEG/PNG · 사진당 10MB · 전체 60MB").assertDoesNotExist()
        compose.onNodeWithText("새 메뉴만 추가 · 기존 메뉴와 가격 유지").assertDoesNotExist()
    }


    @Test fun photoAddOffersGalleryOrCameraAndCancelLeavesSelectionUnchanged() {
        val repository=LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val vm=OwnerMockViewModel(repository)
        compose.setContent { MaterialTheme {
            OwnerMenuPhotoSelectionScreen(vm.state.collectAsState().value,vm,{}, {})
        } }
        compose.onNodeWithTag("stage7-photo-add").performClick()
        compose.onNodeWithText("사진을 어떻게 추가할까요?").assertExists()
        compose.onNodeWithTag("stage7-source-gallery").assertExists()
        compose.onNodeWithTag("stage7-source-camera").assertExists()
        compose.onNodeWithText("카메라").assertExists()
        compose.onNodeWithText("갤러리").assertExists()
        compose.onNodeWithText("취소").assertDoesNotExist()
        // The source chooser itself must not change the photos or enable upload.
        compose.onNodeWithText("사진 0장 올리기").assertExists()
        compose.onNodeWithTag("stage7-photo-submit").assertIsNotEnabled()
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
        compose.onNodeWithText("사진 다시 올리기").assertExists()
        compose.onNodeWithTag("stage7-retry-camera-icon", useUnmergedTree = true).assertExists()
        compose.onNodeWithText("AI 인식 실패").assertDoesNotExist()
    }

    @Test fun debugLongPressDemoKeepsPdfFailureScreenFreeOfExtraButtons() {
        val repository = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val importId = repository.queuePhotoImport("fixture-bar",listOf(
            MockPhoto("demo-photo","file:///mock/demo.jpg",MockPhotoKind.MENU_CAPTURE)))
        repository.finishPhotoImport(importId,MockPhotoExtractionSource { emptyList() })
        val vm=OwnerMockViewModel(repository)
        var opened=false
        compose.setContent { MaterialTheme {
            OwnerMenuPhotoJobScreen(vm.state.collectAsState().value,vm,
                onHome={},onRetryPhotos={},onReview={opened=true})
        } }
        compose.onNodeWithText("[개발용] 샘플 결과로 검수 체험").assertDoesNotExist()
        compose.onNodeWithText("메뉴판을 읽지 못했어요").performTouchInput { longClick() }
        compose.runOnIdle {
            assertTrue(opened)
            val snap=(vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals(MockImportStatus.READY_FOR_REVIEW,snap.imports.last().status)
            assertEquals(5,snap.imports.last().images.single().lines.size)
        }
    }

    @Test fun readyImportImmediatelyRoutesToReviewWithoutIntermediaryPage() {
        val r = LocalOwnerMockRepository(
            InMemoryMockOwnerStateStore(OwnerMockFixtures.registeredBar()))
        val importId = r.queuePhotoImport("fixture-bar", listOf(
            MockPhoto("photo-1", "file:///mock/A.jpg", MockPhotoKind.MENU_CAPTURE)))
        r.finishPhotoImport(importId, MockPhotoExtractionSource { listOf(
            MockExtractedLine("line-1", "A whisky 12", MockLineKind.PRODUCT,
                options = listOf(MockMenuOption("opt", pourMl = 30, priceKrw = 17000)))
        ) })
        val vm = OwnerMockViewModel(r)
        var opened=false
        compose.setContent { MaterialTheme {
            OwnerMenuPhotoJobScreen(vm.state.collectAsState().value, vm, {}, {},
                onReview={opened=true})
        } }
        compose.onNodeWithText("메뉴 확인 준비").assertDoesNotExist()
        compose.onNodeWithText("메뉴 등록 작업 취소").assertDoesNotExist()
        compose.waitForIdle()
        compose.runOnIdle {
            assertTrue(opened)
            val state = (vm.state.value as MockOwnerLoadState.Ready).snapshot
            assertEquals(MockImportStatus.READY_FOR_REVIEW, state.imports.single().status)
            assertEquals(0, state.menuItems.size)
        }
    }

}
