package com.zerotoone.bottlemap.ui.owner

import android.content.Context
import android.content.Intent
import android.graphics.BitmapFactory
import android.net.Uri
import java.io.File
import androidx.core.content.FileProvider
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.sp
import androidx.compose.ui.graphics.Color
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
@OptIn(ExperimentalMaterial3Api::class)
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
    var certificateCapturePath by rememberSaveable { mutableStateOf<String?>(null) }
    var showAddressSheet by remember { mutableStateOf(false) }
    var showMenuPhotoSource by remember { mutableStateOf(false) }
    var menuCapturePath by rememberSaveable { mutableStateOf<String?>(null) }
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
    // App-owned camera output, never a public upload or production OCR request.
    val certificateCamera=rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()){ ok ->
        val file=certificateCapturePath?.let(::File)
        if(ok && file?.isFile==true && file.length()>0L) {
            val uri=FileProvider.getUriForFile(ctx,
                "${ctx.packageName}.owner.camera.provider",file)
            inputMethod="photo"
            save((latestDraft()?:draft).copy(certificatePhoto=MockPhoto(
                UUID.randomUUID().toString(),uri.toString(),MockPhotoKind.REGISTRATION_ATTACHMENT)))
            go(RegPage.READING)
        } else {
            file?.delete()
            if(ok) error="촬영한 사진을 읽지 못했어요. 다시 찍어 주세요."
        }
        certificateCapturePath=null
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

    // Registration capture uses the same camera provider/source choices as PR96.
    val menuCamera=rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()){ ok ->
        val path=menuCapturePath
        menuCapturePath=null
        val file=path?.let(::File)
        if(ok && file?.isFile==true && file.length()>0L) {
            val selected=(latestDraft()?:draft)
            if(selected.initialMenuPhotos.size<15) {
                val uri=FileProvider.getUriForFile(ctx,
                    "${ctx.packageName}.owner.camera.provider",file)
                save(selected.copy(initialMenuPhotos=selected.initialMenuPhotos+
                    MockPhoto(UUID.randomUUID().toString(),uri.toString(),MockPhotoKind.MENU_CAPTURE)))
            } else file.delete()
        } else {
            file?.delete()
            if(ok) error="촬영한 사진을 열 수 없어요. 다시 찍어주세요."
        }
    }
    fun takeMenuPhoto() {
        if((latestDraft()?:draft).initialMenuPhotos.size>=15)return
        try {
            val dir=File(ctx.filesDir,"owner-menu-captures").apply {mkdirs()}
            val file=File.createTempFile("registration-menu-", ".jpg",dir)
            menuCapturePath=file.absolutePath
            val uri=FileProvider.getUriForFile(ctx,
                "${ctx.packageName}.owner.camera.provider",file)
            menuCamera.launch(uri)
        }catch(_:Exception) {
            menuCapturePath?.let {File(it).delete()}
            menuCapturePath=null
            error="카메라를 열지 못했어요. 갤러리에서 선택하거나 다시 시도해 주세요."
        }
    }

    LaunchedEffect(screen) {
        if(screen==RegPage.READING){
            delay(1400) // ACTION_FIRST v4 HTML reading animation            // Explicit deterministic DEMO fixture; never claim results were derived from the photo.
            val current=(viewModel.state.value as? MockOwnerLoadState.Ready)?.snapshot?.registrationDraft
                ?: (viewModel.state.value as? MockOwnerLoadState.Empty)?.snapshot?.registrationDraft
                ?: draft
            save(current.copy(businessNumberDigits="1234567891",representativeName="김민준",
                openingDateIso="2019-05-14",proposedBarName="몰트 앤 무드"))
            go(RegPage.BIZCHECK)
        } else if(screen==RegPage.VERIFYING){
            delay(1300);go(RegPage.VERIFIED) // ACTION_FIRST v4 HTML verifying animation
        }
    }
    LaunchedEffect(snapshot?.registrationDraft!=null,startRegistration) {
        // Explicit local checkpoint outranks field-derived migration heuristics.
        // A newly launched process has an empty rememberSaveable history; rebuild it
        // so system Back and the header Back stay inside registration.
        if(snapshot?.registrationDraft!=null && (bars.isEmpty() || startRegistration) &&
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
        RegPage.BIZCHECK->"확인하기"
        RegPage.REVIEW->"신청하기"
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
    if(showCertificateSheet) ModalBottomSheet(
        onDismissRequest={showCertificateSheet=false},
        containerColor=RegistrationV4.surface,
        contentColor=RegistrationV4.text,
        dragHandle={Box(Modifier.padding(top=12.dp,bottom=12.dp)
            .size(width=32.dp,height=4.dp)
            .background(RegistrationV4.muted,RoundedCornerShape(4.dp)))}
    ) {
        Column(Modifier.fillMaxWidth().padding(start=20.dp,end=20.dp,bottom=28.dp),
            verticalArrangement=Arrangement.spacedBy(12.dp)) {
            Text("사업자등록증 사진",color=RegistrationV4.text,
                fontWeight=FontWeight.SemiBold,fontSize=18.sp)
            Text("글자가 잘 보이게, 네 모서리가 모두 나오게 찍어 주세요.",
                color=RegistrationV4.secondary,fontSize=14.sp)
            Row(Modifier.fillMaxWidth().heightIn(min=56.dp)
                .ownerQuietClick {
                    showCertificateSheet=false
                    try {
                        val dir=File(ctx.filesDir,"owner-menu-captures").apply{mkdirs()}
                        val file=File.createTempFile("registration-cert-", ".jpg",dir)
                        certificateCapturePath=file.absolutePath
                        val uri=FileProvider.getUriForFile(ctx,
                            "${ctx.packageName}.owner.camera.provider",file)
                        certificateCamera.launch(uri)
                    } catch(e:Exception) {
                        certificateCapturePath?.let {File(it).delete()}
                        certificateCapturePath=null
                        error="카메라를 열지 못했어요. 앨범에서 선택해 주세요."
                    }
                },verticalAlignment=Alignment.CenterVertically,
                horizontalArrangement=Arrangement.spacedBy(16.dp)) {
                RegistrationGlyph("camera")
                Text("바로 찍기",fontSize=16.sp,color=RegistrationV4.text)
            }
            Row(Modifier.fillMaxWidth().heightIn(min=56.dp)
                .ownerQuietClick {
                    showCertificateSheet=false
                    certificatePicker.launch(PickVisualMediaRequest(
                        ActivityResultContracts.PickVisualMedia.ImageOnly))
                },verticalAlignment=Alignment.CenterVertically,
                horizontalArrangement=Arrangement.spacedBy(16.dp)) {
                RegistrationGlyph("picture")
                Text("앨범에서 고르기",fontSize=16.sp,color=RegistrationV4.text)
            }
        }
    }
    if(showMenuPhotoSource) OwnerMenuPhotoSourceDialog(
        onDismiss={showMenuPhotoSource=false},
        onCamera={showMenuPhotoSource=false;takeMenuPhoto()},
        onGallery={
            showMenuPhotoSource=false
            menuPicker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
        }
    )
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

    Column(Modifier.fillMaxSize().background(RegistrationV4.bg).imePadding()) {
        if(screen!=RegPage.DONE) {
            if(screen==RegPage.HOME || screen==RegPage.VIEW_APPLICATION)
                OwnerHeader("내 매장 관리",if(screen==RegPage.HOME)onBack else ::back)
            else RegistrationBackBar(::back)
        }
        if(stage!=0) RegistrationProgress(stage)
        val centered=screen in listOf(RegPage.READING,RegPage.VERIFYING,
            RegPage.VERIFIED,RegPage.DONE)
        Column(Modifier.fillMaxWidth().weight(1f)
            .then(if(centered)Modifier else Modifier.verticalScroll(rememberScrollState()))
            .padding(horizontal=20.dp,vertical=if(centered)0.dp else 12.dp),
            horizontalAlignment=if(centered)Alignment.CenterHorizontally else Alignment.Start,
            verticalArrangement=if(centered)Arrangement.Center else Arrangement.spacedBy(16.dp)) {
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
                            snapshot=requireNotNull(snapshot), debug=false,
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
                                onManagerPreview()
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
                    RegPage.INTRO -> RegistrationIntro()
                    RegPage.METHOD -> {
                        OwnerV4Question("사업자등록증으로\n한 번에 채울까요?",
                            "사진을 찍으면 사업자등록번호, 대표자 성명, 개업일을 읽어 채워 드려요.")
                        Spacer(Modifier.height(0.dp))
                        Column(verticalArrangement=Arrangement.spacedBy(12.dp)) {
                            RegistrationChoice("camera","사진으로 채우기",
                                "읽은 내용은 다음 화면에서 확인해요","추천") { showCertificateSheet=true }
                            RegistrationChoice("pen","직접 입력하기","세 가지를 하나씩 입력해요") {
                                inputMethod="manual";go(RegPage.BN)
                            }
                        }
                    }
                    RegPage.READING -> RegistrationCenterContent(
                        "사업자등록증을\n읽고 있어요","잠시만 기다려 주세요.",loading=true)
                    RegPage.BN -> {
                        OwnerV4Question("사업자등록번호를\n알려주세요")
                        Spacer(Modifier.height(0.dp))
                        RegistrationInput(bnFormat(draft.businessNumberDigits),{},"000-00-00000",
                            readonly=true,tag="registration-business-number")
                        Text("숫자 10자리. 하이픈은 자동으로 들어가요.",
                            fontSize=12.sp,color=RegistrationV4.secondary)
                        if(draft.businessNumberDigits.length==10 &&
                            !validBusinessRegistrationNumber(draft.businessNumberDigits))
                            Text("번호를 다시 확인해 주세요. 사업자등록증의 10자리와 같아야 해요.",
                                fontSize=12.sp,color=RegistrationV4.error)
                    }
                    RegPage.REP -> {
                        OwnerV4Question("대표자 성명을\n알려주세요","사업자등록증에 적힌 이름 그대로 입력해 주세요.")
                        Spacer(Modifier.height(0.dp))
                        RegistrationInput(draft.representativeName,{
                            save(draft.copy(representativeName=it.take(100)))},
                            "홍길동",tag="registration-representative",highlight=true)
                        Spacer(Modifier.height(0.dp))
                        OwnerV4Previous("사업자등록번호",bnFormat(draft.businessNumberDigits)){go(RegPage.BN)}
                    }
                    RegPage.DATE -> {
                        OwnerV4Question("개업일을\n알려주세요","사업자등록증의 개업연월일이에요.")
                        Spacer(Modifier.height(0.dp))
                        RegistrationInput(draft.openingDateIso.replace("-","."),{},"YYYY.MM.DD",
                            readonly=true,tag="registration-opening-date")
                        if(draft.openingDateIso.length==10 && !validOpeningDate(draft.openingDateIso))
                            Text("날짜를 다시 확인해 주세요. 오늘 이후 날짜는 넣을 수 없어요.",
                                fontSize=12.sp,color=RegistrationV4.error)
                        Spacer(Modifier.height(0.dp))
                        OwnerV4Previous("대표자 성명",draft.representativeName){go(RegPage.REP)}
                        OwnerV4Previous("사업자등록번호",bnFormat(draft.businessNumberDigits)){go(RegPage.BN)}
                    }
                    RegPage.BIZCHECK -> {
                        OwnerV4Question(
                            if(inputMethod=="photo")"읽은 내용이\n맞는지 확인해 주세요"
                            else "이 정보로\n확인할게요",
                            if(inputMethod=="photo")"사진과 한 글자씩 비교해 주세요. 하나라도 다르면 확인에 실패해요."
                            else "국세청에 등록된 정보와 같은지 확인해요.")
                        Spacer(Modifier.height(0.dp))
                        Column(Modifier.fillMaxWidth()) {
                            OwnerV4Summary("사업자등록번호",bnFormat(draft.businessNumberDigits)){go(RegPage.BN)}
                            OwnerV4Summary("대표자 성명",draft.representativeName){go(RegPage.REP)}
                            OwnerV4Summary("개업일",draft.openingDateIso.replace("-",".")){go(RegPage.DATE)}
                        }
                    }
                    RegPage.VERIFYING -> RegistrationCenterContent(
                        "사업자 정보를\n확인하고 있어요","국세청 정보와 비교하고 있어요.",loading=true)
                    RegPage.VERIFIED -> {
                        when(verify){
                            VerifyFixture.MATCHED->RegistrationCenterContent(
                                "사업자 정보가\n확인됐어요","이제 매장 정보를 알려주세요.")
                            VerifyFixture.FAILED->RegistrationCenterContent(
                                "사업자 정보가\n맞지 않아요","사업자 정보를 다시 확인해 주세요.",success=false)
                            VerifyFixture.UNAVAILABLE->RegistrationCenterContent(
                                "지금은 국세청 확인이\n어려워요","운영팀이 나중에 다시 확인해요.",success=false)
                            VerifyFixture.LIMITED->RegistrationCenterContent(
                                "오늘 확인 횟수를\n모두 썼어요","입력한 내용은 그대로 남아 있어요.",success=false)
                        }
                    }

                    RegPage.BARNAME -> {
                        OwnerV4Question("매장 이름을\n알려주세요",
                            "손님에게 보이는 이름이에요. 사업자등록증의 상호와 간판이 다르면 간판 이름으로 고쳐 주세요.")
                        Spacer(Modifier.height(0.dp))
                        RegistrationInput(draft.proposedBarName,{
                            val edited=updatedBarNameDraft(draft,it)
                            if(needsNewBarDetailsAfterClaimEdit(editingReview,draft.kind,edited.kind)) {
                                editingReview=false
                                history=registrationHistoryFor(RegPage.BARNAME.name,edited.kind)
                            }
                            save(edited)
                        },"예: 몰트 앤 무드",tag="registration-bar-name",highlight=true)
                        exactMatches.forEach{ candidate ->
                            OwnerV4Panel("BottleMap에 이미 등록된 매장\n"+candidate.name+"\n"+candidate.address)
                            Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){
                                TextButton(onClick={
                                    save(draft.copy(kind=MockApplicationKind.EXISTING_BAR,
                                        existingBarId=candidate.barId,proposedBarName=candidate.name))
                                    go(RegPage.MENUS) // Existing bar already has cover, address and public phone.
                                }){Text("우리 매장예요")}
                                TextButton(onClick={
                                    if(needsNewBarDetailsAfterClaimEdit(
                                            editingReview,draft.kind,MockApplicationKind.NEW_BAR)) {
                                        editingReview=false
                                        history=registrationHistoryFor(
                                            RegPage.BARNAME.name,MockApplicationKind.NEW_BAR)
                                    }
                                    save(draft.copy(kind=MockApplicationKind.NEW_BAR,existingBarId=null))
                                    go(RegPage.BARPHOTO)
                                }){Text("아니에요")}
                            }
                        }
                    }
                    RegPage.BARPHOTO -> {
                        OwnerV4Question("매장 사진을\n올려 주세요",
                            "갤러리에서 사진을 선택해 주세요. 등록한 사진은 대표 사진으로 지정돼요.")
                        Spacer(Modifier.height(0.dp))
                        val cover=draft.applicantGallery.firstOrNull()
                        Box(Modifier.fillMaxWidth().aspectRatio(4f/3f)
                            .clip(RoundedCornerShape(16.dp))
                            .background(RegistrationV4.surface)
                            .then(if(cover==null)Modifier.registrationDashedBorder(16.dp)
                                else Modifier)
                            .ownerQuietClick {
                                coverPicker.launch(PickVisualMediaRequest(
                                    ActivityResultContracts.PickVisualMedia.ImageOnly))
                            }.testTag("registration-cover-photo"),
                            contentAlignment=Alignment.Center) {
                            if(cover!=null) {
                                OwnerV4Thumbnail(cover.uri,Modifier.fillMaxSize())
                                Box(Modifier.align(Alignment.BottomEnd).padding(10.dp)
                                    .background(RegistrationV4.bg,RoundedCornerShape(20.dp))
                                    .padding(horizontal=12.dp,vertical=8.dp)) {
                                    Text("바꾸기",color=RegistrationV4.text,fontSize=14.sp)
                                }
                            } else Column(horizontalAlignment=Alignment.CenterHorizontally,
                                verticalArrangement=Arrangement.spacedBy(8.dp)) {
                                RegistrationGlyph("camera",color=RegistrationV4.primary)
                                Text("사진 올리기",color=RegistrationV4.secondary,fontSize=14.sp)
                            }
                        }
                        Column(verticalArrangement=Arrangement.spacedBy(8.dp)) {
                            RegistrationHint("간판이나 입구, 매장 안쪽이 잘 보이는 사진")
                            RegistrationHint("사람 얼굴이 크게 나오지 않은 사진")
                        }
                    }
                    RegPage.ADDRESS -> {
                        OwnerV4Question("매장 주소를\n알려주세요",
                            "손님이 지도에서 찾을 수 있게 정확히 입력해 주세요.")
                        Spacer(Modifier.height(0.dp))
                        Column(verticalArrangement=Arrangement.spacedBy(8.dp)) {
                            Text("주소",color=RegistrationV4.secondary,fontSize=12.sp)
                            Row(Modifier.fillMaxWidth().heightIn(min=56.dp)
                                .background(RegistrationV4.surface,RoundedCornerShape(12.dp))
                                .border(1.dp,RegistrationV4.border,RoundedCornerShape(12.dp))
                                .ownerQuietClick{showAddressSheet=true}
                                .padding(horizontal=16.dp),
                                verticalAlignment=Alignment.CenterVertically,
                                horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                                RegistrationGlyph("search",color=RegistrationV4.text)
                                Text(draft.proposedBarAddress.ifEmpty{"도로명, 건물명으로 검색"},
                                    color=if(draft.proposedBarAddress.isEmpty())RegistrationV4.muted
                                    else RegistrationV4.text,fontSize=16.sp)
                            }
                        }
                        RegistrationInput(draft.proposedBarAddressDetail,{
                            save(draft.copy(proposedBarAddressDetail=it))
                        },"예: 2층",label="상세 주소",tag="registration-address-detail")
                    }
                    RegPage.BARPHONE -> {
                        OwnerV4Question("매장 전화번호를\n알려주세요",
                            "예약이나 문의 전화를 받을 가게 번호예요.")
                        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,
                            verticalAlignment=Alignment.CenterVertically){
                            RegistrationVisibility(public=true)
                            Text("가게 전화가 없어요",color=RegistrationV4.primary,fontSize=12.sp,
                                fontWeight=FontWeight.SemiBold,
                                modifier=Modifier.ownerQuietClick {
                                    save(draft.copy(storePhone=""));forward(RegPage.MENUS)
                                }.padding(8.dp))
                        }
                        RegistrationPhoneInput(draft.storePhone,{
                            save(draft.copy(storePhone=it))
                        },"02-000-0000",tag="registration-store-phone")
                        Text("지역번호나 0507 안심번호도 넣을 수 있어요.",
                            fontSize=12.sp,color=RegistrationV4.secondary)
                    }
                    RegPage.MENUS -> {
                        OwnerV4Question("메뉴판 사진을\n올려 주세요",
                            "AI가 메뉴를 읽어 두면, 승인된 뒤에 확인만 하고 공개할 수 있어요.")
                        Spacer(Modifier.height(0.dp))
                        val photoItems = draft.initialMenuPhotos
                        // Photo tiles and source popup follow PR96 Stage 7. Only this strip changes.
                        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                            horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                            photoItems.forEachIndexed { index,photo ->
                                Box(Modifier.width(112.dp).height(144.dp)
                                    .clip(RoundedCornerShape(7.dp))
                                    .background(Color(0xFFE9DDC9),RoundedCornerShape(7.dp))
                                    .testTag("registration-menu-photo-${index+1}")) {
                                    OwnerV4Thumbnail(photo.uri,Modifier.fillMaxSize())
                                    Text((index+1).toString(),
                                        Modifier.align(Alignment.BottomStart).padding(5.dp)
                                            .background(RegistrationV4.bg,RoundedCornerShape(50))
                                            .padding(horizontal=6.dp,vertical=3.dp),
                                        color=RegistrationV4.text,fontSize=10.sp)
                                    Text("×",Modifier.align(Alignment.TopEnd).padding(4.dp)
                                        .background(RegistrationV4.bg,RoundedCornerShape(50))
                                        .ownerQuietClick {
                                            save(draft.copy(initialMenuPhotos=photoItems.filterIndexed {
                                                i,_->i!=index }))
                                            // Remove only the app-owned capture, never a gallery URI.
                                            val stored=Uri.parse(photo.uri).path.orEmpty()
                                            if(stored.contains("/owner-menu-captures/registration-menu-"))
                                                File(stored).delete()
                                        }.testTag("registration-remove-menu-$index")
                                        .padding(horizontal=7.dp),
                                        color=RegistrationV4.text,fontSize=15.sp)
                                }
                            }
                            if(photoItems.size<15) {
                                Column(Modifier.width(112.dp).height(144.dp)
                                    .border(1.dp,RegistrationV4.border,RoundedCornerShape(7.dp))
                                    .background(RegistrationV4.surface,RoundedCornerShape(7.dp))
                                    .ownerQuietClick {showMenuPhotoSource=true}
                                    .testTag("registration-add-menu"),
                                    verticalArrangement=Arrangement.Center,
                                    horizontalAlignment=Alignment.CenterHorizontally) {
                                    Text("+",color=RegistrationV4.primary,fontSize=28.sp,
                                        fontWeight=FontWeight.Light,lineHeight=28.sp)
                                    Text("사진 추가",color=RegistrationV4.secondary,fontSize=13.sp)
                                }
                            }
                        }
                        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {
                            Text("메뉴판 순서대로 올려 주세요",
                                fontSize=12.sp,color=RegistrationV4.secondary)
                            Text(photoItems.size.toString()+"/15",
                                fontSize=12.sp,color=RegistrationV4.secondary)
                        }
                        Column(verticalArrangement=Arrangement.spacedBy(8.dp)) {
                            RegistrationHint("한 장에 한 면씩, 글자와 가격이 잘리지 않게")
                            RegistrationHint("빛 반사 없이 정면에서")
                        }
                    }
                    RegPage.CONTACT -> {
                        OwnerV4Question("연락받을 번호를\n알려주세요",
                            "승인 전에 운영팀이 확인 연락을 드릴 수 있어요.")
                        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,
                            verticalAlignment=Alignment.CenterVertically){
                            RegistrationVisibility(public=false)
                            if (draft.storePhone.isNotBlank()) {
                                Text("매장 번호와 같아요",color=RegistrationV4.primary,fontSize=12.sp,
                                    fontWeight=FontWeight.SemiBold,
                                    modifier=Modifier.ownerQuietClick(
                                        enabled=canCopyShopPhone(draft.storePhone)) {
                                        save(draft.copy(contactPhone=draft.storePhone))
                                    }.padding(8.dp))
                            }
                        }
                        RegistrationPhoneInput(draft.contactPhone,{
                            save(draft.copy(contactPhone=it))
                        },"010-0000-0000",tag="registration-contact")
                    }
                    RegPage.REVIEW -> {
                        OwnerV4Question("이렇게\n신청할게요","한 번 더 확인하고 신청해 주세요.")
                        Spacer(Modifier.height(8.dp))
                        Column(verticalArrangement=Arrangement.spacedBy(4.dp)) {
                            Row(verticalAlignment=Alignment.CenterVertically,
                                horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                                Text("사업자 정보",color=RegistrationV4.secondary,fontSize=14.sp)
                                Box(Modifier.background(Color(0xFF244C38),RoundedCornerShape(20.dp))
                                    .padding(horizontal=8.dp,vertical=3.dp)) {
                                    Text("확인 완료",color=Color(0xFFB9DFC8),fontSize=12.sp)
                                }
                            }
                            OwnerV4Summary("등록번호",bnFormat(draft.businessNumberDigits),null)
                            OwnerV4Summary("대표자",draft.representativeName,null)
                            OwnerV4Summary("개업일",draft.openingDateIso.replace("-","."),null)
                        }
                        Column(verticalArrangement=Arrangement.spacedBy(4.dp)) {
                            Text("매장 정보",color=RegistrationV4.secondary,fontSize=14.sp)
                            OwnerV4Summary("이름",draft.proposedBarName){edit(RegPage.BARNAME)}
                            if(draft.kind==MockApplicationKind.NEW_BAR) {
                                OwnerV4Summary("사진",draft.applicantGallery.size.toString()+"장"){edit(RegPage.BARPHOTO)}
                                OwnerV4Summary("주소",listOf(
                                    draft.proposedBarAddress,draft.proposedBarAddressDetail)
                                    .filter{it.isNotBlank()}.joinToString(" ")){edit(RegPage.ADDRESS)}
                                OwnerV4Summary("전화번호",formatOwnerPhone(draft.storePhone)
                                    .ifBlank{"없음"}){edit(RegPage.BARPHONE)}
                            }
                        }
                        Column(verticalArrangement=Arrangement.spacedBy(4.dp)) {
                            Text("메뉴판",color=RegistrationV4.secondary,fontSize=14.sp)
                            OwnerV4Summary("사진",draft.initialMenuPhotos.size.toString()+"장"){edit(RegPage.MENUS)}
                        }
                        Column(verticalArrangement=Arrangement.spacedBy(4.dp)) {
                            Text("신청자",color=RegistrationV4.secondary,fontSize=14.sp)
                            OwnerV4Summary("연락처",formatOwnerPhone(draft.contactPhone)){edit(RegPage.CONTACT)}
                        }
                        Row(Modifier.fillMaxWidth().heightIn(min=72.dp)
                            .background(RegistrationV4.surface,RoundedCornerShape(12.dp))
                            .padding(horizontal=16.dp,vertical=12.dp),
                            horizontalArrangement=Arrangement.spacedBy(12.dp),
                            verticalAlignment=Alignment.CenterVertically) {
                            Text("ⓘ",color=RegistrationV4.primary,fontSize=18.sp)
                            Text("운영팀 승인 전에는 매장과 메뉴가 손님에게 보이지 않아요.",
                                color=RegistrationV4.secondary,fontSize=14.sp,lineHeight=20.sp)
                        }
                    }
                    RegPage.DONE -> RegistrationCenterContent("신청을 마쳤어요",
                        "운영팀이 실제 매장인지 확인한 뒤 승인해요. 진행 상황은 마이페이지의 내 매장 관리에서 볼 수 있어요.")
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
        if(cta!=null&&state !is MockOwnerLoadState.Error) {
            Box(Modifier.fillMaxWidth()
                .then(if(screen==RegPage.BN||screen==RegPage.DATE)Modifier
                    else Modifier.navigationBarsPadding())
                .padding(start=20.dp,end=20.dp,top=12.dp,
                    bottom=if(screen==RegPage.BN||screen==RegPage.DATE)8.dp else 24.dp)) {
                RegistrationButton(cta,enabled=enabled,onClick=::primaryAction)
            }
        }
        if(screen==RegPage.BN || screen==RegPage.DATE) {
            RegistrationDigitsKeypad(onDigit={ digit ->
                if(screen==RegPage.BN)save(draft.copy(
                    businessNumberDigits=(draft.businessNumberDigits+digit).take(10)))
                else save(draft.copy(openingDateIso=dateInput(draft.openingDateIso+digit)))
            },onDelete={
                if(screen==RegPage.BN)save(draft.copy(
                    businessNumberDigits=draft.businessNumberDigits.dropLast(1)))
                else save(draft.copy(openingDateIso=dateInput(
                    draft.openingDateIso.filter(Char::isDigit).dropLast(1))))
            })
        }
    }
}

