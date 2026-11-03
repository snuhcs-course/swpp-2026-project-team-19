package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zerotoone.bottlemap.data.owner.*

/** Exact error surface contract from ACTION_FIRST v4 pp.23-25. */
internal enum class OwnerVerifyOutcome { MISMATCH, UNAVAILABLE, LIMIT }

@Composable
internal fun RegistrationVerifyException(outcome:OwnerVerifyOutcome) {
    val error=outcome==OwnerVerifyOutcome.MISMATCH
    val headline=when(outcome) {
        OwnerVerifyOutcome.MISMATCH -> "사업자 정보가\n맞지 않아요"
        OwnerVerifyOutcome.UNAVAILABLE -> "지금은 국세청 확인이\n어려워요"
        OwnerVerifyOutcome.LIMIT -> "오늘 확인 횟수를\n모두 썼어요"
    }
    val subtitle=when(outcome){
        OwnerVerifyOutcome.MISMATCH ->
            "사업자등록번호, 대표자 성명, 개업일 중 하나가 국세청 정보와 달라요. 사업자등록증과 똑같이 입력했는지 확인해 주세요."
        OwnerVerifyOutcome.UNAVAILABLE ->
            "신청은 이어서 할 수 있어요. 운영팀이 나중에 다시 확인해요."
        OwnerVerifyOutcome.LIMIT ->
            "사업자 정보 확인은 하루 5번까지 시도할 수 있어요.\n내일 0시부터 다시 진행해 주세요."
    }
    Column(Modifier.fillMaxWidth().testTag("registration-verify-${outcome.name.lowercase()}"),
        horizontalAlignment=Alignment.CenterHorizontally,
        verticalArrangement=Arrangement.spacedBy(8.dp)) {
        Box(Modifier.size(64.dp).background(if(error)Color(0xFF8E3736)
            else Color(0xFF503C29),CircleShape),contentAlignment=Alignment.Center) {
            Canvas(Modifier.size(32.dp)) {
                val u=size.width/24f
                val fg=if(error)Color(0xFFFFD8CC) else Color(0xFFF7DFBF)
                if(error) {
                    drawLine(fg,Offset(5f*u,5f*u),Offset(19f*u,19f*u),
                        strokeWidth=2.4f*u,cap=StrokeCap.Round)
                    drawLine(fg,Offset(19f*u,5f*u),Offset(5f*u,19f*u),
                        strokeWidth=2.4f*u,cap=StrokeCap.Round)
                }else{
                    drawCircle(fg,8f*u,Offset(12f*u,12f*u),
                        style=Stroke(2.4f*u))
                    drawLine(fg,Offset(12f*u,7f*u),Offset(12f*u,12f*u),
                        strokeWidth=2.4f*u,cap=StrokeCap.Round)
                    drawLine(fg,Offset(12f*u,12f*u),Offset(15f*u,14f*u),
                        strokeWidth=2.4f*u,cap=StrokeCap.Round)
                }
            }
        }
        Spacer(Modifier.height(8.dp))
        Text(headline,style=MaterialTheme.typography.headlineSmall,
            lineHeight=32.sp,color=RegistrationV4.text,textAlign=TextAlign.Center)
        Text(subtitle,color=RegistrationV4.secondary,fontSize=14.sp,
            lineHeight=21.sp,textAlign=TextAlign.Center)
    }
}

