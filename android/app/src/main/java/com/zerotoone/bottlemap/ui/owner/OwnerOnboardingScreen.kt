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
import kotlinx.coroutines.launch
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
    onFirstReview: (MockImportStatus?) -> Unit,
    onManagerPreview: () -> Unit,
    startRegistration: Boolean = false,
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
    val submitScope=rememberCoroutineScope()
    var screen by rememberSaveable { mutableStateOf(if(startRegistration)RegPage.INTRO else RegPage.HOME) }
    var history by rememberSaveable { mutableStateOf(listOf<String>()) }
    var inputMethod by rememberSaveable { mutableStateOf("manual") }
    var verify by rememberSaveable { mutableStateOf(VerifyFixture.MATCHED) }
    var showCertificateSheet by remember { mutableStateOf(false) }
    var certificateCapturePath by rememberSaveable { mutableStateOf<String?>(null) }
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
            val current=latestDraft() ?: draft
            val uri=current.certificatePhoto?.uri
            try {
                val extracted=uri?.let { viewModel.readBusinessCertificateLive(it) }
                if(extracted!=null) {
                    save(current.copy(
                        businessNumberDigits=extracted.businessRegistrationNumber
                            ?.filter(Char::isDigit) ?: current.businessNumberDigits,
                        representativeName=extracted.representativeName ?: current.representativeName,
                        openingDateIso=extracted.openingDate ?: current.openingDateIso,
                        proposedBarName=extracted.businessName ?: current.proposedBarName,
                        proposedBarAddress=extracted.address ?: current.proposedBarAddress,
                    ))
                } else {
                    // Retain deterministic screenshots for direct MockRepository tests only.
                    delay(1400)
                    save(current.copy(businessNumberDigits="1234567891",
                        representativeName="김민준",openingDateIso="2019-05-14",
                        proposedBarName="몰트 앤 무드"))
                }
                go(RegPage.BIZCHECK)
            } catch(e: Exception) {
                go(RegPage.BIZCHECK)
                error=e.message ?: "사업자등록증을 읽지 못했어요. 직접 입력해 주세요."
            }
        } else if(screen==RegPage.VERIFYING){
            // The actual NTS verification happens on POST /api/owner-applications.
            delay(350)
            // The direct Mock UI test retains its explicit demo verification flow.
            // Live NTS validation happens only on application POST, never here.
            verify=if(viewModel.usesProductionOwnerApi()) VerifyFixture.UNAVAILABLE
                else VerifyFixture.MATCHED
            go(RegPage.VERIFIED)
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

    LaunchedEffect(screen, draft.proposedBarName) {
        if(screen==RegPage.BARNAME && draft.proposedBarName.trim().length>=2 &&
            viewModel.usesProductionOwnerApi()) {
            delay(300)
            runCatching {
                viewModel.searchExistingBarCandidatesLive(draft.proposedBarName)
            }.onFailure { error=it.message ?: "기존 매장을 검색하지 못했어요." }
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
        RegPage.BN,RegPage.REP,RegPage.DATE,
        RegPage.BARNAME,RegPage.BARPHOTO,RegPage.ADDRESS,RegPage.BARPHONE,
        RegPage.MENUS,RegPage.CONTACT->"다음"
        RegPage.BIZCHECK->"확인하기"
        RegPage.VERIFIED->when(verify) {
            VerifyFixture.FAILED->"다시 확인하기"
            VerifyFixture.UNAVAILABLE->"계속하기"
            VerifyFixture.LIMITED->"돌아가기"
            VerifyFixture.MATCHED->"다음"
        }
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
            RegPage.BN->forward(if(inputMethod=="photo")RegPage.BIZCHECK else RegPage.REP)
            RegPage.REP->forward(if(inputMethod=="photo")RegPage.BIZCHECK else RegPage.DATE)
            RegPage.DATE->forward(RegPage.BIZCHECK)
            RegPage.BIZCHECK->go(RegPage.VERIFYING)
            RegPage.VERIFIED->when(verify){
                VerifyFixture.MATCHED,VerifyFixture.UNAVAILABLE->forward(RegPage.BARNAME)
                VerifyFixture.FAILED->go(RegPage.BIZCHECK)
                VerifyFixture.LIMITED->{history=emptyList();onBack()}
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
                    submitScope.launch {
                        try {
                            viewModel.submitRegistrationDraftLive()
                            history=emptyList()
                            screen=RegPage.DONE
                            error=null
                        } catch(e: Exception) {
                            error=e.message ?: "신청을 접수하지 못했어요."
                        } finally { busy=false }
                    }
                }
            }
            RegPage.DONE->onBack()
            else->Unit
        }
    }

    if(cancelId!=null) RegistrationApplicationConfirmSheet(
        kind=RegistrationApplicationSheet.CANCEL,
        onClose={cancelId=null},
        onConfirm={
            cancelId?.let { id ->
                if(!busy) {
                    busy=true
                    submitScope.launch {
                        try {
                            viewModel.cancelOwnerApplicationLive(id)
                            cancelId=null
                            error=null
                        } catch(e: Exception) {
                            error=e.message ?: "신청을 취소하지 못했어요."
                        } finally {busy=false}
                    }
                }
            }
        }
    )
    if(dismissId!=null) RegistrationApplicationConfirmSheet(
        kind=RegistrationApplicationSheet.DISMISS,
        onClose={dismissId=null},
        onConfirm={
            dismissId?.let { id ->
                runCatching {viewModel.dismissRejectedForFixture(id)}
                    .onSuccess {dismissId=null}.onFailure {error=it.message}
            }
        }
    )
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
                MockOwnerLoadState.Loading -> OwnerLoading(
                    if(viewModel.usesProductionOwnerApi()) "매장 정보를 불러오는 중" else "Mock 저장소 불러오는 중")
                is MockOwnerLoadState.Error -> {
                    Text(s.message,color=MaterialTheme.colorScheme.error)
                    OwnerActionButton("다시 시도",viewModel::retry)
                }
                else -> when(screen){
                    RegPage.HOME -> {
                        OwnerRegistrationDashboard(
                            snapshot=requireNotNull(snapshot),
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
                                if(!viewModel.usesProductionOwnerApi() && !snapshot.hasPublishedInitialReview(bar.barId)) {
                                    onFirstReview(snapshot.imports.lastOrNull{it.barId==bar.barId}?.status)
                                } else onManagerPreview()
                            },
                            onViewApplication={ id ->
                                activeApplicationId=id;go(RegPage.VIEW_APPLICATION)
                            },
                            onCancel={id->cancelId=id},
                            onDismiss={id->dismissId=id},
                            onReapply={app->
                                save(reapplicationDraftFromRejected(app))
                                editingReview=false
                                history=emptyList()
                                go(RegPage.INTRO)
                            },

                        )
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
                        RegistrationInput(bnFormat(draft.businessNumberDigits),{ entered ->
                            save(draft.copy(businessNumberDigits=entered.filter(Char::isDigit).take(10)))
                        },"000-00-00000",tag="registration-business-number",highlight=true)
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
                        RegistrationInput(draft.openingDateIso.replace("-","."),{ entered ->
                            val digits=entered.filter(Char::isDigit).take(8)
                            val formatted=when {
                                digits.length<=4 -> digits
                                digits.length<=6 -> digits.take(4)+"-"+digits.drop(4)
                                else -> digits.take(4)+"-"+digits.slice(4..5)+"-"+digits.drop(6)
                            }
                            save(draft.copy(openingDateIso=formatted))
                        },"YYYY.MM.DD",tag="registration-opening-date",highlight=true)
                        if(draft.openingDateIso.length==10 && !validOpeningDate(draft.openingDateIso))
                            Text("날짜를 다시 확인해 주세요. 오늘 이후 날짜는 넣을 수 없어요.",
                                fontSize=12.sp,color=RegistrationV4.error)
                        Spacer(Modifier.height(0.dp))
                        OwnerV4Previous("대표자 성명",draft.representativeName){go(RegPage.REP)}
                        OwnerV4Previous("사업자등록번호",bnFormat(draft.businessNumberDigits)){go(RegPage.BN)}
                    }
                    RegPage.BIZCHECK -> {
                        val ocrPartial=inputMethod=="photo" &&
                            (draft.businessNumberDigits.isBlank() ||
                                draft.representativeName.isBlank() || draft.openingDateIso.isBlank())
                        if(ocrPartial) {
                            RegistrationOcrPartialReview(
                                bnFormat(draft.businessNumberDigits),
                                draft.representativeName,
                                draft.openingDateIso.replace("-","."),
                                onEdit={ target ->
                                    go(when(target){
                                        "bn"->RegPage.BN
                                        "rep"->RegPage.REP
                                        else->RegPage.DATE
                                    })
                                })
                        } else {
                            OwnerV4Question(
                                if(inputMethod=="photo")"읽은 내용이\n맞는지 확인해 주세요"
                                else "이 정보로\n확인할게요",
                                if(inputMethod=="photo")
                                    "사진과 한 글자씩 비교해 주세요. 하나라도 다르면 확인에 실패해요."
                                else "국세청에 등록된 정보와 같은지 확인해요.")
                            Spacer(Modifier.height(0.dp))
                            Column(Modifier.fillMaxWidth()) {
                                OwnerV4Summary("사업자등록번호",bnFormat(draft.businessNumberDigits)){go(RegPage.BN)}
                                OwnerV4Summary("대표자 성명",draft.representativeName){go(RegPage.REP)}
                                OwnerV4Summary("개업일",draft.openingDateIso.replace("-",".")){go(RegPage.DATE)}
                            }
                        }
                    }
                    RegPage.VERIFYING -> RegistrationCenterContent(
                        "사업자 정보를\n확인하고 있어요","국세청 정보와 비교하고 있어요.",loading=true)
                    RegPage.VERIFIED -> {
                        when(verify){
                            VerifyFixture.MATCHED->RegistrationCenterContent(
                                "사업자 정보가\n확인됐어요","이제 매장 정보를 알려주세요.")
                            VerifyFixture.FAILED->RegistrationVerifyException(OwnerVerifyOutcome.MISMATCH)
                            VerifyFixture.UNAVAILABLE->RegistrationVerifyException(OwnerVerifyOutcome.UNAVAILABLE)
                            VerifyFixture.LIMITED->RegistrationVerifyException(OwnerVerifyOutcome.LIMIT)
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
                        exactMatches.forEach { candidate ->
                            RegistrationExistingBarCard(candidate.name,candidate.address,
                                onMine={
                                    save(draft.copy(kind=MockApplicationKind.EXISTING_BAR,
                                        existingBarId=candidate.barId,proposedBarName=candidate.name))
                                    go(RegPage.MENUS)
                                },
                                onOther={
                                    if(needsNewBarDetailsAfterClaimEdit(
                                            editingReview,draft.kind,MockApplicationKind.NEW_BAR)) {
                                        editingReview=false
                                        history=registrationHistoryFor(
                                            RegPage.BARNAME.name,MockApplicationKind.NEW_BAR)
                                    }
                                    save(draft.copy(kind=MockApplicationKind.NEW_BAR,existingBarId=null))
                                    go(RegPage.BARPHOTO)
                                })
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
                        RegistrationInput(draft.proposedBarAddress,{
                            save(draft.copy(proposedBarAddress=it.take(500)))
                        },"도로명 주소 또는 건물명 입력",
                            label="주소",tag="registration-address")
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
                                            // Never delete a capture retained by a submitted
                                            // application, another job or the persisted draft.
                                            val persisted=latestDraft()
                                            val retainedByDraft=persisted?.initialMenuPhotos
                                                ?.any { it.photoId==photo.photoId } == true
                                            val retainedByApplication=snapshot?.applications.orEmpty()
                                                .any { app -> app.registrationPhotos.any {
                                                    it.uri==photo.uri
                                                } }
                                            val retainedByImport=snapshot?.imports.orEmpty().any { job ->
                                                job.images.any { it.sourceUri==photo.uri }
                                            }
                                            if(!retainedByDraft && !retainedByApplication && !retainedByImport)
                                                deleteOwnedRegistrationMenuCapture(ctx,Uri.parse(photo.uri))
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
                        RegistrationReviewDetails(
                            values=RegistrationReviewValues(
                                number=bnFormat(draft.businessNumberDigits),
                                representative=draft.representativeName,
                                openingDate=draft.openingDateIso.replace("-","."),
                                name=draft.proposedBarName,
                                representativePhotoCount=if(draft.kind==MockApplicationKind.NEW_BAR)
                                    draft.applicantGallery.size else null,
                                address=if(draft.kind==MockApplicationKind.NEW_BAR)
                                    listOf(draft.proposedBarAddress,draft.proposedBarAddressDetail)
                                        .filter {it.isNotBlank()}.joinToString(" ") else null,
                                phone=if(draft.kind==MockApplicationKind.NEW_BAR)
                                    formatOwnerPhone(draft.storePhone) else null,
                                menuPhotoCount=draft.initialMenuPhotos.size,
                                contact=formatOwnerPhone(draft.contactPhone)
                            ),
                            readOnly=false,onEdit={ key ->
                                edit(when(key) {
                                    "barname"->RegPage.BARNAME
                                    "barphoto"->RegPage.BARPHOTO
                                    "address"->RegPage.ADDRESS
                                    "barphone"->RegPage.BARPHONE
                                    "menus"->RegPage.MENUS
                                    else->RegPage.CONTACT
                                })
                            }
                        )
                    }
                    RegPage.DONE -> RegistrationCenterContent("신청을 마쳤어요",
                        "운영팀이 실제 매장인지 확인한 뒤 승인해요.\n진행 상황은 마이페이지의 내 매장 관리에서 볼 수 있어요.")
                    RegPage.VIEW_APPLICATION -> {
                        OwnerV4Question("신청한 내용","검토 중에는 내용을 수정할 수 없어요.")
                        val application=snapshot?.applications?.firstOrNull {
                            it.applicationId==activeApplicationId
                        }
                        if(application==null) Text("신청을 찾지 못했어요.")
                        else {
                            Spacer(Modifier.height(8.dp))
                            RegistrationReviewDetails(
                                values=RegistrationReviewValues(
                                    number=bnFormat(application.businessNumberDigits.orEmpty()),
                                    representative=application.representativeName.orEmpty(),
                                    openingDate=application.openingDateIso.orEmpty().replace("-","."),
                                    name=application.proposedBarName,
                                    representativePhotoCount=if(application.kind==MockApplicationKind.NEW_BAR)
                                        application.registrationPhotos.count {it.kind==MockPhotoKind.BAR_GALLERY}
                                        else null,
                                    address=application.proposedBarAddress,
                                    phone=if(application.kind==MockApplicationKind.NEW_BAR)
                                        formatOwnerPhone(application.storePhone.orEmpty()) else null,
                                    menuPhotoCount=application.registrationPhotos.count {
                                        it.kind==MockPhotoKind.MENU_CAPTURE
                                    },
                                    contact=formatOwnerPhone(application.contactPhone.orEmpty())
                                ),
                                readOnly=true,onEdit={}
                            )
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