@Composable private fun OwnerV4Question(title:String,subtitle:String?=null) {
    RegistrationHeading(title,subtitle)
}
@Composable private fun OwnerV4Panel(value:String) {
    Box(Modifier.fillMaxWidth().background(RegistrationV4.surface,RoundedCornerShape(16.dp))
        .padding(16.dp)){Text(value,color=RegistrationV4.text,fontSize=14.sp)}
}
@Composable private fun OwnerV4Previous(label:String,value:String,action:()->Unit) {
    Column(Modifier.fillMaxWidth().ownerQuietClick(onClick=action).padding(vertical=8.dp)){
        Text(label,fontSize=12.sp,color=RegistrationV4.secondary)
        Text(value,fontSize=16.sp,color=RegistrationV4.text)
        Spacer(Modifier.height(8.dp))
        HorizontalDivider(color=RegistrationV4.border)
    }
}
@Composable private fun OwnerV4Summary(label:String,value:String,edit:(()->Unit)?) {
    RegistrationRow(label,value,edit)
}
@Composable private fun OwnerV4Input(label:String,value:String,change:(String)->Unit,
    keyboard:KeyboardType=KeyboardType.Text,placeholder:String="") {
    RegistrationInput(value,change,placeholder,keyboard=keyboard,
        tag="registration-field-"+label)
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