/** Page 26 source is the user's corrected screenshot, NOT the old PDF frame. */
@Composable
internal fun RegistrationOcrPartialReview(
    business:String,representative:String,openingDate:String="",onEdit:(String)->Unit
) {
    Spacer(Modifier.height(28.dp))
    RegistrationHeading("읽은 내용이\n맞는지 확인해 주세요",
        "사진과 한 글자씩 비교해 주세요. 하나라도 다르면 확인에 실패해요.")
    Spacer(Modifier.height(16.dp))
    Column(Modifier.fillMaxWidth()) {
        RegistrationPartialRow("사업자등록번호",
            business.ifBlank{"읽지 못했어요"},if(business.isBlank())"입력" else "수정",
            error=business.isBlank()){onEdit("bn")}
        RegistrationPartialRow("대표자 성명",
            representative.ifBlank{"읽지 못했어요"},if(representative.isBlank())"입력" else "수정",
            error=representative.isBlank()){onEdit("rep")}
        RegistrationPartialRow("개업일",
            openingDate.ifBlank{"읽지 못했어요"},if(openingDate.isBlank())"입력" else "수정",
            error=openingDate.isBlank()){onEdit("date")}
    }
    Row(Modifier.fillMaxWidth().padding(top=8.dp)
        .background(RegistrationV4.surface,RoundedCornerShape(12.dp))
        .heightIn(min=48.dp).padding(horizontal=16.dp,vertical=12.dp),
        verticalAlignment=Alignment.CenterVertically,
        horizontalArrangement=Arrangement.spacedBy(12.dp)) {
        RegistrationGlyph("info",color=RegistrationV4.primary,size=20.dp)
        Text("읽지 못한 항목은 직접 입력해 주세요.",
            color=RegistrationV4.secondary,fontSize=14.sp,lineHeight=20.sp)
    }
}
@Composable
private fun RegistrationPartialRow(
    label:String,value:String,editLabel:String,error:Boolean=false,onEdit:()->Unit
){
    Row(Modifier.fillMaxWidth().heightIn(min=56.dp),
        verticalAlignment=Alignment.CenterVertically,
        horizontalArrangement=Arrangement.spacedBy(8.dp)) {
        Text(label,modifier=Modifier.width(112.dp),color=RegistrationV4.secondary,
            fontSize=14.sp,lineHeight=21.sp)
        Text(value,modifier=Modifier.weight(1f),textAlign=TextAlign.End,
            fontSize=15.sp,lineHeight=22.sp,color=if(error)RegistrationV4.error
            else RegistrationV4.text,fontWeight=FontWeight.Medium)
        Box(Modifier.width(48.dp).height(48.dp).ownerQuietClick(onClick=onEdit),
            contentAlignment=Alignment.Center){
            Text(editLabel,color=RegistrationV4.primary,fontSize=14.sp,lineHeight=20.sp)
        }
    }
    Box(Modifier.fillMaxWidth().height(1.dp).background(RegistrationV4.border))
}

/** Existing-bar match overlay, p.27; no backend bar lookup is performed here. */
@Composable
internal fun RegistrationExistingBarCard(
    name:String,address:String,onMine:()->Unit,onOther:()->Unit
){
    Column(Modifier.fillMaxWidth().padding(top=4.dp)
        .background(RegistrationV4.surface,RoundedCornerShape(16.dp))
        .border(1.dp,Color(0xFF786A60),RoundedCornerShape(16.dp))
        .padding(16.dp),verticalArrangement=Arrangement.spacedBy(4.dp)) {
        Text("BottleMap에 이미 등록된 매장이 있어요",
            color=RegistrationV4.secondary,fontSize=14.sp,lineHeight=20.sp)
        Spacer(Modifier.height(4.dp))
        Text(name,color=RegistrationV4.text,fontSize=16.sp,lineHeight=24.sp,
            fontWeight=FontWeight.SemiBold)
        Text(address,color=RegistrationV4.secondary,fontSize=14.sp,lineHeight=20.sp)
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            RegistrationMiniAction("우리 매장이에요",Modifier.weight(1f),primary=true,onClick=onMine)
            RegistrationMiniAction("아니에요",Modifier.weight(1f),onClick=onOther)
        }
    }
}
@Composable internal fun RegistrationMiniAction(
    text:String,modifier:Modifier=Modifier,primary:Boolean=false,onClick:()->Unit
){
    Box(modifier.heightIn(min=48.dp)
        .background(if(primary)RegistrationV4.primary else RegistrationV4.elevated,
            RoundedCornerShape(12.dp)).ownerQuietClick(onClick=onClick),
        contentAlignment=Alignment.Center){
        Text(text,fontSize=14.sp,lineHeight=21.sp,fontWeight=FontWeight.SemiBold,
            color=if(primary)RegistrationV4.onPrimary else RegistrationV4.text)
    }
}

/** Debug-only catalog. Previews are ephemeral fixtures: production Draft is never mutated. */
internal val ownerRegistrationQaPages=listOf(
    21 to "내 매장 관리 · 검토 중",22 to "내 매장 관리 · 승인되지 않음",
    23 to "사업자 확인 · 불일치",24 to "사업자 확인 · 일시 오류",
    25 to "사업자 확인 · 횟수 제한",26 to "사업자등록증 · 일부 누락",
    27 to "매장 이름 · 기존 매장 발견",28 to "내 매장 관리 · 승인됨",
    29 to "내 매장 관리 · 여러 매장"
)

