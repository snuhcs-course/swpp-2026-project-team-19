package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zerotoone.bottlemap.data.owner.*
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Approved ACTION_FIRST v4 HTML/PDF pp.21,22,28,29. Pure Mock snapshot display. */
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
    val visible=snapshot.applications.filterNot {
        it.applicationId in snapshot.dismissedApplicationIds
    }.filterNot {
        it.status==MockApplicationStatus.APPROVED &&
            snapshot.bars.any { b -> b.barId==it.barId }
    }
    if(snapshot.bars.isEmpty() && visible.isEmpty()){
        RegistrationIntro()
        Spacer(Modifier.height(16.dp))
        RegistrationButton("시작하기",onClick=onRegister)
        return
    }
    if(snapshot.bars.isNotEmpty()){
        snapshot.bars.forEach { bar ->
            Column(Modifier.fillMaxWidth()
                .background(RegistrationV4.surface,RoundedCornerShape(16.dp))
                .padding(16.dp),verticalArrangement=Arrangement.spacedBy(4.dp)) {
                Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically,
                    horizontalArrangement=Arrangement.spacedBy(8.dp)){
                    Text(bar.name,Modifier.weight(1f),fontSize=16.sp,lineHeight=24.sp,
                        color=RegistrationV4.text,fontWeight=FontWeight.SemiBold)
                    RegistrationDashboardBadge(
                        if(snapshot.hasPublishedInitialReview(bar.barId))"승인됨" else "메뉴 확인 필요",
                        "approved")
                }
                Text(bar.address,color=RegistrationV4.secondary,fontSize=14.sp,lineHeight=21.sp)
                Spacer(Modifier.height(8.dp))
                RegistrationDashboardAction(
                    if(snapshot.hasPublishedInitialReview(bar.barId)) "매장 관리하기"
                    else "메뉴 검수하기",
                    primary=true,onClick={onManage(bar)}
                )
            }
        }
    }
    if(visible.isNotEmpty()){
        visible.forEach { app ->
            Column(Modifier.fillMaxWidth()
                .background(RegistrationV4.surface,RoundedCornerShape(16.dp))
                .padding(16.dp).testTag("registration-dashboard-application"),
                verticalArrangement=Arrangement.spacedBy(4.dp)) {
                Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically,
                    horizontalArrangement=Arrangement.spacedBy(8.dp)){
                    Text(app.proposedBarName,Modifier.weight(1f),color=RegistrationV4.text,
                        fontSize=16.sp,lineHeight=24.sp,fontWeight=FontWeight.SemiBold)
                    val label=when(app.status){
                        MockApplicationStatus.PENDING -> "검토 중"
                        MockApplicationStatus.REJECTED -> "승인되지 않음"
                        MockApplicationStatus.APPROVED -> "승인됨"
                        MockApplicationStatus.CANCELED -> "취소됨"
                    }
                    RegistrationDashboardBadge(label,when(app.status){
                        MockApplicationStatus.REJECTED -> "rejected"
                        MockApplicationStatus.APPROVED -> "approved"
                        else -> "pending"
                    })
                }
                val date=when {
                    app.submittedAtEpochMs>0 ->
                        SimpleDateFormat("M월 d일",Locale.KOREAN).format(Date(app.submittedAtEpochMs))
                    app.status==MockApplicationStatus.REJECTED -> "10월 30일"
                    else -> "10월 28일"
                }
                Text(date + if(app.status==MockApplicationStatus.REJECTED)"에 검토했어요" else
                    "에 신청했어요",color=RegistrationV4.secondary,
                    fontSize=14.sp,lineHeight=21.sp)
                when(app.status){
                    MockApplicationStatus.PENDING -> {
                        Spacer(Modifier.height(12.dp))
                        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)){
                            listOf("신청 완료","운영팀 확인 중","승인").forEachIndexed { i,name ->
                                Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                                    Box(Modifier.fillMaxWidth().height(3.dp)
                                        .background(if(i<2)RegistrationV4.primary
                                            else RegistrationV4.border))
                                    Text(name,color=when(i){
                                        0->RegistrationV4.text;1->RegistrationV4.primary
                                        else->RegistrationV4.secondary
                                    },fontSize=12.sp,lineHeight=18.sp,
                                        fontWeight=if(i==1)FontWeight.SemiBold else FontWeight.Normal)
                                }
                            }
                        }
                        Spacer(Modifier.height(4.dp))
                        Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                            Box(Modifier.weight(1f)) {
                                RegistrationDashboardAction("신청 내용 보기",onClick={
                                    onViewApplication(app.applicationId)
                                })
                            }
                            Box(Modifier.weight(1f)) {
                                RegistrationDashboardAction("신청 취소",onClick={
                                    onCancel(app.applicationId)
                                })
                            }
                        }
                        if(debug){
                            Row {
                                RegistrationDashboardAction("Mock 거절",onClick={
                                    onReject(app.applicationId)
                                })
                                RegistrationDashboardAction("Mock 승인",onClick={onApprove(app)})
                            }
                        }
                    }
                    MockApplicationStatus.REJECTED -> {
                        Spacer(Modifier.height(8.dp))
                        Column(Modifier.fillMaxWidth()
                            .background(RegistrationV4.bg,RoundedCornerShape(12.dp))
                            .padding(12.dp),verticalArrangement=Arrangement.spacedBy(4.dp)) {
                            Text("운영팀이 남긴 이유",color=RegistrationV4.secondary,
                                fontSize=12.sp,lineHeight=18.sp)
                            Text(app.rejectionReason
                                ?: "사업자 주소에서 매장을 확인할 수 없었어요. 주소를 다시 확인해 주세요.",
                                color=RegistrationV4.text,fontSize=14.sp,lineHeight=21.sp)
                        }
                        Spacer(Modifier.height(8.dp))
                        Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                            Box(Modifier.weight(1f)){
                                RegistrationDashboardAction("다시 신청하기",primary=true,
                                    onClick={onReapply(app)})
                            }
                            Box(Modifier.weight(1f)){
                                RegistrationDashboardAction("목록에서 지우기",
                                    onClick={onDismiss(app.applicationId)})
                            }
                        }
                    }
                    MockApplicationStatus.CANCELED ->
                        Text("신청이 취소됐어요.",fontSize=14.sp,
                            color=RegistrationV4.secondary)
                    MockApplicationStatus.APPROVED ->
                        RegistrationDashboardAction("매장 관리하기",onClick={
                            snapshot.bars.firstOrNull{it.barId==app.barId}?.let(onManage)
                        })
                }
            }
        }
    }
    Box(Modifier.fillMaxWidth().padding(top=4.dp)
        .border(1.dp,Color(0xFF786A60),RoundedCornerShape(12.dp))
        .ownerQuietClick(onClick=onRegister).testTag("registration-dashboard-add"),
        contentAlignment=Alignment.Center){
        Row(Modifier.heightIn(min=48.dp),verticalAlignment=Alignment.CenterVertically,
            horizontalArrangement=Arrangement.spacedBy(8.dp)){
            RegistrationGlyph("plus",color=RegistrationV4.primary,size=16.dp)
            Text("다른 매장 등록하기",fontSize=14.sp,color=RegistrationV4.text)
        }
    }
}

