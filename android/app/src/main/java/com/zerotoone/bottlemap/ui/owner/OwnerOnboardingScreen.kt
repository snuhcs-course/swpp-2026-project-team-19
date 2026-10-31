package com.zerotoone.bottlemap.ui.owner

import android.content.Context
import android.content.Intent
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.zerotoone.bottlemap.data.owner.*
import com.zerotoone.bottlemap.ui.common.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import java.util.UUID

/** ACTION_FIRST v4 mock form; no real OCR, NTS, operator approval or upload API. */
private enum class RegPage {
    HOME, INTRO, METHOD, READING, BN, REP, DATE, BIZCHECK, VERIFYING, VERIFIED,
    BARNAME, BARPHOTO, ADDRESS, BARPHONE, MENUS, CONTACT, REVIEW, DONE, VIEW_APPLICATION
}
private enum class VerifyFixture { MATCHED, FAILED, UNAVAILABLE, LIMITED }
private fun regStage(page: RegPage): Int = when(page) {
    RegPage.METHOD, RegPage.READING, RegPage.BN, RegPage.REP, RegPage.DATE,
    RegPage.BIZCHECK, RegPage.VERIFYING, RegPage.VERIFIED -> 1
    RegPage.BARNAME, RegPage.BARPHOTO, RegPage.ADDRESS, RegPage.BARPHONE -> 2
    RegPage.MENUS -> 3
    RegPage.CONTACT, RegPage.REVIEW -> 4
    else -> 0
}
private fun bnFormat(s:String):String {
    val n=ownerBusinessDigits(s)
    return when {
        n.length<=3 -> n
        n.length<=5 -> n.take(3)+"-"+n.drop(3)
        else -> n.take(3)+"-"+n.substring(3,5)+"-"+n.drop(5)
    }
}
private fun dateInput(raw:String):String {
    val n=raw.filter(Char::isDigit).take(8)
    return when {
        n.length<=4 -> n
        n.length<=6 -> n.take(4)+"-"+n.drop(4)
        else -> n.take(4)+"-"+n.substring(4,6)+"-"+n.drop(6)
    }
}
@Composable
fun OwnerOnboardingScreen(
    viewModel: OwnerMockViewModel,
    onBack: () -> Unit,
    onFirstReview: () -> Unit,
    onManagerPreview: () -> Unit,
    startRegistration: Boolean = false,
    onComponents: (() -> Unit)? = null,
    onLegacyDebugUpload: (() -> Unit)? = null,
) {
    val state by viewModel.state.collectAsState()
    val snapshot = when(val s=state) {
        is MockOwnerLoadState.Ready -> s.snapshot
        is MockOwnerLoadState.Empty -> s.snapshot
        else -> null
    }
    val draft=snapshot?.registrationDraft ?: MockRegistrationDraft()
    val bars=snapshot?.bars.orEmpty()
    val candidates=snapshot?.existingBarCandidates.orEmpty()
    val ctx=LocalContext.current
    var screen by rememberSaveable { mutableStateOf(if(startRegistration)RegPage.INTRO else RegPage.HOME) }
    var history by rememberSaveable { mutableStateOf(listOf<String>()) }
    var inputMethod by rememberSaveable { mutableStateOf("manual") }
    var verify by rememberSaveable { mutableStateOf(VerifyFixture.MATCHED) }
    var showCertificateSheet by remember { mutableStateOf(false) }
    var showAddressSheet by remember { mutableStateOf(false) }
    var cancelId by remember { mutableStateOf<String?>(null) }
    var dismissId by remember { mutableStateOf<String?>(null) }
    var activeApplicationId by rememberSaveable { mutableStateOf<String?>(null) }
    var editingReview by rememberSaveable { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    fun latestDraft(): MockRegistrationDraft? = when(val now=viewModel.state.value) {
        is MockOwnerLoadState.Ready -> now.snapshot.registrationDraft
        is MockOwnerLoadState.Empty -> now.snapshot.registrationDraft
        else -> null
    }
    fun save(value:MockRegistrationDraft){ viewModel.saveRegistrationDraft(value);error=null }
    fun checkpoint(target:RegPage){
        if(!registrationCheckpointable(target.name))return
        val current=latestDraft() ?: if(target==RegPage.METHOD) MockRegistrationDraft() else return
        if(current.resumePageKey!=target.name)
            viewModel.saveRegistrationDraft(current.copy(resumePageKey=target.name))
    }
    fun go(target:RegPage){
        checkpoint(target)
        history=history+screen.name
        screen=target
        error=null
    }
    fun showDashboard() {
        // Keep the registration draft/checkpoint intact while managing an owned bar.
        screen=RegPage.HOME
        history=emptyList()
        editingReview=false
        error=null
    }
    fun back() {
        val stack=if(history.isEmpty() && registrationCheckpointable(screen.name))
            registrationHistoryFor(screen.name,draft.kind) else history
        if(stack.isEmpty()) {
            if(bars.isNotEmpty())showDashboard() else onBack()
        } else {
            screen=RegPage.valueOf(stack.last())
            history=stack.dropLast(1)
            checkpoint(screen)
        }
        error=null
    }
    fun forward(target:RegPage) {
        if(editingReview) { editingReview=false;go(RegPage.REVIEW) } else go(target)
    }
    fun edit(target:RegPage){ editingReview=true;go(target) }
    BackHandler(enabled=screen!=RegPage.HOME && screen!=RegPage.DONE) { back() }

    val certificatePicker=rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()){ uri ->
        if(uri!=null){
            persistSelectedUri(ctx,uri)
            inputMethod="photo"
            save((latestDraft()?:draft).copy(certificatePhoto=MockPhoto(UUID.randomUUID().toString(),uri.toString(),MockPhotoKind.REGISTRATION_ATTACHMENT)))
            go(RegPage.READING)
        }
    }
    val coverPicker=rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()){ uri ->
        if(uri!=null){
            persistSelectedUri(ctx,uri)
            save((latestDraft()?:draft).copy(applicantGallery=listOf(MockPhoto(UUID.randomUUID().toString(),uri.toString(),MockPhotoKind.BAR_GALLERY))))
        }
    }
    val menuPicker=rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(15)){ uris ->
        val latest=latestDraft()?:draft
        val old=latest.initialMenuPhotos
        val oldUris=old.map{it.uri}.toSet()
        val added=uris.distinctBy{it.toString()}.filterNot{it.toString() in oldUris}
            .take((15-old.size).coerceAtLeast(0)).map{
                persistSelectedUri(ctx,it)
                MockPhoto(UUID.randomUUID().toString(),it.toString(),MockPhotoKind.MENU_CAPTURE)
            }
        if(added.isNotEmpty())save(latest.copy(initialMenuPhotos=old+added))
    }

    LaunchedEffect(screen) {
        if(screen==RegPage.READING){
            delay(400)
            // Explicit deterministic DEMO fixture; never claim results were derived from the photo.
            val current=(viewModel.state.value as? MockOwnerLoadState.Ready)?.snapshot?.registrationDraft
                ?: (viewModel.state.value as? MockOwnerLoadState.Empty)?.snapshot?.registrationDraft
                ?: draft
            save(current.copy(businessNumberDigits="1234567891",representativeName="김민준",
                openingDateIso="2019-05-14",proposedBarName="몰트 앤 무드"))
            go(RegPage.BIZCHECK)
        } else if(screen==RegPage.VERIFYING){
            delay(350);go(RegPage.VERIFIED)
        }
    }
    LaunchedEffect(snapshot?.registrationDraft!=null,startRegistration) {
        // Explicit local checkpoint outranks field-derived migration heuristics.
        // A newly launched process has an empty rememberSaveable history; rebuild it
        // so system Back and the header Back stay inside registration.
        if(snapshot?.registrationDraft!=null &&
            (screen==RegPage.HOME || (startRegistration && screen==RegPage.INTRO))){
            val target=registrationResumePage(draft)
            screen=RegPage.valueOf(target)
            history=registrationHistoryFor(target,draft.kind)
        }
    }

    LaunchedEffect(snapshot?.bars?.size,snapshot?.applications?.size,startRegistration) {
        if(!startRegistration && snapshot!=null &&
            snapshot.bars.isEmpty() && snapshot.applications.isEmpty() &&
            snapshot.registrationDraft==null && screen==RegPage.HOME){
            // HTML v4: no redundant entry page before the registration introduction.
            screen=RegPage.INTRO
        }
    }

    val exactMatches=candidates.filter{
        draft.proposedBarName.isNotBlank() &&
            it.name.trim().equals(draft.proposedBarName.trim(),ignoreCase=true)
    }
    val validContact=draft.contactPhone.isNotBlank()&&validOwnerPhone(draft.contactPhone)
    val stage=regStage(screen)
    val cta=when(screen){
        RegPage.INTRO->"시작하기"
        RegPage.BN,RegPage.REP,RegPage.DATE,RegPage.VERIFIED,
        RegPage.BARNAME,RegPage.BARPHOTO,RegPage.ADDRESS,RegPage.BARPHONE,
        RegPage.MENUS,RegPage.CONTACT->"다음"
        RegPage.BIZCHECK->"사업자 정보 확인 (Mock)"
        RegPage.REVIEW->"신청하기 (Mock)"
        RegPage.DONE->"확인"
        else->null
    }
    val enabled=!busy&&when(screen){
        RegPage.BN->validBusinessRegistrationNumber(draft.businessNumberDigits)
        RegPage.REP->draft.representativeName.trim().length in 1..100
        RegPage.DATE->validOpeningDate(draft.openingDateIso)
        RegPage.BIZCHECK->validBusinessRegistrationNumber(draft.businessNumberDigits)&&
            draft.representativeName.trim().length in 1..100&&validOpeningDate(draft.openingDateIso)
        RegPage.BARNAME->draft.proposedBarName.trim().length in 1..150&&exactMatches.isEmpty()
        RegPage.BARPHOTO->draft.applicantGallery.isNotEmpty()
        RegPage.ADDRESS->draft.proposedBarAddress.isNotBlank() &&
            listOf(draft.proposedBarAddress,draft.proposedBarAddressDetail)
                .filter{it.isNotBlank()}.joinToString(" ").trim().length in 1..500
        RegPage.BARPHONE->draft.storePhone.isNotBlank()&&validOwnerPhone(draft.storePhone)
        RegPage.MENUS->draft.initialMenuPhotos.isNotEmpty()
        RegPage.CONTACT->validContact
        RegPage.REVIEW->validContact&&draft.initialMenuPhotos.isNotEmpty()&&
            validBusinessRegistrationNumber(draft.businessNumberDigits)
        else->true
    }
    fun primaryAction(){
        when(screen){
            RegPage.INTRO->go(RegPage.METHOD)
            RegPage.BN->forward(RegPage.REP)
            RegPage.REP->forward(RegPage.DATE)
            RegPage.DATE->forward(RegPage.BIZCHECK)
            RegPage.BIZCHECK->go(RegPage.VERIFYING)
            RegPage.VERIFIED->when(verify){
                VerifyFixture.MATCHED,VerifyFixture.UNAVAILABLE->forward(RegPage.BARNAME)
                VerifyFixture.FAILED->go(RegPage.BIZCHECK)
                VerifyFixture.LIMITED->{history=emptyList();screen=RegPage.HOME}
            }
            RegPage.BARNAME->forward(RegPage.BARPHOTO)
            RegPage.BARPHOTO->forward(RegPage.ADDRESS)
            RegPage.ADDRESS->forward(RegPage.BARPHONE)
            RegPage.BARPHONE->forward(RegPage.MENUS)
            RegPage.MENUS->forward(RegPage.CONTACT)
            RegPage.CONTACT->forward(RegPage.REVIEW)
            RegPage.REVIEW->{
                if(!busy){
                    busy=true
                    try{viewModel.submitRegistrationDraftForFixture();history=emptyList();screen=RegPage.DONE}
                    catch(e:Exception){error=e.message}
                    finally{busy=false}
                }
            }
            RegPage.DONE->onBack()
            else->Unit
        }
    }

    if(cancelId!=null)AlertDialog(onDismissRequest={cancelId=null},
        title={Text("신청을 취소할까요?")},
        text={Text("취소하면 처음부터 다시 신청해야 해요.")},
        confirmButton={TextButton(onClick={
            cancelId?.let{viewModel.closeApplicationForFixture(it,MockApplicationStatus.CANCELED)}
            cancelId=null
        }){Text("취소하기")}},
        dismissButton={TextButton(onClick={cancelId=null}){Text("닫기")}})
    if(dismissId!=null)AlertDialog(onDismissRequest={dismissId=null},
        title={Text("이 신청을 지울까요?")},
        text={Text("목록에서만 숨기고 Mock 신청 이력은 보존해요.")},
        confirmButton={TextButton(onClick={
            dismissId?.let{viewModel.dismissRejectedForFixture(it)}
            dismissId=null
        }){Text("지우기")}},
        dismissButton={TextButton(onClick={dismissId=null}){Text("닫기")}})
    if(showCertificateSheet)AlertDialog(onDismissRequest={showCertificateSheet=false},
        title={Text("사업자등록증 사진")},
        text={Text("네 모서리와 글자가 잘 보이게 선택해 주세요. 실제 OCR은 실행하지 않습니다.")},
        confirmButton={TextButton(onClick={
            showCertificateSheet=false
            certificatePicker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
        }){Text("앨범에서 고르기")}},
        dismissButton={TextButton(onClick={showCertificateSheet=false}){Text("닫기")}})
    if(showAddressSheet)AlertDialog(onDismissRequest={showAddressSheet=false},
        title={Text("주소 검색 · Mock 예시")},
        text={
            Column {
                listOf("서울특별시 관악구 봉천로 12길 8",
                    "서울특별시 관악구 봉천로 12길 10").forEach{ addr->
                    TextButton(onClick={
                        save(draft.copy(proposedBarAddress=addr))
                        showAddressSheet=false
                    }){Text(addr)}
                }
                Text("실제 주소 검색 API는 연결되지 않았습니다.")
            }
        },
        confirmButton={TextButton(onClick={showAddressSheet=false}){Text("닫기")}})

    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).imePadding()) {
        if(screen!=RegPage.DONE)OwnerHeader(
            if(screen==RegPage.HOME||screen==RegPage.VIEW_APPLICATION)"내 매장 관리" else "",
            if(screen==RegPage.HOME)onBack else ::back)
        if(stage!=0){
            Row(Modifier.fillMaxWidth().padding(horizontal=20.dp),
                horizontalArrangement=Arrangement.spacedBy(4.dp)){
                repeat(4){ index ->
                    Box(Modifier.weight(1f).height(3.dp).background(
                        if(index<stage)MaterialTheme.colorScheme.primary
                        else MaterialTheme.colorScheme.outlineVariant,RoundedCornerShape(3.dp)))
                }
            }
            Text(stage.toString()+"/4 "+listOf("사업자 정보","매장 정보","메뉴판","확인")[stage-1],
                modifier=Modifier.padding(start=20.dp,top=8.dp),
                style=MaterialTheme.typography.labelSmall,
                color=MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Column(Modifier.fillMaxWidth().weight(1f).verticalScroll(rememberScrollState())
            .padding(horizontal=20.dp,vertical=12.dp),
            verticalArrangement=Arrangement.spacedBy(16.dp)) {
            if(bars.isNotEmpty() && screen!=RegPage.HOME && screen!=RegPage.DONE &&
                screen!=RegPage.VIEW_APPLICATION) {
                TextButton(onClick=::showDashboard) { Text("내 매장 목록으로 돌아가기") }
            }
            when(val s=state){
                MockOwnerLoadState.Loading -> OwnerLoading("Mock 저장소 불러오는 중")
                is MockOwnerLoadState.Error -> {
                    Text(s.message,color=MaterialTheme.colorScheme.error)
                    OwnerActionButton("다시 시도",viewModel::retry)
                }
                else -> when(screen){
                    RegPage.HOME -> {
                        OwnerRegistrationDashboard(
                            snapshot=requireNotNull(snapshot), debug=com.zerotoone.bottlemap.BuildConfig.DEBUG,
                            onRegister={
                                val saved=snapshot?.registrationDraft
                                if(saved!=null) {
                                    val target=RegPage.valueOf(registrationResumePage(saved))
                                    history=registrationHistoryFor(target.name,saved.kind)
                                    screen=target
                                    error=null
                                } else {
                                    save(MockRegistrationDraft());go(RegPage.INTRO)
                                }
                            },
                            onManage={ bar ->
                                viewModel.selectBar(bar.barId)
                                if(snapshot.hasPublishedInitialReview(bar.barId))onManagerPreview()
                                else onFirstReview()
                            },
                            onViewApplication={ id ->
                                activeApplicationId=id;go(RegPage.VIEW_APPLICATION)
                            },
                            onCancel={id->cancelId=id},
                            onDismiss={id->dismissId=id},
                            onReapply={app->
                                save(MockRegistrationDraft(kind=app.kind,existingBarId=app.barId,
                                    proposedBarName=app.proposedBarName,
                                    proposedBarAddress=app.proposedBarAddress.orEmpty()))
                                go(RegPage.INTRO)
                            },
                            onReject={id->viewModel.closeApplicationForFixture(id,MockApplicationStatus.REJECTED)},
                            onApprove={app->
                                try{
                                    val barId=app.barId?:"mock-bar-"+app.applicationId
                                    val bar=(bars+candidates).firstOrNull{it.barId==barId}
                                        ?:MockBar(barId,app.proposedBarName,app.proposedBarAddress?:"Mock 주소",
                                            phone=app.storePhone,
                                            gallery=app.registrationPhotos.filter{it.kind==MockPhotoKind.BAR_GALLERY})
                                    viewModel.approveForFixture(app.applicationId,bar)
                                    val uris=app.registrationPhotos.filter{it.kind==MockPhotoKind.MENU_CAPTURE}.map{it.uri}
                                    if(uris.isNotEmpty())viewModel.importPhotos(barId,uris,OwnerMockFixtures.imageFixtures(emptyMap()))
                                }catch(e:Exception){error=e.message}
                            }
                        )
                        if(onComponents!=null)OwnerActionButton("공통 컴포넌트 점검",onComponents,
                            Modifier.fillMaxWidth(),secondary=true)
                        if(onLegacyDebugUpload!=null)OwnerActionButton("개발자 도구 · 기존 메뉴 업로드 테스트",
                            onLegacyDebugUpload,Modifier.fillMaxWidth(),secondary=true)
                    }
                    RegPage.INTRO -> {
                        OwnerV4Question("매장 등록은\n이렇게 진행돼요",
                            "중간에 멈춰도 입력한 내용은 기기에 남아 있어요.")
                        listOf("1  사업자 정보 확인","2  매장 정보 입력",
                            "3  메뉴판 사진 올리기 (최대 15장)","4  운영팀 승인").forEach{OwnerV4Panel(it)}
                        OwnerV4Panel("미리 준비해 주세요 · 사업자등록증, 가게 사진 1장, 메뉴판 사진")
                    }
                    RegPage.METHOD -> {
                        OwnerV4Question("사업자등록증으로\n한 번에 채울까요?",
                            "사진을 선택하면 Mock OCR 샘플로 채워요. 실제 사진 인식은 하지 않습니다.")
                        OwnerActionButton("사진으로 채우기 (Mock)",{showCertificateSheet=true},
                            Modifier.fillMaxWidth())
                        OwnerActionButton("직접 입력하기",{
                            inputMethod="manual";go(RegPage.BN)
                        },Modifier.fillMaxWidth(),secondary=true)
                    }
                    RegPage.READING -> {
                        OwnerLoading("사업자등록증 읽는 중 · Mock")
                        Text("미리 준비한 예시 데이터입니다. 실제 OCR 결과가 아닙니다.")
                    }
                    RegPage.BN -> {
                        OwnerV4Question("사업자등록번호를\n알려주세요")
                        OwnerV4Input("사업자등록번호",bnFormat(draft.businessNumberDigits),
                            {save(draft.copy(businessNumberDigits=ownerBusinessDigits(it)))},
                            KeyboardType.Number,"000-00-00000")
                        Text("숫자 10자리. 마지막 자리 검증번호를 확인합니다.",
                            style=MaterialTheme.typography.bodySmall)
                        if(draft.businessNumberDigits.length==10 &&
                            !validBusinessRegistrationNumber(draft.businessNumberDigits))
                            Text("번호를 다시 확인해 주세요.",color=MaterialTheme.colorScheme.error)
                    }
                    RegPage.REP -> {
                        OwnerV4Question("대표자 성명을\n알려주세요","사업자등록증에 적힌 이름 그대로 입력해 주세요.")
                        OwnerV4Input("대표자 성명",draft.representativeName,{
                            save(draft.copy(representativeName=it.take(100)))
                        },placeholder="홍길동")
                        OwnerV4Previous("사업자등록번호",bnFormat(draft.businessNumberDigits)){go(RegPage.BN)}
                    }
                    RegPage.DATE -> {
                        OwnerV4Question("개업일을\n알려주세요","사업자등록증의 개업연월일이에요.")
                        OwnerV4Input("개업일",draft.openingDateIso.replace("-","."),{
                            save(draft.copy(openingDateIso=dateInput(it)))
                        },KeyboardType.Number,"YYYY.MM.DD")
                        if(draft.openingDateIso.length==10 && !validOpeningDate(draft.openingDateIso))
                            Text("잘못된 날짜이거나 오늘 이후 날짜예요.",color=MaterialTheme.colorScheme.error)
                        OwnerV4Previous("대표자 성명",draft.representativeName){go(RegPage.REP)}
                        OwnerV4Previous("사업자등록번호",bnFormat(draft.businessNumberDigits)){go(RegPage.BN)}
                    }
                    RegPage.BIZCHECK -> {
                        OwnerV4Question(
                            if(inputMethod=="photo")"읽은 내용이\n맞는지 확인해 주세요"
                            else "이 정보로\n확인할게요",
                            "직접 확인·수정해 주세요. 실제 국세청 조회는 실행하지 않습니다.")
                        OwnerV4Summary("사업자등록번호",bnFormat(draft.businessNumberDigits)){go(RegPage.BN)}
                        OwnerV4Summary("대표자 성명",draft.representativeName){go(RegPage.REP)}
                        OwnerV4Summary("개업일",draft.openingDateIso.replace("-",".")){go(RegPage.DATE)}
                        if(com.zerotoone.bottlemap.BuildConfig.DEBUG){
                            Text("Mock 확인 결과 선택",style=MaterialTheme.typography.labelLarge)
                            Row(Modifier.horizontalScroll(rememberScrollState())){
                                VerifyFixture.entries.forEach{ kind ->
                                    TextButton(onClick={verify=kind}){
                                        Text(when(kind){
                                            VerifyFixture.MATCHED->"일치"
                                            VerifyFixture.FAILED->"불일치"
                                            VerifyFixture.UNAVAILABLE->"확인 불가"
                                            VerifyFixture.LIMITED->"횟수 초과"
                                        })
                                    }
                                }
                            }
                        }
                    }
                    RegPage.VERIFYING -> {
                        OwnerLoading("사업자 정보 확인 중 · Mock")
                        Text("국세청 API는 호출하지 않습니다.")
                    }
                    RegPage.VERIFIED -> {
                        OwnerStatusLabel("Mock 시뮬레이션 · 실제 인증 아님",OwnerStatusTone.ATTENTION)
                        when(verify){
                            VerifyFixture.MATCHED->OwnerV4Question("사업자 정보가\n확인됐어요 (Mock)",
                                "이제 매장 정보를 알려주세요.")
                            VerifyFixture.FAILED->OwnerV4Question("사업자 정보가\n맞지 않아요 (Mock)",
                                "사업자등록번호, 대표자 성명, 개업일을 다시 확인해 주세요.")
                            VerifyFixture.UNAVAILABLE->OwnerV4Question("지금은 확인이\n어려워요 (Mock)",
                                "운영팀이 나중에 다시 확인할 수 있어요.")
                            VerifyFixture.LIMITED->OwnerV4Question("확인 횟수를\n모두 썼어요 (Mock)",
                                "Mock 응답 시나리오예요. 입력한 내용은 저장됩니다.")
                        }
                    }

                    RegPage.BARNAME -> {
                        OwnerV4Question("매장 이름을\n알려주세요",
                            "손님에게 보이는 이름이에요. 간판 이름으로 적어 주세요.")
                        OwnerV4Input("매장 이름",draft.proposedBarName,{
                            save(updatedBarNameDraft(draft,it))
                        },placeholder="예: 몰트 앤 무드")
                        exactMatches.forEach{ candidate ->
                            OwnerV4Panel("BottleMap에 이미 등록된 매장\n"+candidate.name+"\n"+candidate.address)
                            Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){
                                TextButton(onClick={
                                    save(draft.copy(kind=MockApplicationKind.EXISTING_BAR,
                                        existingBarId=candidate.barId,proposedBarName=candidate.name))
                                    go(RegPage.MENUS) // Existing bar already has cover, address and public phone.
                                }){Text("우리 매장예요")}
                                TextButton(onClick={
                                    save(draft.copy(kind=MockApplicationKind.NEW_BAR,existingBarId=null))
                                    go(RegPage.BARPHOTO)
                                }){Text("아니에요")}
                            }
                        }
                        if(com.zerotoone.bottlemap.BuildConfig.DEBUG&&candidates.isEmpty())
                            TextButton(onClick={
                                viewModel.seedExistingCandidateForFixture(MockBar("fixture-v4-bar",
                                    draft.proposedBarName.ifBlank{"몰트 앤 무드"},
                                    "서울특별시 관악구 봉천로 12길 8"))
                            }){Text("테스트: 같은 이름의 기존 매장 준비 (Mock)")}
                    }
                    RegPage.BARPHOTO -> {
                        OwnerV4Question("매장 사진을\n올려 주세요",
                            "갤러리에서 선택한 사진이 대표 사진으로 지정돼요.")
                        val cover=draft.applicantGallery.firstOrNull()
                        if(cover!=null)OwnerV4Thumbnail(cover.uri,Modifier.fillMaxWidth().height(230.dp))
                        OwnerActionButton(if(cover==null)"사진 올리기" else "사진 바꾸기",{
                            coverPicker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                        },Modifier.fillMaxWidth(),secondary=true)
                        Text("간판·입구·매장 안쪽이 보이는 사진을 선택해 주세요.",
                            style=MaterialTheme.typography.bodySmall)
                    }
                    RegPage.ADDRESS -> {
                        OwnerV4Question("매장 주소를\n알려주세요",
                            "손님이 지도에서 찾을 수 있게 정확히 입력해 주세요.")
                        OwnerV4Input("주소",draft.proposedBarAddress,{
                            save(draft.copy(proposedBarAddress=it))
                        },placeholder="도로명, 건물명으로 검색")
                        TextButton(onClick={showAddressSheet=true}){Text("주소 검색 결과 예시 (Mock)")}
                        OwnerV4Input("상세 주소",draft.proposedBarAddressDetail,{
                            save(draft.copy(proposedBarAddressDetail=it))
                        },placeholder="예: 2층")
                    }
                    RegPage.BARPHONE -> {
                        OwnerV4Question("매장 전화번호를\n알려주세요",
                            "예약이나 문의 전화를 받을 가게 번호예요.")
                        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,
                            verticalAlignment=Alignment.CenterVertically){
                            OwnerStatusLabel("손님에게 보여요")
                            TextButton(onClick={
                                save(draft.copy(storePhone=""));forward(RegPage.MENUS)
                            }){Text("가게 전화가 없어요",style=MaterialTheme.typography.labelSmall)}
                        }
                        OwnerV4Input("매장 전화번호",formatOwnerPhone(draft.storePhone),{
                            save(draft.copy(storePhone=ownerPhoneDigits(it)))
                        },KeyboardType.Phone,"02-000-0000")
                        Text("지역번호나 0507 안심번호도 넣을 수 있어요.",
                            style=MaterialTheme.typography.bodySmall)
                    }
                    RegPage.MENUS -> {
                        OwnerV4Question("메뉴판 사진을\n올려 주세요",
                            "AI 분석은 아직 실행하지 않으며 선택한 사진 참조와 순서를 보존해요.")
                        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                            horizontalArrangement=Arrangement.spacedBy(8.dp)){
                            draft.initialMenuPhotos.forEachIndexed{ index,photo ->
                                Column(verticalArrangement=Arrangement.spacedBy(4.dp)){
                                    OwnerV4Thumbnail(photo.uri,Modifier.size(width=106.dp,height=142.dp))
                                    Text((index+1).toString()+"번 사진",style=MaterialTheme.typography.labelSmall)
                                    TextButton(onClick={
                                        save(draft.copy(initialMenuPhotos=draft.initialMenuPhotos
                                            .filterIndexed{ i,_->i!=index }))
                                    }){Text("사진 빼기")}
                                }
                            }
                        }
                        if(draft.initialMenuPhotos.size<15)
                            OwnerActionButton("사진 추가",{
                                menuPicker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                            },Modifier.fillMaxWidth(),secondary=true)
                        Text("메뉴판 순서대로 올려 주세요     "+draft.initialMenuPhotos.size+"/15")
                        Text("한 장에 한 면씩, 글자와 가격이 잘리지 않게 촬영해 주세요.",
                            style=MaterialTheme.typography.bodySmall)
                    }
                    RegPage.CONTACT -> {
                        OwnerV4Question("연락받을 번호를\n알려주세요",
                            "승인 전에 운영팀이 확인 연락을 드릴 수 있어요.")
                        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,
                            verticalAlignment=Alignment.CenterVertically){
                            OwnerStatusLabel("운영팀만 봐요")
                            if (draft.storePhone.isNotBlank()) {
                                TextButton(
                                    onClick={save(draft.copy(contactPhone=draft.storePhone))},
                                    enabled=canCopyShopPhone(draft.storePhone)
                                ){
                                    Text("매장 번호와 같아요",style=MaterialTheme.typography.labelSmall)
                                }
                            }
                        }
                        OwnerV4Input("연락받을 번호",formatOwnerPhone(draft.contactPhone),{
                            save(draft.copy(contactPhone=ownerPhoneDigits(it)))
                        },KeyboardType.Phone,"010-0000-0000")
                    }
                    RegPage.REVIEW -> {
                        OwnerV4Question("이렇게\n신청할게요","한 번 더 확인하고 신청해 주세요.")
                        OwnerStatusLabel("Mock 정보 확인 · 실제 국세청 인증 아님",
                            OwnerStatusTone.ATTENTION)
                        Text("사업자 정보",style=MaterialTheme.typography.titleMedium)
                        OwnerV4Summary("등록번호",bnFormat(draft.businessNumberDigits),null)
                        OwnerV4Summary("대표자",draft.representativeName,null)
                        OwnerV4Summary("개업일",draft.openingDateIso.replace("-","."),null)
                        Text("매장 정보",style=MaterialTheme.typography.titleMedium)
                        OwnerV4Summary("이름",draft.proposedBarName){edit(RegPage.BARNAME)}
                        if(draft.kind==MockApplicationKind.NEW_BAR){
                            OwnerV4Summary("대표 사진",draft.applicantGallery.size.toString()+"장"){edit(RegPage.BARPHOTO)}
                            OwnerV4Summary("주소",listOf(draft.proposedBarAddress,draft.proposedBarAddressDetail)
                                .filter{it.isNotBlank()}.joinToString(" ")){edit(RegPage.ADDRESS)}
                            OwnerV4Summary("매장 전화",draft.storePhone.ifBlank{"없음"}){edit(RegPage.BARPHONE)}
                        }
                        OwnerV4Summary("메뉴판",draft.initialMenuPhotos.size.toString()+"장"){edit(RegPage.MENUS)}
                        OwnerV4Summary("연락처",formatOwnerPhone(draft.contactPhone)){edit(RegPage.CONTACT)}
                        OwnerV4Panel("운영팀 승인 전에는 매장과 메뉴가 손님에게 보이지 않아요.")
                    }
                    RegPage.DONE -> {
                        Spacer(Modifier.height(80.dp))
                        OwnerV4Question("신청을 마쳤어요",
                            "운영팀이 실제 매장인지 확인한 뒤 승인해요. "+
                                "진행 상황은 마이페이지의 내 매장 관리에서 볼 수 있어요.")
                        OwnerStatusLabel("Mock 신청 완료 · 실제 서버 제출 아님")
                    }
                    RegPage.VIEW_APPLICATION -> {
                        OwnerV4Question("신청한 내용",
                            "검토 중인 신청은 수정할 수 없어요.")
                        val application=snapshot?.applications?.firstOrNull{
                            it.applicationId==activeApplicationId
                        }
                        if(application==null)Text("신청을 찾지 못했어요.")
                        else{
                            OwnerV4Summary("매장명",application.proposedBarName,null)
                            OwnerV4Summary("등록번호",application.businessNumberDigits.orEmpty(),null)
                            OwnerV4Summary("대표자",application.representativeName.orEmpty(),null)
                            OwnerV4Summary("개업일",application.openingDateIso.orEmpty(),null)
                            if(application.kind==MockApplicationKind.NEW_BAR){
                                OwnerV4Summary("주소",application.proposedBarAddress.orEmpty(),null)
                                OwnerV4Summary("매장 전화",application.storePhone?:"없음",null)
                            }
                            OwnerV4Summary("메뉴판",application.registrationPhotos.count{
                                it.kind==MockPhotoKind.MENU_CAPTURE
                            }.toString()+"장",null)
                            OwnerV4Summary("연락처",application.contactPhone.orEmpty(),null)
                        }
                    }
                }
            }
            error?.let{Text(it,color=MaterialTheme.colorScheme.error)}
        }
        if(cta!=null&&state !is MockOwnerLoadState.Error){
            Box(Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal=20.dp,vertical=12.dp)){
                OwnerActionButton(cta,::primaryAction,Modifier.fillMaxWidth(),enabled=enabled)
            }
        }
    }
}