@Composable
internal fun OwnerRegistrationQaCatalog(onChoose:(Int)->Unit){
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState())
        .padding(horizontal=20.dp,vertical=12.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){
        Text("신청·예외 UI 검증 (Mock)",style=MaterialTheme.typography.headlineSmall,
            color=RegistrationV4.text)
        Text("21~29쪽 모두 표시 가능해요. 이 화면은 Debug 빌드에서만 보이고, 저장된 신청/매장 데이터는 변경하지 않아요.",
            color=RegistrationV4.secondary,fontSize=14.sp,lineHeight=21.sp)
        ownerRegistrationQaPages.forEach { (page,label) ->
            Row(Modifier.fillMaxWidth().heightIn(min=54.dp)
                .background(RegistrationV4.surface,RoundedCornerShape(12.dp))
                .ownerQuietClick {onChoose(page)}
                .testTag("registration-qa-page-$page").padding(horizontal=16.dp),
                verticalAlignment=Alignment.CenterVertically){
                Text(page.toString(),Modifier.width(35.dp),color=RegistrationV4.primary)
                Text(label,Modifier.weight(1f),color=RegistrationV4.text,fontSize=14.sp)
                RegistrationGlyph("chevron",color=RegistrationV4.secondary,size=16.dp)
            }
        }
    }
}
internal fun ownerQaPreviewSnapshot(page:Int):MockOwnerSnapshot {
    val bar=MockBar("qa-bar-1","몰트 앤 무드",
        "서울특별시 관악구 봉천로 12길 8 2층")
    val pending=MockOwnerApplication("qa-app-1",MockApplicationKind.NEW_BAR,
        MockApplicationStatus.PENDING,"몰트 앤 무드",submittedAtEpochMs=0L)
    val rejected=pending.copy(status=MockApplicationStatus.REJECTED,
        rejectionReason="사업자 주소에서 매장을 확인할 수 없었어요. 주소를 다시 확인해 주세요.")
    return when(page) {
        21->MockOwnerSnapshot(applications=listOf(pending))
        22->MockOwnerSnapshot(applications=listOf(rejected))
        28->MockOwnerSnapshot(bars=listOf(bar))
        29->MockOwnerSnapshot(
            bars=listOf(bar),
            applications=listOf(pending.copy(applicationId="qa-app-2",
                proposedBarName="샤로수길 몰트하우스")),
            imports=listOf(MockMenuImport("qa-import-1","qa-bar-1",
                MockImportStatus.APPLIED,reviewVersion=1,images=emptyList())),
            menuItems=listOf(MockBarMenuItem("qa-item-1","qa-bar-1","qa-product-1",
                options=listOf(MockMenuOption("qa-option-1",priceKrw=12000))))
        )
        else->MockOwnerSnapshot()
    }
}

@Composable
internal fun OwnerRegistrationQaPreview(page:Int,onBack:()->Unit,onAction:()->Unit){
    var sheet by remember(page) {mutableStateOf<RegistrationApplicationSheet?>(null)}
    sheet?.let { kind ->
        RegistrationApplicationConfirmSheet(kind=kind,onClose={sheet=null},
            onConfirm={sheet=null}) // Preview only: real actions stay on OwnerOnboardingScreen.
    }
    val managerPage=page in listOf(21,22,28,29)
    Column(Modifier.fillMaxSize().background(RegistrationV4.bg)
        .testTag("registration-qa-preview-$page")) {
        if(managerPage) {
            Row(Modifier.fillMaxWidth().height(52.dp),
                verticalAlignment=Alignment.CenterVertically) {
                Box(Modifier.width(56.dp)) { RegistrationBackBar(onBack) }
                Text("내 매장 관리",color=RegistrationV4.text,
                    fontSize=16.sp,fontWeight=FontWeight.SemiBold)
            }
        }
        else RegistrationBackBar(onBack)
        val stage=when(page) { 23,24,25,26->1; 27->2; else->0 }
        if(stage>0)RegistrationProgress(stage)
        if(managerPage){
            Column(Modifier.fillMaxWidth().weight(1f).verticalScroll(rememberScrollState())
                .padding(horizontal=20.dp,vertical=12.dp),
                verticalArrangement=Arrangement.spacedBy(12.dp)){
                OwnerRegistrationDashboard(
                    snapshot=ownerQaPreviewSnapshot(page),debug=false,
                    onRegister=onAction,onManage={onAction()},onViewApplication={onAction()},
                    onCancel={sheet=RegistrationApplicationSheet.CANCEL},
                    onDismiss={sheet=RegistrationApplicationSheet.DISMISS},
                    onReapply={onAction()},
                    onReject={onAction()},onApprove={onAction()}
                )
            }
        }else{
            val centered=page in 23..25
            Column(Modifier.fillMaxWidth().weight(1f)
                .then(if(centered)Modifier else Modifier.verticalScroll(rememberScrollState()))
                .padding(horizontal=if(centered)32.dp else 20.dp,
                    vertical=if(centered)0.dp else 12.dp),
                horizontalAlignment=if(centered)Alignment.CenterHorizontally else Alignment.Start,
                verticalArrangement=if(centered)Arrangement.Center else Arrangement.spacedBy(16.dp)){
                when(page){
                    23->RegistrationVerifyException(OwnerVerifyOutcome.MISMATCH)
                    24->RegistrationVerifyException(OwnerVerifyOutcome.UNAVAILABLE)
                    25->RegistrationVerifyException(OwnerVerifyOutcome.LIMIT)
                    26->RegistrationOcrPartialReview(
                        "123-45-67891","김민준",onEdit={onAction()})
                    27->{
                        RegistrationHeading("매장 이름을\n알려주세요",
                            "손님에게 보이는 이름이에요. 사업자등록증의 상호와 간판이 다르면 간판 이름으로 고쳐 주세요.")
                        Spacer(Modifier.height(8.dp))
                        RegistrationInput("몰트 앤 무드",{},"예: 몰트 앤 무드",
                            readonly=true)
                        RegistrationExistingBarCard("몰트 앤 무드",
                            "서울특별시 관악구 봉천로 12길 8",onMine=onAction,onOther=onAction)
                    }
                }
            }
            val label=when(page){
                23->"다시 확인하기";24->"계속하기";25->"돌아가기"
                26->"확인하기";27->"다음";else->"확인"
            }
            Box(Modifier.fillMaxWidth().padding(horizontal=20.dp,vertical=24.dp)) {
                RegistrationButton(label,enabled=page!=26 && page!=27,onClick=onAction)
            }
        }
    }
}