@Composable
private fun RegistrationDashboardBadge(label:String,kind:String) {
    val bg=when(kind){
        "approved"->Color(0xFF244C38)
        "rejected"->Color(0xFF8E3736)
        else->Color(0xFF503C29)
    }
    val fg=when(kind){
        "approved"->Color(0xFFB9DFC8)
        "rejected"->Color(0xFFFFD8CC)
        else->Color(0xFFF7DFBF)
    }
    Box(Modifier.background(bg,RoundedCornerShape(50))
        .padding(horizontal=8.dp,vertical=2.dp)) {
        Text(label,color=fg,fontSize=12.sp,lineHeight=18.sp,
            fontWeight=FontWeight.SemiBold)
    }
}
@Composable
private fun RegistrationDashboardAction(
    label:String,primary:Boolean=false,onClick:()->Unit
){
    Box(Modifier.fillMaxWidth().heightIn(min=48.dp)
        .background(if(primary)RegistrationV4.primary else RegistrationV4.elevated,
            RoundedCornerShape(12.dp)).ownerQuietClick(onClick=onClick),
        contentAlignment=Alignment.Center) {
        Text(label,fontSize=14.sp,lineHeight=20.sp,fontWeight=FontWeight.SemiBold,
            color=if(primary)RegistrationV4.onPrimary else RegistrationV4.text)
    }
}