@Composable private fun OwnerV4Question(title:String,subtitle:String?=null){
    Text(title,style=MaterialTheme.typography.headlineSmall,
        color=MaterialTheme.colorScheme.onBackground)
    if(!subtitle.isNullOrBlank())Text(subtitle,style=MaterialTheme.typography.bodyMedium,
        color=MaterialTheme.colorScheme.onSurfaceVariant)
}
@Composable private fun OwnerV4Panel(value:String){
    Box(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface,RoundedCornerShape(16.dp))
        .padding(16.dp)){Text(value,style=MaterialTheme.typography.bodyMedium)}
}
@Composable private fun OwnerV4Previous(label:String,value:String,action:()->Unit){
    Column(Modifier.fillMaxWidth().clickable(onClick=action).padding(vertical=8.dp)){
        Text(label,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value,style=MaterialTheme.typography.bodyLarge)
    }
}
@Composable private fun OwnerV4Summary(label:String,value:String,edit:(()->Unit)?){
    Row(Modifier.fillMaxWidth().padding(vertical=8.dp),
        horizontalArrangement=Arrangement.spacedBy(8.dp),
        verticalAlignment=Alignment.CenterVertically){
        Text(label,modifier=Modifier.width(88.dp),
            color=MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value,modifier=Modifier.weight(1f),style=MaterialTheme.typography.bodyMedium)
        if(edit!=null)TextButton(onClick=edit){Text("수정")}
    }
    HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
}
@Composable private fun OwnerV4Input(label:String,value:String,change:(String)->Unit,
    keyboard:KeyboardType=KeyboardType.Text,placeholder:String=""){
    OutlinedTextField(value=value,onValueChange=change,label={Text(label)},
        placeholder={Text(placeholder)},singleLine=true,
        keyboardOptions=KeyboardOptions(keyboardType=keyboard),
        modifier=Modifier.fillMaxWidth())
}
private fun persistSelectedUri(context:Context,uri:Uri){
    try{
        context.contentResolver.takePersistableUriPermission(uri,Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }catch(_:SecurityException){/* The picker may grant temporary URI only. */}
}
/** Downsample before decode; never decode a full-resolution camera image on main thread. */
@Composable private fun OwnerV4Thumbnail(uri:String,modifier:Modifier){
    val ctx=LocalContext.current
    val image by produceState<androidx.compose.ui.graphics.ImageBitmap?>(null,uri){
        value=withContext(Dispatchers.IO){
            try{
                ctx.contentResolver.openInputStream(Uri.parse(uri))?.use{
                    BitmapFactory.decodeStream(it,null,BitmapFactory.Options().apply{
                        inSampleSize=8
                    })?.asImageBitmap()
                }
            }catch(_:Exception){null}
        }
    }
    if(image!=null)Image(bitmap=image!!,contentDescription="선택한 사진",
        modifier=modifier,contentScale=ContentScale.Crop)
    else Box(modifier.background(MaterialTheme.colorScheme.surface,RoundedCornerShape(12.dp)),
        contentAlignment=Alignment.Center){
        Text("사진 미리보기 불가",style=MaterialTheme.typography.labelSmall)
    }
}