/** Same approved v4 warning sheet for pending cancellation and rejected-card
 * dismissal. Dismiss only hides the card locally, never deletes audit history. */
internal enum class RegistrationApplicationSheet { CANCEL, DISMISS }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun RegistrationApplicationConfirmSheet(
    kind:RegistrationApplicationSheet,
    onClose:()->Unit,
    onConfirm:()->Unit
) {
    val dismiss=kind==RegistrationApplicationSheet.DISMISS
    ModalBottomSheet(
        onDismissRequest=onClose,
        containerColor=RegistrationV4.surface,
        contentColor=RegistrationV4.text,
        dragHandle={
            Box(Modifier.padding(top=12.dp,bottom=16.dp)
                .size(width=36.dp,height=4.dp)
                .background(Color(0xFF786A60),RoundedCornerShape(4.dp)))
        }
    ) {
        Column(Modifier.fillMaxWidth().padding(start=20.dp,end=20.dp,bottom=24.dp)
            .testTag(if(dismiss)"registration-dismiss-sheet" else "registration-cancel-sheet"),
            verticalArrangement=Arrangement.spacedBy(8.dp)) {
            Text(if(dismiss)"이 신청을 지울까요?" else "신청을 취소할까요?",
                color=RegistrationV4.text,fontSize=20.sp,lineHeight=28.sp,
                fontWeight=FontWeight.SemiBold)
            Text(if(dismiss)
                "목록에서만 사라지고, 운영팀이 검토한 기록은 남아요. 같은 매장은 언제든 다시 신청할 수 있어요."
                else "취소하면 처음부터 다시 신청해야 해요.",
                color=RegistrationV4.secondary,fontSize=14.sp,lineHeight=21.sp)
            Spacer(Modifier.heightIn(min=4.dp))
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)){
                Box(Modifier.weight(1f).heightIn(min=56.dp)
                    .background(RegistrationV4.elevated,RoundedCornerShape(12.dp))
                    .ownerQuietClick(onClick=onClose),contentAlignment=Alignment.Center){
                    Text("닫기",color=RegistrationV4.text,fontSize=16.sp,
                        fontWeight=FontWeight.SemiBold)
                }
                Box(Modifier.weight(1f).heightIn(min=56.dp)
                    .background(RegistrationV4.primary,RoundedCornerShape(12.dp))
                    .ownerQuietClick(onClick=onConfirm),contentAlignment=Alignment.Center){
                    Text(if(dismiss)"지우기" else "취소하기",color=RegistrationV4.onPrimary,
                        fontSize=16.sp,fontWeight=FontWeight.SemiBold)
                }
            }
        }
    }
}
