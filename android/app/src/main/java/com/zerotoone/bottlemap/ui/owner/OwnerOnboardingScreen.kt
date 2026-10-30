package com.zerotoone.bottlemap.ui.owner

import android.content.Context
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.Image
import androidx.compose.foundation.horizontalScroll
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import android.graphics.BitmapFactory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import com.zerotoone.bottlemap.data.owner.*
import com.zerotoone.bottlemap.ui.common.*
import java.util.UUID

/** I3-P14 local-only registration. Latest ACTION_FIRST v4 HTML was not supplied to
 * this runtime: labels/layout below follow the explicit prompt, not unverified HTML. */
private enum class FormStep { METHOD, CERTIFICATE, BIZ, BAR, VERIFICATION, PHOTOS, PHONE, MENU, CONTACT, REVIEW, SUBMITTED }

internal fun ownerPhoneDigits(v: String): String = v.filter(Char::isDigit).take(12)
internal fun validOwnerPhone(value: String): Boolean =
    value.isBlank() || (value.filter(Char::isDigit).length in 8..12)

@Composable
fun OwnerOnboardingScreen(
    repository: OwnerMockRepository,
    onBack: () -> Unit,
    onFirstReview: () -> Unit,
    onManagerPreview: () -> Unit,
    startRegistration: Boolean = false,
    onComponents: (() -> Unit)? = null,
    onLegacyDebugUpload: (() -> Unit)? = null,
) {
    val state by repository.state.collectAsState()
    val snapshot = when(val s=state) {
        is MockOwnerLoadState.Ready -> s.snapshot
        is MockOwnerLoadState.Empty -> s.snapshot
        else -> null
    }
    val context=LocalContext.current
    var step by rememberSaveable { mutableStateOf(if(startRegistration)FormStep.CERTIFICATE else FormStep.METHOD) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    var noShopPhone by rememberSaveable { mutableStateOf(false) }
    var selectedBarId by rememberSaveable { mutableStateOf<String?>(null) }
    val draft = snapshot?.registrationDraft ?: MockRegistrationDraft()
    val certificateUri = draft.certificatePhoto?.uri
    // Persisted form fields survive process restart. Reopen the unfinished draft
    // instead of forcing registration mode selection (which would clear it).
    LaunchedEffect(snapshot?.registrationDraft != null, startRegistration) {
        if (!startRegistration && snapshot?.registrationDraft != null && step == FormStep.METHOD) {
            step = if(draft.businessNumberDigits.isNotBlank()) FormStep.BAR else FormStep.BIZ
        }
    }
    fun save(newDraft: MockRegistrationDraft) { repository.saveRegistrationDraft(newDraft);error=null }
    fun next() { error=null;step=FormStep.entries.getOrElse(step.ordinal+1){FormStep.REVIEW} }
    fun goBack() {
        error=null
        if (step == FormStep.METHOD || (startRegistration && step == FormStep.CERTIFICATE)) onBack()
        else step=FormStep.entries[(step.ordinal - 1).coerceAtLeast(0)]
    }
    BackHandler(enabled=step != FormStep.METHOD) { goBack() }
    val pickCertificate=rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if(uri!=null) { persistUri(context,uri); save(draft.copy(certificatePhoto=MockPhoto(UUID.randomUUID().toString(),uri.toString(),MockPhotoKind.REGISTRATION_ATTACHMENT))) }
    }
    val pickCover=rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if(uri!=null) {
            persistUri(context,uri)
            save(draft.copy(applicantGallery=listOf(MockPhoto(UUID.randomUUID().toString(),uri.toString(),MockPhotoKind.BAR_GALLERY))))
        }
    }
    val pickMenu=rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(15)) { uris ->
        uris.forEach { persistUri(context,it) }
        if(uris.isNotEmpty()) save(draft.copy(initialMenuPhotos=uris.map {
            MockPhoto(UUID.randomUUID().toString(),it.toString(),MockPhotoKind.MENU_CAPTURE)
        }))
    }
    val bars=snapshot?.bars.orEmpty()
    val candidates=snapshot?.existingBarCandidates.orEmpty()
    val apps=snapshot?.applications.orEmpty()
    val pending=apps.lastOrNull { it.status==MockApplicationStatus.PENDING }
    val rejected=apps.lastOrNull { it.status==MockApplicationStatus.REJECTED }
    val canceled=apps.lastOrNull { it.status==MockApplicationStatus.CANCELED }
    val approved=apps.lastOrNull { it.status==MockApplicationStatus.APPROVED }
    Column(Modifier.fillMaxSize()) {
        OwnerHeader("내 매장 관리",::goBack)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).imePadding().navigationBarsPadding().padding(20.dp),
            verticalArrangement=Arrangement.spacedBy(14.dp)) {
            OwnerStatusLabel("Mock 시연 전용 · 실제 개인/사업자 정보 입력 금지",OwnerStatusTone.ATTENTION)
            when {
                state is MockOwnerLoadState.Loading -> OwnerLoading("Mock 정보 불러오는 중")
                state is MockOwnerLoadState.Error -> {
                    Text((state as MockOwnerLoadState.Error).message)
                    OwnerActionButton("다시 시도",repository::retryLoad)
                }
                pending!=null && step!=FormStep.SUBMITTED -> {
                    OwnerStatusLabel("신청 중",OwnerStatusTone.ATTENTION)
                    Text("운영팀 승인 전에는 매장 메뉴가 공개되지 않습니다.")
                    Text(pending.proposedBarName)
                    OwnerActionButton("신청 취소 (Mock)",{
                        repository.closeApplicationForFixture(pending.applicationId,MockApplicationStatus.CANCELED)
                        step=FormStep.METHOD
                    },Modifier.fillMaxWidth(),secondary=true)
                    if(BuildConfigDebug()) OwnerActionButton("테스트: 거절 처리 (Mock)", {
                        repository.closeApplicationForFixture(pending.applicationId,MockApplicationStatus.REJECTED)
                    },Modifier.fillMaxWidth(),secondary=true)
                    if(BuildConfigDebug()) OwnerActionButton("테스트: 승인 처리 (Mock)", {
                        val id=pending.barId?:"mock-bar-${pending.applicationId}"
                        val existing=(bars+candidates).firstOrNull { it.barId==id }
                        val newBar=existing?:MockBar(id,pending.proposedBarName,pending.proposedBarAddress?:"테스트 주소",
                            phone=pending.storePhone,
                            gallery=pending.registrationPhotos.filter { it.kind==MockPhotoKind.BAR_GALLERY })
                        repository.approveForFixture(pending.applicationId,newBar)
                        val uris=pending.registrationPhotos.filter { it.kind==MockPhotoKind.MENU_CAPTURE }.map{it.uri}
                        if(uris.isNotEmpty()) repository.startPhotoImport(id,uris,OwnerMockFixtures.imageFixtures(emptyMap()))
                    },Modifier.fillMaxWidth())
                }
                step==FormStep.METHOD && bars.isNotEmpty() && pending==null -> {
                    if(bars.size==1) {
                        OwnerStatusLabel(if(snapshot!!.menuItems.any { it.barId==bars.first().barId }) "정상 영업" else "메뉴 확인 필요")
                        Text(bars.first().name,style=MaterialTheme.typography.headlineSmall)
                        OwnerActionButton("매장 관리",onManagerPreview,Modifier.fillMaxWidth())
                        OwnerActionButton("최초 검수",onFirstReview,Modifier.fillMaxWidth(),secondary=true)
                    }else{
                        Text("관리 매장 ${bars.size}개",style=MaterialTheme.typography.titleLarge)
                        bars.forEach { bar -> OwnerMenuRow(bar.name,bar.address,{
                            repository.selectBar(bar.barId);onManagerPreview()
                        },trailing="관리") }
                    }
                    OwnerActionButton("매장 추가", { step=FormStep.METHOD; selectedBarId=null; next() },Modifier.fillMaxWidth(),secondary=true)
                }
                else -> {
                    if((rejected!=null || canceled!=null) && step==FormStep.METHOD) {
                        OwnerStatusLabel(if(rejected!=null)"신청 거절" else "신청 취소",OwnerStatusTone.ERROR)
                        Text("새로운 신청을 시작할 수 있습니다.")
                    }
                    when(step) {
                        FormStep.METHOD -> {
                            Text("매장 사장님이신가요?",style=MaterialTheme.typography.headlineSmall)
                            OwnerActionButton("내 매장 등록하기",{next()},Modifier.fillMaxWidth())
                        }
                        FormStep.CERTIFICATE -> {
                            Text("등록 방식을 선택해주세요",style=MaterialTheme.typography.titleLarge)
                            OwnerActionButton("신규 매장 등록",{
                                save(MockRegistrationDraft(kind=MockApplicationKind.NEW_BAR));next()
                            },Modifier.fillMaxWidth())
                            OwnerActionButton("이미 등록된 매장 신청",{
                                save(MockRegistrationDraft(kind=MockApplicationKind.EXISTING_BAR));next()
                            },Modifier.fillMaxWidth(),secondary=true)
                        }
                        FormStep.BIZ -> {
                            if(draft.kind==MockApplicationKind.EXISTING_BAR) {
                                Text("신청할 기존 매장 선택",style=MaterialTheme.typography.titleLarge)
                                if(candidates.isEmpty()) {
                                    Text("검색 API가 연결되지 않아 Mock 기존 매장이 없습니다.")
                                    if(BuildConfigDebug()) OwnerActionButton("테스트 기존 매장 만들기 (Mock)", {
                                        repository.seedExistingCandidateForFixture(
                                            MockBar("fixture-existing-bar", "테스트 등록 매장", "테스트 주소")
                                        )
                                    },Modifier.fillMaxWidth(),secondary=true)
                                }
                                candidates.forEach { bar -> OwnerMenuRow(bar.name,bar.address,{
                                    selectedBarId=bar.barId;save(draft.copy(existingBarId=bar.barId));next()
                                }) }
                            } else {
                                Text("사업자등록증 선택",style=MaterialTheme.typography.titleLarge)
                                OwnerActionButton("갤러리에서 등록증 선택",{
                                    pickCertificate.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                                })
                                Text(certificateUri ?: "선택한 사진 없음")
                                draft.certificatePhoto?.let { PickerThumbnail(it.uri) }
                                OwnerActionButton("Mock OCR 샘플 채우기",{
                                    // Explicit fixed DEMO fixture, not image-derived OCR.
                                    save(draft.copy(
                                        businessNumberDigits="1234567890",
                                        representativeName="테스트 대표",
                                        openingDateIso="2024-01-01",
                                    ))
                                    next()
                                },enabled=certificateUri!=null)
                                OwnerActionButton("직접 입력",{next()},secondary=true)
                                Text("사업자등록증 AI 인식은 실행하지 않습니다. 아래 정보는 직접 확인·수정합니다.",
                                    style=MaterialTheme.typography.bodySmall)
                            }
                        }
                        FormStep.BAR -> {
                            Text("사업자 정보 확인 및 수정",style=MaterialTheme.typography.titleLarge)
                            Input("사업자등록번호",draft.businessNumberDigits,{save(draft.copy(businessNumberDigits=ownerPhoneDigits(it).take(10)))},KeyboardType.Number)
                            Input("대표자명",draft.representativeName,{save(draft.copy(representativeName=it))})
                            Input("개업일 (YYYY-MM-DD)",draft.openingDateIso,{save(draft.copy(openingDateIso=it))},KeyboardType.Number)
                            OwnerActionButton("샘플 정보 채우기 (Mock)", {
                                save(draft.copy(businessNumberDigits="1234567890", representativeName="테스트 대표",openingDateIso="2024-01-01"))
                            },Modifier.fillMaxWidth(),secondary=true)
                            OwnerActionButton("다음",{
                                if(draft.businessNumberDigits.length!=10 || draft.representativeName.isBlank() ||
                                   !Regex("\\d{4}-\\d{2}-\\d{2}").matches(draft.openingDateIso)) error="사업자 정보를 확인해주세요."
                                else next()
                            },Modifier.fillMaxWidth())
                        }
                        FormStep.VERIFICATION -> {
                            Text("사업자 정보 확인 결과",style=MaterialTheme.typography.titleLarge)
                            OwnerStatusLabel("Mock 검증 · 실제 조회 없음",OwnerStatusTone.ATTENTION)
                            Text("등록번호 ${draft.businessNumberDigits} · 대표자 ${draft.representativeName}")
                            Text("공공데이터 인증과 사업자등록증 OCR은 아직 연결되지 않았습니다. " +
                                "입력 정보가 실제로 유효한지 검증하지 않습니다.")
                            OwnerActionButton("정보 확인 완료 · 계속",::next,Modifier.fillMaxWidth())
                        }
                        FormStep.PHOTOS -> {
                            Text("매장 정보",style=MaterialTheme.typography.titleLarge)
                            if(draft.kind==MockApplicationKind.NEW_BAR){
                                Input("매장명",draft.proposedBarName,{save(draft.copy(proposedBarName=it))})
                                Input("주소",draft.proposedBarAddress,{save(draft.copy(proposedBarAddress=it))})
                            }else Text("기존 매장: ${(bars+candidates).firstOrNull{it.barId==draft.existingBarId}?.name?:"선택 필요"}")
                            OwnerActionButton("다음",{
                                if(draft.kind==MockApplicationKind.NEW_BAR &&
                                    (draft.proposedBarName.isBlank()||draft.proposedBarAddress.isBlank())) error="매장명과 주소를 입력해주세요."
                                else next()
                            },Modifier.fillMaxWidth())
                        }
                        FormStep.PHONE -> {
                            Text("대표 매장 사진",style=MaterialTheme.typography.titleLarge)
                            OwnerActionButton("갤러리에서 대표 사진 선택",{
                                pickCover.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                            })
                            draft.applicantGallery.forEach { PickerThumbnail(it.uri) }
                            OwnerActionButton("다음", ::next,Modifier.fillMaxWidth(),enabled=draft.applicantGallery.isNotEmpty())
                        }
                        FormStep.MENU -> {
                            Text("매장 전화번호",style=MaterialTheme.typography.titleLarge)
                            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                                Text("손님에게 보여요",style=MaterialTheme.typography.bodySmall)
                                TextButton(onClick={noShopPhone=!noShopPhone; if(noShopPhone)save(draft.copy(storePhone=""))}){
                                    Text(if(noShopPhone)"전화번호 입력하기" else "가게 전화가 없어요")
                                }
                            }
                            if(!noShopPhone) Input("매장 전화번호",draft.storePhone,{save(draft.copy(storePhone=ownerPhoneDigits(it)))},KeyboardType.Phone)
                            OwnerActionButton("다음",{
                                if(!validOwnerPhone(draft.storePhone))error="전화번호를 확인해주세요."
                                else next()
                            },Modifier.fillMaxWidth())
                        }
                        FormStep.CONTACT -> {
                            Text("메뉴판 사진",style=MaterialTheme.typography.titleLarge)
                            OwnerActionButton("Photo Picker로 사진 선택",{
                                pickMenu.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
                            },Modifier.fillMaxWidth())
                            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                                horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                                draft.initialMenuPhotos.forEachIndexed { i,photo ->
                                    Column { Text("${i+1}번 사진"); PickerThumbnail(photo.uri) }
                                }
                            }
                            Text("사진별 선택 순서는 유지됩니다. AI 분석은 승인 후 다음 단계에서 진행합니다.")
                            OwnerActionButton("다음",::next,Modifier.fillMaxWidth(),enabled=draft.initialMenuPhotos.isNotEmpty())
                        }
                        FormStep.REVIEW -> {
                            Text("연락받을 번호",style=MaterialTheme.typography.titleLarge)
                            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                                Text("운영팀만 봐요",style=MaterialTheme.typography.bodySmall)
                                TextButton(onClick={save(draft.copy(contactPhone=draft.storePhone))}){Text("매장 번호와 같아요")}
                            }
                            Input("연락받을 번호",draft.contactPhone,{save(draft.copy(contactPhone=ownerPhoneDigits(it)))},KeyboardType.Phone)
                            OwnerActionButton("신청 내용 확인",{
                                if(draft.contactPhone.isBlank()||!validOwnerPhone(draft.contactPhone)) error="연락받을 번호를 입력해주세요."
                                else step=FormStep.SUBMITTED
                            },Modifier.fillMaxWidth())
                        }
                        FormStep.SUBMITTED -> {
                            Text("신청 내용 확인",style=MaterialTheme.typography.titleLarge)
                            Text("매장: ${draft.proposedBarName.ifBlank { bars.firstOrNull{it.barId==draft.existingBarId}?.name.orEmpty() }}")
                            Text("연락받을 번호: ${draft.contactPhone}")
                            Text("등록 사진: ${draft.applicantGallery.size}장 · 메뉴판: ${draft.initialMenuPhotos.size}장")
                            if(busy) CircularProgressIndicator()
                            OwnerActionButton("신청 제출 (Mock)",{
                                if(!busy && snapshot?.applications?.none { it.status==MockApplicationStatus.PENDING }==true){
                                    busy=true
                                    try { repository.submitRegistrationDraftForFixture();step=FormStep.METHOD }
                                    catch(e:Exception){error=e.message}
                                    finally {busy=false}
                                }
                            },Modifier.fillMaxWidth(),enabled=!busy)
                        }
                    }
                    if(step==FormStep.METHOD) {
                        if(onComponents!=null) OwnerActionButton("공통 컴포넌트 점검", onComponents,
                            Modifier.fillMaxWidth(),secondary=true)
                        if(onLegacyDebugUpload!=null) OwnerActionButton("개발자 도구 · 기존 메뉴 업로드 테스트",
                            onLegacyDebugUpload,Modifier.fillMaxWidth(),secondary=true)
                    }
                    if(step!=FormStep.METHOD) {
                        OwnerActionButton("이전",::goBack,
                            Modifier.fillMaxWidth(),secondary=true)
                    }
                }
            }
            error?.let{Text(it,color=MaterialTheme.colorScheme.error)}
        }
    }
}
@Composable private fun Input(label:String,value:String,change:(String)->Unit,type:KeyboardType=KeyboardType.Text){
    OutlinedTextField(value=value,onValueChange=change,label={Text(label)},modifier=Modifier.fillMaxWidth(),
        keyboardOptions=KeyboardOptions(keyboardType=type),singleLine=true)
}
private fun persistUri(context:Context,uri:Uri){
    try { context.contentResolver.takePersistableUriPermission(uri,android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION) }
    catch (_:SecurityException){ /* platform picker may grant temporary URI only */ }
}
private fun BuildConfigDebug()=com.zerotoone.bottlemap.BuildConfig.DEBUG

/** Loads only a downsampled thumbnail; never decodes a full-resolution camera image on UI. */
@Composable private fun PickerThumbnail(uri:String) {
    val ctx=LocalContext.current
    val image by produceState<androidx.compose.ui.graphics.ImageBitmap?>(initialValue=null,uri) {
        value=withContext(Dispatchers.IO) {
            try {
                ctx.contentResolver.openInputStream(Uri.parse(uri))?.use { input ->
                    BitmapFactory.decodeStream(input,null,BitmapFactory.Options().apply { inSampleSize=8 })?.asImageBitmap()
                }
            }catch (_:Exception){null}
        }
    }
    if(image!=null) Image(bitmap=image!!, contentDescription="선택한 사진",
        modifier=Modifier.size(120.dp),contentScale=ContentScale.Crop)
    else Text("선택한 사진 · 미리보기 불가",style=MaterialTheme.typography.bodySmall)
}
