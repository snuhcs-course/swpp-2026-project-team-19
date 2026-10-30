package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.zerotoone.bottlemap.data.owner.MockOwnerLoadState
import com.zerotoone.bottlemap.navigation.OwnerFlowGroup
import com.zerotoone.bottlemap.navigation.OwnerPage
import com.zerotoone.bottlemap.ui.common.OwnerActionButton
import com.zerotoone.bottlemap.ui.common.OwnerCalendarDialog
import com.zerotoone.bottlemap.ui.common.OwnerConfirmationDialog
import com.zerotoone.bottlemap.ui.common.OwnerHeader
import com.zerotoone.bottlemap.ui.common.OwnerLoading
import com.zerotoone.bottlemap.ui.common.OwnerMenuRow
import com.zerotoone.bottlemap.ui.common.OwnerPhotoThumbnail
import com.zerotoone.bottlemap.ui.common.OwnerStatusLabel
import com.zerotoone.bottlemap.ui.common.OwnerStatusTone
import com.zerotoone.bottlemap.ui.common.OwnerTextInput
import com.zerotoone.bottlemap.ui.common.OwnerTimeWheel
import com.zerotoone.bottlemap.ui.theme.BottleMapSpacing

/**
 * Navigation-only shells. Nothing here reads/writes a bar or simulates successful API calls.
 * The UI must visibly state that it is incomplete, even when the user enters from My Page.
 */
@Composable
fun OwnerEntryScreen(
    mockState: MockOwnerLoadState,
    onRetry: () -> Unit,
    onBack: () -> Unit,
    onOpenGroup: (OwnerFlowGroup) -> Unit,
    onComponents: () -> Unit,
    onOpenLegacyUpload: (() -> Unit)? = null, // Only supplied for Debug navigation
) {
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        OwnerHeader("매장 사장님", onBack)
        Column(
            modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(BottleMapSpacing.screenHorizontal),
            verticalArrangement = Arrangement.spacedBy(BottleMapSpacing.md),
        ) {
            OwnerStatusLabel("화면 연결 단계 · 실제 기능 미완성", OwnerStatusTone.ATTENTION)
            OwnerMockStateLine(mockState, onRetry)
            Text("Owner 화면 구조 미리보기", style = MaterialTheme.typography.headlineSmall)
            Text(
                "현재는 화면 이동과 공통 컴포넌트만 연결되어 있습니다. 매장 조회, 신청, 저장, OCR, AI 검수, 게시는 동작하지 않습니다.",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            OwnerFlowGroup.entries.forEach { group ->
                OwnerMenuRow(
                    title = group.title,
                    subtitle = "화면 흐름만 확인하기 · 데이터 미연결",
                    onClick = { onOpenGroup(group) },
                    trailing = "보기",
                )
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            }
            OwnerMenuRow(
                title = "UI 컴포넌트 점검",
                subtitle = "버튼, 입력, 팝업, 시간·날짜, 썸네일, 로딩",
                onClick = onComponents,
                trailing = "보기",
            )
            if (onOpenLegacyUpload != null) {
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                OwnerMenuRow(
                    title = "개발자 도구 · 기존 메뉴 업로드 테스트",
                    subtitle = "Debug 전용 · 임시 Operator 인증의 과거 통합 테스트 화면",
                    onClick = onOpenLegacyUpload,
                    trailing = "테스트",
                )
            }
        }
    }
}

@Composable
fun OwnerSkeletonScreen(
    page: OwnerPage,
    mockState: MockOwnerLoadState,
    onRetry: () -> Unit,
    onBack: () -> Unit,
    onNavigate: (OwnerPage) -> Unit,
    onHome: () -> Unit,
) {
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        OwnerHeader(page.title, onBack)
        Column(
            modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(BottleMapSpacing.screenHorizontal),
            verticalArrangement = Arrangement.spacedBy(BottleMapSpacing.md),
        ) {
            OwnerStatusLabel("미구현 · 이동 골격만 제공", OwnerStatusTone.ATTENTION)
            OwnerMockStateLine(mockState, onRetry)
            Text(page.group.title, style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.primary)
            Text(page.title, style = MaterialTheme.typography.headlineSmall)
            Text(
                "최종 HTML 화면 (${page.htmlId})의 구성과 상태 로직은 아직 연결되지 않았습니다. " +
                    "이 화면에서 입력·사진 선택·서버 저장·AI 처리·게시는 실행되지 않습니다.",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (page == OwnerPage.MGR_HOME) {
                Text("매장 관리 하위 화면 (Navigation 미리보기)", style = MaterialTheme.typography.titleLarge)
                listOf(
                    OwnerPage.MGR_INFO, OwnerPage.MGR_STATUS, OwnerPage.MGR_PHOTOS,
                    OwnerPage.MGR_MENU, OwnerPage.MGR_PHOTO, OwnerPage.MGR_PREVIEW,
                ).forEach { destination ->
                    OwnerMenuRow(destination.title, "아직 기능 미구현", onClick = { onNavigate(destination) })
                }
            }
            if (page == OwnerPage.MGR_INFO) {
                listOf(OwnerPage.MGR_PHOTOS, OwnerPage.MGR_HOURS, OwnerPage.MGR_TAGS).forEach { destination ->
                    OwnerMenuRow(destination.title, "아직 기능 미구현", onClick = { onNavigate(destination) })
                }
            }
            if (page == OwnerPage.MGR_MENU) {
                listOf(OwnerPage.MGR_ITEM, OwnerPage.MGR_PROMO, OwnerPage.MGR_PHOTO).forEach { destination ->
                    OwnerMenuRow(destination.title, "아직 기능 미구현", onClick = { onNavigate(destination) })
                }
            }
            page.next()?.let { next ->
                OwnerActionButton("다음 화면: ${next.title}", onClick = { onNavigate(next) }, modifier = Modifier.fillMaxWidth())
            }
            OwnerActionButton("Owner 화면 목록으로", onClick = onHome, secondary = true, modifier = Modifier.fillMaxWidth())
        }
    }
}

