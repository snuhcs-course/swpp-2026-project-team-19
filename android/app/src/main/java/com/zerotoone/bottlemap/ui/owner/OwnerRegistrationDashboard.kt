package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.zerotoone.bottlemap.data.owner.*
import com.zerotoone.bottlemap.ui.common.*

/** ACTION_FIRST v4: approved bars and active applications share the same management list. */
@Composable
internal fun OwnerRegistrationDashboard(
    snapshot: MockOwnerSnapshot,
    debug: Boolean,
    onRegister: () -> Unit,
    onManage: (MockBar) -> Unit,
    onViewApplication: (String) -> Unit,
    onCancel: (String) -> Unit,
    onDismiss: (String) -> Unit,
    onReapply: (MockOwnerApplication) -> Unit,
    onReject: (String) -> Unit,
    onApprove: (MockOwnerApplication) -> Unit,
) {
    val bars = snapshot.bars
    val applications = snapshot.applications
        .filterNot { it.applicationId in snapshot.dismissedApplicationIds }
        .filterNot { it.status == MockApplicationStatus.APPROVED && bars.any { bar -> bar.barId == it.barId } }

    if (bars.isEmpty() && applications.isEmpty()) {
        Text("매장 등록은\n이렇게 진행돼요", style = MaterialTheme.typography.headlineSmall)
        Text("사업자 정보 확인, 매장 정보 입력, 메뉴판 사진, 운영팀 승인 순서예요.",
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text("중간에 멈춰도 입력한 내용은 기기에 남아 있어요.")
        OwnerActionButton("시작하기", onRegister, Modifier.fillMaxWidth())
        return
    }

    if (bars.isNotEmpty()) {
        Text("내 매장", style = MaterialTheme.typography.titleMedium)
        bars.forEach { bar ->
            Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface,
                RoundedCornerShape(16.dp)).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(bar.name, style = MaterialTheme.typography.titleLarge)
                // Same persisted bar exception and weekly schedule as management home.
                val now = System.currentTimeMillis()
                val temporary = homeOperatingException(bar, now)
                // Match the home-card headline; keep current open/closed as separate detail.
                val operatingLabel = if (temporary?.kind == MockExceptionKind.VACATION)
                    "임시 휴무" else homeExceptionHeading(temporary)
                OwnerStatusLabel(operatingLabel,
                    if (temporary != null) OwnerStatusTone.ATTENTION else OwnerStatusTone.SUCCESS)
                if (bar.weeklyHours.isNotEmpty()) {
                    Text(homeOperatingState(bar, now), style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (!snapshot.hasPublishedInitialReview(bar.barId)) {
                    OwnerStatusLabel("메뉴 확인 필요", OwnerStatusTone.ATTENTION)
                }
                Text(bar.address, style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                OwnerActionButton("매장 관리하기", { onManage(bar) }, Modifier.fillMaxWidth())
            }
        }
    }
    if (applications.isNotEmpty()) {
        Text("신청", style = MaterialTheme.typography.titleMedium)
        applications.forEach { application ->
            Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface,
                RoundedCornerShape(16.dp)).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(application.proposedBarName, style = MaterialTheme.typography.titleLarge)
                OwnerStatusLabel(when(application.status) {
                    MockApplicationStatus.PENDING -> "검토 중"
                    MockApplicationStatus.APPROVED -> "승인됨"
                    MockApplicationStatus.REJECTED -> "승인되지 않음"
                    MockApplicationStatus.CANCELED -> "취소됨"
                }, if(application.status==MockApplicationStatus.REJECTED) OwnerStatusTone.ERROR
                    else OwnerStatusTone.ATTENTION)
                when(application.status) {
                    MockApplicationStatus.PENDING -> {
                        Text("신청 완료  ·  운영팀 확인 중  ·  승인 대기",
                            style = MaterialTheme.typography.bodySmall)
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            TextButton(onClick={onViewApplication(application.applicationId)}) {
                                Text("신청 내용 보기")
                            }
                            TextButton(onClick={onCancel(application.applicationId)}) {
                                Text("신청 취소")
                            }
                        }
                        if(debug) {
                            Text("운영팀 Fixture · Mock 전용", style = MaterialTheme.typography.labelSmall)
                            Row {
                                TextButton(onClick={onReject(application.applicationId)}) { Text("거절") }
                                TextButton(onClick={onApprove(application)}) { Text("승인") }
                            }
                        }
                    }
                    MockApplicationStatus.REJECTED -> {
                        Text(application.rejectionReason ?: "Mock 심사 거절 사유 없음")
                        Row {
                            TextButton(onClick={onReapply(application)}) { Text("다시 신청하기") }
                            TextButton(onClick={onDismiss(application.applicationId)}) { Text("목록에서 지우기") }
                        }
                    }
                    MockApplicationStatus.CANCELED ->
                        Text("신청이 취소되었습니다. 다른 매장을 다시 등록할 수 있어요.")
                    MockApplicationStatus.APPROVED ->
                        Text("승인된 매장의 메뉴 확인이 필요합니다.")
                }
            }
        }
    }
    OwnerActionButton("다른 매장 등록하기", onRegister, Modifier.fillMaxWidth(), secondary=true)
}