/** A stateful component showcase; all state is local to this design QA surface only. */
@Composable
fun OwnerComponentGallery(onBack: () -> Unit) {
    var name by rememberSaveable { mutableStateOf("") }
    var hour by rememberSaveable { mutableIntStateOf(18) }
    var minute by rememberSaveable { mutableIntStateOf(0) }
    var showConfirm by rememberSaveable { mutableStateOf(false) }
    var showCalendar by rememberSaveable { mutableStateOf(false) }
    var showLoading by rememberSaveable { mutableStateOf(false) }
    var thumbnailVisible by rememberSaveable { mutableStateOf(true) }
    var dateMillis by rememberSaveable { mutableLongStateOf(0L) }

    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        OwnerHeader("공통 컴포넌트", onBack)
        Column(
            modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(BottleMapSpacing.screenHorizontal),
            verticalArrangement = Arrangement.spacedBy(BottleMapSpacing.md),
        ) {
            OwnerStatusLabel("UI 테스트 전용 · 서버 저장 없음", OwnerStatusTone.ATTENTION)
            OwnerTextInput("매장 이름 (예시 입력)", value = name, onValueChange = { name = it })
            OwnerMenuRow("메뉴 항목", "기본 행 컴포넌트 (서버 데이터 없음)", onClick = { showConfirm = true }, trailing = "선택")
            Row(horizontalArrangement = Arrangement.spacedBy(BottleMapSpacing.xs)) {
                OwnerStatusLabel("준비", OwnerStatusTone.NEUTRAL)
                OwnerStatusLabel("완료", OwnerStatusTone.SUCCESS)
                OwnerStatusLabel("오류", OwnerStatusTone.ERROR)
            }
            OwnerActionButton("기본 버튼", onClick = { showConfirm = true }, modifier = Modifier.fillMaxWidth())
            OwnerActionButton("보조 버튼", onClick = { showCalendar = true },
                secondary = true, modifier = Modifier.fillMaxWidth())
            Text("시간 선택 (스크롤 가능)", style = MaterialTheme.typography.titleMedium)
            Text("%02d:%02d".format(hour, minute), style = MaterialTheme.typography.titleLarge)
            OwnerTimeWheel(hour = hour, minute = minute, onTimeChange = { h, m -> hour = h; minute = m })
            Text("사진 썸네일 (이미지 미연결)", style = MaterialTheme.typography.titleMedium)
            if (thumbnailVisible) {
                OwnerPhotoThumbnail(contentDescription = "예시 사진 자리", painter = null,
                    onRemove = { thumbnailVisible = false })
            } else {
                OwnerActionButton("썸네일 되돌리기", onClick = { thumbnailVisible = true }, secondary = true)
            }
            Text("날짜: " + if (dateMillis == 0L) "미선택" else dateMillis.toString(),
                style = MaterialTheme.typography.bodyMedium)
            TextButton(onClick = { showLoading = !showLoading }) {
                Text(if (showLoading) "로딩 예시 숨기기" else "로딩 예시 보기")
            }
            if (showLoading) OwnerLoading("화면 로딩 예시 · 실제 작업 아님")
        }
    }
    OwnerCalendarDialog(
        visible = showCalendar, onDismiss = { showCalendar = false },
        onSelectDateUtcMillis = { dateMillis = it },
    )
    OwnerConfirmationDialog(
        visible = showConfirm,
        title = "확인 팝업 예시",
        message = "디자인 검증용이며 실제 변경 사항은 저장하지 않습니다.",
        confirmLabel = "확인",
        onConfirm = { showConfirm = false },
        onDismiss = { showConfirm = false },
    )
}

/** Minimal debug readout; all Owner shells observe the same persisted repository. */
@Composable
private fun OwnerMockStateLine(state: MockOwnerLoadState, onRetry: (() -> Unit)? = null) {
    when (state) {
        MockOwnerLoadState.Loading -> OwnerLoading("로컬 Mock 상태 불러오는 중")
        is MockOwnerLoadState.Empty -> Text(
            "Mock 데이터: 매장 0개 · 메뉴 0개 (초기 상태)",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        is MockOwnerLoadState.Ready -> Text(
            "Mock 데이터: 매장 ${state.snapshot.bars.size}개 · 메뉴 ${state.snapshot.menuItems.size}개",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        is MockOwnerLoadState.Error -> {
            Text("Mock 데이터 오류: ${state.message}", color = MaterialTheme.colorScheme.error)
            if (onRetry != null) OwnerActionButton("다시 시도", onRetry, secondary = true)
        }
    }
}
