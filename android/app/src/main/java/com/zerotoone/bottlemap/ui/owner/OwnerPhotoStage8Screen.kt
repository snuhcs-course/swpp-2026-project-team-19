package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.drawscope.Fill
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.unit.sp
import com.zerotoone.bottlemap.data.owner.*
import org.json.JSONObject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Only save the owner-confirmed product draft, not inferred OCR data. */
private fun encodeReviewDraft(draft: MockNewProductDraft): String = JSONObject().apply {
    put("name",draft.name)
    put("brandId",draft.brandId)
    put("brandName",draft.brandName)
    put("category",draft.category)
    put("ageYears",draft.ageYears)
    put("editionName",draft.editionName)
    put("abvPercent",draft.abvPercent)
    put("otherAlcoholKind",draft.otherAlcoholKind)
}.toString()
private fun decodeReviewDraft(value: String): MockNewProductDraft? = runCatching {
    val obj=JSONObject(value)
    fun optional(key:String)=if(obj.isNull(key))null else obj.optString(key).ifBlank{null}
    MockNewProductDraft(
        name=obj.getString("name"),
        brandId=optional("brandId"), brandName=optional("brandName"),
        category=obj.optString("category","whisky"),
        ageYears=if(obj.isNull("ageYears"))null else obj.getInt("ageYears"),
        editionName=optional("editionName"),
        abvPercent=if(obj.isNull("abvPercent"))null else obj.getDouble("abvPercent"),
        otherAlcoholKind=optional("otherAlcoholKind")
    )
}.getOrNull()
internal data class Stage8Counts(val photos: Int, val lines: Int, val reviewed: Int, val existing: Int,
    val newCandidates: Int) {
    val remaining: Int get() = lines - reviewed
}
internal fun stage8Counts(job: MockMenuImport, s: MockOwnerSnapshot): Stage8Counts {
    val ids=s.menuItems.filter { it.barId==job.barId }.map { it.productId }.toSet()
    val lines=job.images.flatMap { it.lines }
    return Stage8Counts(job.images.size,lines.size,lines.count { it.decision!=null },
        lines.count {it.kind == MockLineKind.PRODUCT &&
            (it.suggestedProductId in ids || it.candidateProductIds.any { id->id in ids }) &&
            it.decision?.kind !in listOf(MockDecisionKind.EXCLUDE,MockDecisionKind.CONFIRM_NON_PRODUCT)},
        lines.count {it.kind == MockLineKind.PRODUCT &&
            it.suggestedProductId !in ids && it.candidateProductIds.none { id->id in ids } &&
            it.decision?.kind !in listOf(MockDecisionKind.EXCLUDE,MockDecisionKind.CONFIRM_NON_PRODUCT)})
}
// One source of truth for EVERY entry into an extracted line (start/next/previous/back).
// A price-less known product is a price-entry page; an unmatched line is a new product.
internal fun stage8ReviewDestination(line: MockExtractedLine): String = when {
    line.kind == MockLineKind.NON_PRODUCT -> "line"
    line.suggestedProductId == null && line.candidateProductIds.isEmpty() -> "new"
    line.options.isEmpty() || line.options.any { it.priceKrw <= 0 } -> "price"
    else -> "line"
}
private fun reviewSnap(s: MockOwnerLoadState): MockOwnerSnapshot? = when(s) {
    is MockOwnerLoadState.Ready->s.snapshot
    is MockOwnerLoadState.Empty->s.snapshot
    else->null
}
@Composable private fun St8Button(text: String, enabled: Boolean=true, click:()->Unit) {
    Button(onClick=click,enabled=enabled,modifier=Modifier.fillMaxWidth().height(55.dp),
        shape=RoundedCornerShape(12.dp),colors=ButtonDefaults.buttonColors(
            containerColor=V4Color.primary,contentColor=V4Color.background)) {
        Text(text,fontSize=15.sp,fontWeight=FontWeight.Bold)
    }
}
@Composable private fun St8Secondary(text: String, click:()->Unit) {
    OutlinedButton(onClick=click,modifier=Modifier.fillMaxWidth().height(56.dp),
        shape=RoundedCornerShape(12.dp),
        border=androidx.compose.foundation.BorderStroke(1.dp,V4Color.line),
        colors=ButtonDefaults.outlinedButtonColors(
            containerColor=V4Color.surface,contentColor=V4Color.text)) {
        Text(text,fontSize=15.sp,fontWeight=FontWeight.Bold)
    }
}
@Composable private fun St8Field(text: String, value: String, change:(String)->Unit, digits:Boolean=false) {
    OutlinedTextField(value=value,onValueChange={change(if(digits)it.filter(Char::isDigit) else it)},
        label={Text(text)},singleLine=true,modifier=Modifier.fillMaxWidth(),
        colors=OutlinedTextFieldDefaults.colors(focusedTextColor=V4Color.text,
            unfocusedTextColor=V4Color.text,focusedBorderColor=V4Color.primary))
}
@Composable private fun St8NewField(title:String, value:String,
    change:(String)->Unit, placeholder:String="",digits:Boolean=false) {
    Column(Modifier.fillMaxWidth(),verticalArrangement=Arrangement.spacedBy(7.dp)) {
        Text(title,color=V4Color.sub,fontSize=12.sp)
        OutlinedTextField(value=value,onValueChange={
            change(if(digits)it.filter(Char::isDigit) else it)
        },modifier=Modifier.fillMaxWidth(),singleLine=true,
            keyboardOptions=KeyboardOptions(keyboardType=if(digits)
                KeyboardType.Number else KeyboardType.Text),
            placeholder={Text(placeholder,fontSize=15.sp)},
            colors=OutlinedTextFieldDefaults.colors(
                focusedTextColor=V4Color.text,unfocusedTextColor=V4Color.text,
                focusedBorderColor=V4Color.primary,unfocusedBorderColor=V4Color.line,
                focusedContainerColor=V4Color.background,
                unfocusedContainerColor=V4Color.background))
    }
}
@Composable private fun St8Card(content:@Composable ColumnScope.()->Unit) {
    Column(Modifier.fillMaxWidth().background(V4Color.surface,RoundedCornerShape(12.dp))
        .border(1.dp,V4Color.line,RoundedCornerShape(12.dp)).padding(14.dp),
        verticalArrangement=Arrangement.spacedBy(9.dp),content=content)
}
/** PDF 87/89: compact back navigation and a truly centered item index. */
@Composable private fun St8PublishSteps(active:Int) {
    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(5.dp)) {
        listOf("사진 올리기","읽기","확인","더하기").forEachIndexed { i,label->
            Column(Modifier.weight(1f)) {
                Box(Modifier.fillMaxWidth().height(3.dp).background(
                    if(i<=active)V4Color.primary else V4Color.line))
                Spacer(Modifier.height(7.dp))
                Text(label,color=if(i==active)V4Color.primary else V4Color.sub,
                    fontSize=10.sp)
            }
        }
    }
}
@Composable private fun St8CountCard(firstLabel:String,firstCount:Int,
    secondLabel:String,secondCount:Int,secondSuffix:String="줄") {
    St8Card {
        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {
            Text(firstLabel,color=V4Color.sub,fontSize=14.sp)
            Text("${firstCount}${secondSuffix}",color=V4Color.text,fontWeight=FontWeight.Bold)
        }
        HorizontalDivider(color=V4Color.line)
        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {
            Text(secondLabel,color=V4Color.sub,fontSize=14.sp)
            Text("${secondCount}${secondSuffix}",color=V4Color.text,fontWeight=FontWeight.Bold)
        }
    }
}
/** The v4 HTML #i-edit geometry, not a rotated rectangle approximation. */
@Composable private fun V4PencilIcon(modifier: Modifier = Modifier.size(22.dp),
    color: Color=V4Color.primary) {
    Canvas(modifier) {
        val u=size.width/24f
        val pencil=Path().apply {
            moveTo(4f*u,20f*u)
            lineTo(8f*u,20f*u)
            lineTo(19f*u,9f*u)
            lineTo(15f*u,5f*u)
            lineTo(4f*u,16f*u)
            close()
            moveTo(13f*u,7f*u)
            lineTo(17f*u,11f*u)
        }
        drawPath(pencil,color,style=Stroke(
            width=1.8f*u,cap=androidx.compose.ui.graphics.StrokeCap.Round,
            join=androidx.compose.ui.graphics.StrokeJoin.Round))
    }
}
@Composable private fun V4PriceBadge(label: String, color:Color=V4Color.primary) {
    Box(Modifier.background(Color(0xFF4A382A),RoundedCornerShape(100))
        .padding(horizontal=9.dp,vertical=3.dp)) {
        Text(label,color=color,fontSize=11.sp,maxLines=1)
    }
}
@Composable private fun V4ReviewStateBadge(label: String) {
    val isSkip=label=="건너뜀"
    Box(Modifier.background(if(isSkip)Color(0xFF423B36) else Color(0xFF463D34),
        RoundedCornerShape(100)).padding(horizontal=8.dp,vertical=3.dp)){
        Text(label,color=V4Color.sub,fontSize=11.sp,maxLines=1)
    }
}
@Composable private fun V4ExistingPriceRow(
    name:String,source:String,menuPrice:Int?,currentPrice:Int?,
) {
    val different=menuPrice!=null && currentPrice!=null && menuPrice!=currentPrice
    Row(Modifier.fillMaxWidth().padding(vertical=7.dp),
        verticalAlignment=Alignment.CenterVertically,
        horizontalArrangement=Arrangement.spacedBy(10.dp)) {
        Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(6.dp)) {
            Text(name,color=V4Color.text,fontSize=16.sp,maxLines=2)
            Row(verticalAlignment=Alignment.CenterVertically,
                horizontalArrangement=Arrangement.spacedBy(6.dp)) {
                Text(source,color=V4Color.sub,fontSize=11.sp)
                if(different) V4PriceBadge("가격이 달라요",Color(0xFFD5B991))
            }
        }
        Column(horizontalAlignment=Alignment.End,verticalArrangement=Arrangement.spacedBy(6.dp)){
            Text(menuPrice?.let {
                    if(different) "메뉴판 %,d원".format(it) else "%,d원".format(it)
                } ?:currentPrice?.let{"%,d원".format(it)} ?: "가격 확인 필요",
                color=V4Color.text,fontSize=13.sp)
            if(different)Text("지금 %,d원".format(currentPrice),
                color=V4Color.sub,fontSize=13.sp,
                textDecoration=TextDecoration.LineThrough)
        }
    }
    HorizontalDivider(color=V4Color.line)
}
@Composable private fun V4ExistingHint() {
    Row(Modifier.fillMaxWidth().border(1.dp,Color(0xFF75583D),
        RoundedCornerShape(12.dp)).background(Color(0xFF302822),RoundedCornerShape(12.dp))
        .padding(15.dp),horizontalArrangement=Arrangement.spacedBy(15.dp),
        verticalAlignment=Alignment.CenterVertically) {
        V4PencilIcon(Modifier.size(22.dp))
        Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)){
            Text("가격은 메뉴 직접 편집에서 바꿔요",
                color=V4Color.text,fontWeight=FontWeight.Bold,fontSize=14.sp)
            Text("확인을 다 끝낸 뒤 완료 화면에서 바로 갈 수 있어요.",
                color=V4Color.sub,fontSize=11.sp)
        }
    }
}
/** Secondary review actions sit below the source excerpt, never in the bottom CTA. */
@Composable private fun St8ReviewHeading(title: String, exclude:()->Unit) {
    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(4.dp),
        verticalAlignment=Alignment.CenterVertically) {
        Text(title,modifier=Modifier.weight(1f),color=V4Color.text,
            fontSize=20.sp,fontWeight=FontWeight.Bold,maxLines=2)
        listOf("위스키가 아니에요","이번 줄 제외").forEach { label ->
            Box(Modifier.height(30.dp).border(1.dp,V4Color.primary,
                RoundedCornerShape(100)).clickable(onClick=exclude)
                .padding(horizontal=7.dp),contentAlignment=Alignment.Center) {
                Text(label,color=V4Color.primary,fontSize=10.sp,maxLines=1)
            }
        }
    }
}
@Composable private fun St8ReviewToolbar(step: Int, total: Int, back: () -> Unit) {
    Box(Modifier.fillMaxWidth().height(48.dp)) {
        TextButton(onClick=back,modifier=Modifier.align(Alignment.CenterStart)
            .padding(start=14.dp).size(48.dp)) {
            Text("←",color=V4Color.text,fontSize=26.sp)
        }
        Text("${step} / ${total}",color=V4Color.sub,fontWeight=FontWeight.Bold,
            fontSize=14.sp,modifier=Modifier.align(Alignment.Center))
    }
}
/** Exit an in-progress photo review without modifying any review decision. */
@Composable private fun St8ReviewHome(onLater:()->Unit) {
    // The reference icon has a nearly square silhouette and rounded corners.
    // Its visual bottom shares the extracted-line label's bottom alignment.
    Box(Modifier.size(31.dp).testTag("stage8-review-home")
        .semantics { contentDescription="나중에 하기 · 메뉴 관리로" }
        .clickable(onClick=onLater),contentAlignment=Alignment.BottomCenter) {
        Canvas(Modifier.size(29.dp)) {
            val u=size.width/24f
            val home=Path().apply {
                moveTo(3f*u,11f*u)
                lineTo(11.3f*u,3.4f*u)
                quadraticBezierTo(12f*u,2.8f*u,12.7f*u,3.4f*u)
                lineTo(21f*u,11f*u)
                moveTo(5.4f*u,10.7f*u)
                lineTo(5.4f*u,20.7f*u)
                quadraticBezierTo(5.4f*u,21.7f*u,6.4f*u,21.7f*u)
                lineTo(10f*u,21.7f*u)
                lineTo(10f*u,16.4f*u)
                quadraticBezierTo(10f*u,15f*u,11.4f*u,15f*u)
                lineTo(12.6f*u,15f*u)
                quadraticBezierTo(14f*u,15f*u,14f*u,16.4f*u)
                lineTo(14f*u,21.7f*u)
                lineTo(17.6f*u,21.7f*u)
                quadraticBezierTo(18.6f*u,21.7f*u,18.6f*u,20.7f*u)
                lineTo(18.6f*u,10.7f*u)
            }
            drawPath(home,V4Color.primary,style=Stroke(
                width=2.35f*u,cap=androidx.compose.ui.graphics.StrokeCap.Round,
                join=androidx.compose.ui.graphics.StrokeJoin.Round))
        }
    }
}
@Composable private fun St8Bottle() {
    Canvas(Modifier.width(40.dp).height(53.dp)) {
        val u=size.width/40f
        drawRect(Color(0xFFA86E36),topLeft=Offset(16f*u,8f*u),
            size=Size(8f*u,5f*u))
        drawRoundRect(Color(0xFF986128),topLeft=Offset(11f*u,14f*u),
            size=Size(18f*u,35f*u),cornerRadius=androidx.compose.ui.geometry.CornerRadius(4f*u))
        drawRoundRect(Color(0xFFDFC08C),topLeft=Offset(14f*u,27f*u),
            size=Size(12f*u,14f*u),cornerRadius=androidx.compose.ui.geometry.CornerRadius(1f*u))
        drawRect(Color(0xFFC99D6B),topLeft=Offset(16f*u,5f*u),
            size=Size(8f*u,4f*u))
    }
}
@Composable private fun St8RecognizedStrip(photo: MockPhotoExtraction, line: MockExtractedLine,
    defaultPourMl: Int?=null, onLater:()->Unit, onPhoto: ()->Unit) {
    val price=line.decision?.correctedOptions?.firstOrNull()?.priceKrw
        ?:line.options.firstOrNull()?.priceKrw
    val pour=line.decision?.correctedOptions?.firstOrNull()?.pourMl
        ?:line.options.firstOrNull()?.pourMl ?: defaultPourMl
    val ordinal=listOf("첫째","둘째","셋째","넷째","다섯째","여섯째","일곱째")
    val photoRow=photo.lines.indexOfFirst { it.extractedItemId==line.extractedItemId }
    Row(Modifier.fillMaxWidth().height(31.dp),
        verticalAlignment=Alignment.Bottom,horizontalArrangement=Arrangement.SpaceBetween) {
        Text("메뉴판 ${photo.imageOrder} · ${ordinal.getOrElse(photoRow){(photoRow+1).toString()+"번째"}} 줄",
            modifier=Modifier.weight(1f).padding(bottom=1.dp)
                .testTag("stage8-source-line-label"),
            color=V4Color.sub,fontSize=12.sp)
        St8ReviewHome(onLater)
    }
    Row(Modifier.fillMaxWidth().heightIn(min=50.dp).background(Color(0xFFE7DDCB),
        RoundedCornerShape(9.dp)).padding(horizontal=16.dp,vertical=10.dp),
        verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(6.dp)) {
        Text(line.sourceText,color=Color(0xFF2A231D),fontSize=17.sp,
            fontWeight=FontWeight.Bold,maxLines=2)
        Canvas(Modifier.weight(1f).height(1.dp)) {
            drawLine(Color(0xFFA99C8A),Offset.Zero,Offset(size.width,0f),
                strokeWidth=1.5.dp.toPx(),pathEffect=PathEffect.dashPathEffect(
                    floatArrayOf(3.dp.toPx(),3.dp.toPx())))
        }
        Text(if(price!=null&&price>0)"%,d".format(price)
            else (pour?.let{"${it}ml"} ?: "가격 확인 필요"),
            color=Color(0xFF2A231D),fontSize=17.sp,fontWeight=FontWeight.Bold)
    }
    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,
        verticalAlignment=Alignment.CenterVertically) {
        Text((if(price!=null&&price>0)"%,d원".format(price) else "가격 확인 필요")+
            (pour?.let{"  ${it}ml"} ?: ""),
            color=V4Color.text,fontSize=14.sp)
        TextButton(onClick=onPhoto,contentPadding=PaddingValues(0.dp)){
            Text("원본 사진 보기",color=V4Color.sub,fontSize=14.sp)
        }
    }
}
/** Every count and item comes from the Stage 7 persisted import. No fixed PDF example data. */
@Composable internal fun OwnerPhotoStage8Screen(
    state: MockOwnerLoadState, vm: OwnerMockViewModel,
    onBack:()->Unit, onHome:()->Unit,
    resumeFromMenu: Boolean=false,
) {
    val s=reviewSnap(state)
    val barId=s?.selectedBarId ?: s?.bars?.firstOrNull()?.barId
    val job=s?.imports?.lastOrNull { it.barId==barId }
    // Non-product lines must remain reviewable or they block final publication.
    val all=job?.images?.flatMap { photo -> photo.lines.map { photo to it } }.orEmpty()
    val counts=if(job!=null && s!=null)stage8Counts(job,s) else null
    val focusManager=LocalFocusManager.current
    val keyboardController=LocalSoftwareKeyboardController.current
    var screen by rememberSaveable(job?.menuImportId) {
        mutableStateOf(if(resumeFromMenu) {
            if(all.isNotEmpty() && all.all{it.second.decision!=null}) "publish"
            else "incomplete"
        } else "summary")
    }
    var position by rememberSaveable(job?.menuImportId){mutableIntStateOf(0)}
    var error by rememberSaveable {mutableStateOf<String?>(null)}
    var publishConfirmed by rememberSaveable {mutableStateOf(false)}
    var selectedProductId by rememberSaveable(job?.menuImportId) { mutableStateOf<String?>(null) }
    var selectedForLineId by rememberSaveable(job?.menuImportId) { mutableStateOf<String?>(null) }
    var chosenCategory by rememberSaveable(job?.menuImportId) { mutableStateOf("whisky") }
    var choosingOther by rememberSaveable(job?.menuImportId) { mutableStateOf(false) }
    var catalogQuery by rememberSaveable(job?.menuImportId) { mutableStateOf("") }
    var pendingNewDraftEncoded by rememberSaveable(job?.menuImportId) {
        mutableStateOf<String?>(null)
    }
    var pendingNewDraftLineId by rememberSaveable(job?.menuImportId) {
        mutableStateOf<String?>(null)
    }
    val pendingNewDraft=remember(pendingNewDraftEncoded) {
        pendingNewDraftEncoded?.let(::decodeReviewDraft)
    }
    var showRestartWarning by rememberSaveable { mutableStateOf(false) }
    var pageHistory by rememberSaveable(job?.menuImportId) { mutableStateOf(listOf<String>()) }
    fun visit(page:String, target:Int=position) {
        if(screen!=page || position!=target) {
            pageHistory=pageHistory+("$screen|$position")
            screen=page
            position=target
        }
    }
    fun destinationFor(line:MockExtractedLine):String {
        val knownIds=(listOfNotNull(line.suggestedProductId)+line.candidateProductIds)
        val available=knownIds.any { id->
            s?.products?.any {it.productId==id && it.isActive}==true
        }
        // Stale or inactive catalog IDs must never be auto-selected.
        return if(line.kind==MockLineKind.PRODUCT && knownIds.isNotEmpty() &&
            !available) "catalog" else stage8ReviewDestination(line)
    }
    fun visitLine(target:Int) {
        all.getOrNull(target)?.second?.takeUnless {it.mockAutoAccepted}
            ?.let {visit(destinationFor(it),target)}
    }
    fun backPage() {
        val last=pageHistory.lastOrNull()
        if(last==null) onBack() else {
            pageHistory=pageHistory.dropLast(1)
            screen=last.substringBeforeLast("|")
            position=last.substringAfterLast("|").toIntOrNull() ?: position
        }
    }
    val pair=all.getOrNull(position)
    // Normalize legacy saved "line" destinations after a configuration change/re-entry.
    LaunchedEffect(job?.menuImportId,position,screen) {
        if(screen=="line") {
            pair?.second?.let { line ->
                val destination=destinationFor(line)
                if(destination!="line")screen=destination
            }
        }
    }
    LaunchedEffect(pair?.second?.extractedItemId) {
        val lineId=pair?.second?.extractedItemId
        if(selectedForLineId!=lineId) {
            selectedProductId=pair?.second?.decision?.productId ?:
                pair?.second?.suggestedProductId
            selectedForLineId=lineId
            chosenCategory=pair?.second?.decision?.newProduct?.category ?: "whisky"
            choosingOther=false
        }
    }
    fun next() {
        selectedProductId=null
        pendingNewDraftEncoded=null
        pendingNewDraftLineId=null
        val target=all.indices.firstOrNull{it>position && all[it].second.decision==null}
            ?: all.indices.firstOrNull{it!=position && all[it].second.decision==null}
        if(target==null) visit("publish") else visitLine(target)
    }
    if(showRestartWarning) AlertDialog(
        onDismissRequest={showRestartWarning=false},
        title={Text("처음부터 검수할까요?")},
        text={Text("기존 검수 결과를 모두 초기화해요.")},
        confirmButton={TextButton(onClick={
            showRestartWarning=false
            runCatching {job?.let {vm.resetPhotoReview(it.menuImportId,it.reviewVersion)}}
                .onSuccess {
                    error=null
                    pageHistory=emptyList()
                    position=0
                    selectedProductId=null
                    pendingNewDraftEncoded=null
                    pendingNewDraftLineId=null
                    selectedForLineId=null
                    screen="summary"
                }.onFailure {error=it.message}
        }){Text("처음부터 검수")}},
        dismissButton={TextButton(onClick={showRestartWarning=false}){Text("취소",color=V4Color.text)}}
    )
    Column(Modifier.fillMaxSize().background(V4Color.background)) {
        val back: () -> Unit = { if(screen=="summary") onHome() else backPage() }
        if(screen=="catalog") {
            Row(Modifier.fillMaxWidth().height(66.dp)
                .padding(start=17.dp,end=14.dp,top=10.dp,bottom=0.dp),
                horizontalArrangement=Arrangement.spacedBy(9.dp),
                verticalAlignment=Alignment.CenterVertically) {
                TextButton(onClick=back,contentPadding=PaddingValues(0.dp),
                    modifier=Modifier.width(40.dp)) {
                    Text("←",color=V4Color.text,fontSize=25.sp)
                }
                BasicTextField(value=catalogQuery,onValueChange={catalogQuery=it},
                    singleLine=true,textStyle=TextStyle(color=V4Color.text,fontSize=16.sp),
                    modifier=Modifier.weight(1f).offset(y=7.dp),
                    decorationBox={field ->
                        Row(Modifier.fillMaxWidth().height(45.dp)
                            .border(1.dp,V4Color.line,RoundedCornerShape(14.dp))
                            .padding(horizontal=12.dp),
                            verticalAlignment=Alignment.CenterVertically,
                            horizontalArrangement=Arrangement.spacedBy(9.dp)){
                            Text("⌕",color=V4Color.sub,fontSize=24.sp)
                            Box(Modifier.weight(1f)) {
                                if(catalogQuery.isBlank())
                                    Text("메뉴 이름 검색",color=V4Color.sub,fontSize=16.sp)
                                field()
                            }
                        }
                    })
            }
        } else if(screen in listOf("line","edit","new","price") && counts!=null)
            St8ReviewToolbar(position+1,counts.lines,back)
        else V4Toolbar(null,back)
        if (s==null || job==null || job.status !in
            listOf(MockImportStatus.READY_FOR_REVIEW,MockImportStatus.APPLIED)) {
            Box(Modifier.weight(1f),contentAlignment=Alignment.Center) {
                Text(when(state) {
                    MockOwnerLoadState.Loading -> "검수 정보를 불러오고 있어요."
                    is MockOwnerLoadState.Error -> state.message
                    else -> "검수 가능한 메뉴판 작업이 없어요."
                },color=V4Color.text)
            }
            if(state is MockOwnerLoadState.Error) {
                St8Button("다시 시도",click=vm::retry)
            }
            St8Button("내 매장으로 돌아가기",click=onHome)
            return@Column
        }
        LaunchedEffect(job.status) {
            if(job.status==MockImportStatus.APPLIED)visit("done")
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState())
            .padding(start=19.dp,end=19.dp,
                top=if(screen in listOf("line","new","edit","price"))0.dp else 3.dp,
                bottom=19.dp),
            verticalArrangement=Arrangement.spacedBy(10.dp)) {
            if(screen=="summary") {
                Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(5.dp)){
                    listOf("사진 올리기","읽기","확인","더하기").forEachIndexed{ i,label->
                        Column(Modifier.weight(1f)){
                            Box(Modifier.fillMaxWidth().height(3.dp).background(
                                if(i<=2)V4Color.primary else V4Color.line))
                            Text(label,color=V4Color.sub,fontSize=10.sp)
                        }
                    }
                }
                Text("메뉴판 "+counts!!.photos+"장 · "+counts.lines+"줄 인식",
                    color=V4Color.sub,fontSize=13.sp)
                Text(counts.remaining.toString()+"줄 확인",color=V4Color.text,
                    fontWeight=FontWeight.Bold,fontSize=26.sp)
                val bar=s.bars.firstOrNull{it.barId==barId}
                St8Card {
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {
                        Text("기본 잔 용량",color=V4Color.text,fontWeight=FontWeight.Bold)
                        Text(bar?.defaultPourMl?.let { it.toString()+"ml" } ?: "미설정",
                            color=V4Color.sub,fontSize=12.sp)
                    }
                    var pour by rememberSaveable(barId){mutableStateOf(bar?.defaultPourMl?.toString().orEmpty())}
                    Row(verticalAlignment=Alignment.CenterVertically,
                        horizontalArrangement=Arrangement.spacedBy(7.dp)) {
                        OutlinedTextField(pour,{pour=it.filter(Char::isDigit).take(3)},
                            modifier=Modifier.width(100.dp),singleLine=true,
                            placeholder={Text("예: 30")},colors=OutlinedTextFieldDefaults.colors(
                                focusedTextColor=V4Color.text,unfocusedTextColor=V4Color.text))
                        Text("ml",color=V4Color.text)
                        Box(Modifier.size(width=52.dp,height=46.dp),
                            contentAlignment=Alignment.Center) {
                            Box(Modifier.size(width=43.dp,height=26.dp)
                                .border(1.dp,V4Color.line,RoundedCornerShape(7.dp))
                                .clickable {
                                    val n=pour.toIntOrNull()
                                    if(bar!=null && (pour.isBlank() || n!=null && n in 1..999)){
                                        vm.saveBar(bar.copy(defaultPourMl=n));error=null
                                        focusManager.clearFocus()
                                        keyboardController?.hide()
                                    } else error="1~999ml로 입력해 주세요."
                                },contentAlignment=Alignment.Center) {
                                Text("저장",color=V4Color.primary,fontSize=14.sp,
                                    fontWeight=FontWeight.Medium)
                            }
                        }
                    }
                    Text("용량 표시가 없는 잔에 적용해요.",color=V4Color.sub,fontSize=11.sp)
                }
                St8Card {
                    Text("자동 인식 신규 메뉴 "+counts.newCandidates+"줄 ›",
                        color=V4Color.text,fontWeight=FontWeight.Bold,
                        modifier=Modifier.fillMaxWidth().clickable {visit("auto")})
                }
                St8Card {
                    Text("이미 등록된 메뉴 "+counts.existing+"줄 ›",
                        color=V4Color.text,fontWeight=FontWeight.Bold,
                        modifier=Modifier.fillMaxWidth().clickable {visit("existing")})
                }
            } else if(screen=="auto" || screen=="existing") {
                Text(if(screen=="auto")"새로 더할 메뉴 "+counts!!.newCandidates+"줄"
                    else if(counts!!.existing==0)"이미 있는 메뉴 5줄 · UI 예시"
                    else "이미 있는 메뉴 "+counts.existing+"줄",
                    color=V4Color.text,fontSize=24.sp,fontWeight=FontWeight.Bold)
                val existingIds=s.menuItems.filter {it.barId==job.barId}.map{it.productId}.toSet()
                val subset=all.withIndex().filter{(_,entry)->
                    val line=entry.second
                    val known=line.suggestedProductId in existingIds ||
                        line.candidateProductIds.any{it in existingIds}
                    line.kind==MockLineKind.PRODUCT &&
                        line.decision?.kind !in listOf(
                            MockDecisionKind.EXCLUDE,MockDecisionKind.CONFIRM_NON_PRODUCT) &&
                        (if(screen=="existing")known else !known)
                }
                if(subset.isEmpty()) Text("해당하는 메뉴가 없어요.",color=V4Color.sub)
                subset.forEach { entry->
                    val line=entry.value.second
                    val matchingId=(listOfNotNull(line.suggestedProductId)+
                        line.candidateProductIds).firstOrNull{ id->
                        s.menuItems.any{it.barId==job.barId && it.productId==id}
                    }
                    val registered=s.menuItems.firstOrNull{it.barId==job.barId &&
                        it.productId==matchingId}
                    val found=line.decision?.correctedOptions?.firstOrNull()?.priceKrw ?:
                        line.options.firstOrNull()?.priceKrw
                    if(screen=="existing") {
                        V4ExistingPriceRow(line.sourceText,
                            "메뉴판 ${entry.value.first.imageOrder} · 인식한 줄",
                            found,registered?.options?.firstOrNull()?.priceKrw)
                    } else {
                        Column(Modifier.fillMaxWidth().clickable{
                            visitLine(entry.index)
                        }.padding(vertical=2.dp)) {
                            Row(Modifier.fillMaxWidth(),
                                horizontalArrangement=Arrangement.SpaceBetween,
                                verticalAlignment=Alignment.CenterVertically) {
                                Text(line.sourceText,color=V4Color.text,fontSize=17.sp,
                                    modifier=Modifier.weight(1f))
                                Text(found?.takeIf{it>0}?.let{"%,d원".format(it)}
                                    ?: "가격 확인 필요",color=V4Color.text,fontSize=13.sp)
                            }
                            Text("메뉴판 ${entry.value.first.imageOrder} · 신규 등록 후보",
                                color=V4Color.sub,fontSize=11.sp)
                            HorizontalDivider(color=V4Color.line)
                        }
                    }
                }
            } else if(screen=="catalog" && pair!=null) {
                val q=catalogQuery.trim()
                val candidates=s.products.filter { p ->
                    p.isActive && q.isNotEmpty() && (
                        p.displayName.contains(q,ignoreCase=true) ||
                        (q.contains("잭다니엘") && p.displayName.contains("Jack Daniel",ignoreCase=true)) ||
                        s.brands.firstOrNull {it.brandId==p.brandId}?.name
                            ?.contains(q,ignoreCase=true)==true)
                }
                Text("카탈로그에서 찾은 메뉴 ${candidates.size}개",color=V4Color.sub,
                    fontSize=12.sp)
                candidates.forEach { product ->
                    Row(Modifier.fillMaxWidth()
                        .background(V4Color.surface,RoundedCornerShape(14.dp))
                        .border(1.dp,V4Color.line,RoundedCornerShape(14.dp))
                        .clickable {
                            selectedProductId=product.productId
                            val line=pair.second
                            if(line.options.isEmpty() || line.options.any{it.priceKrw<=0}) {
                                visit("price")
                            } else runCatching {
                                vm.review(job.menuImportId,line.extractedItemId,
                                    job.reviewVersion,MockReviewDecision(
                                        MockDecisionKind.SELECT_PRODUCT,productId=product.productId,
                                        correctedOptions=line.options))
                            }.onSuccess {error=null;next()}.onFailure {error=it.message}
                        }.padding(horizontal=13.dp,vertical=12.dp),
                        verticalAlignment=Alignment.CenterVertically,
                        horizontalArrangement=Arrangement.spacedBy(11.dp)) {
                        St8Bottle()
                        Column(Modifier.weight(1f)) {
                            val brand=s.brands.firstOrNull {it.brandId==product.brandId}?.name
                            Text(brand ?: product.displayName,color=V4Color.text,
                                fontSize=15.sp,fontWeight=FontWeight.Bold)
                            Text(product.displayName.removePrefix((brand ?: "")+" "),
                                color=V4Color.text,fontSize=13.sp)
                            if(product.displayName.contains("Old No.7"))
                                Text("이미 메뉴에 있을 수 있어요 · 선택 전 확인",
                                    color=V4Color.sub,fontSize=11.sp)
                        }
                    }
                }
            } else if(screen=="line" && pair!=null) {
                val (photo,line)=pair
                var openPhoto by remember {mutableStateOf(false)}
                St8RecognizedStrip(photo,line,onLater=onHome){openPhoto=true}
                if(openPhoto)Stage8SourcePhoto(photo,line.sourceBox){openPhoto=false}
                var categoryPopup by remember {mutableStateOf(false)}
                St8ReviewHeading(
                    if(line.candidateProductIds.size>1)"어느 메뉴인가요?" else "이 메뉴가 맞나요?"
                ) {runCatching{vm.review(job.menuImportId,line.extractedItemId,
                        job.reviewVersion,MockReviewDecision(MockDecisionKind.EXCLUDE))}
                        .onSuccess{pendingNewDraftEncoded=null;error=null;next()}
                        .onFailure{error=it.message}}
                val candidates=(listOfNotNull(line.suggestedProductId)+line.candidateProductIds)
                    .distinct().mapNotNull{id->s.products.firstOrNull{
                        it.productId==id && it.isActive}}
                if(!choosingOther && chosenCategory=="whisky")candidates.forEach{product->
                    Row(Modifier.fillMaxWidth()
                        .background(V4Color.surface,RoundedCornerShape(16.dp))
                        .border(1.dp,if(selectedProductId==product.productId)
                            V4Color.primary else V4Color.line,RoundedCornerShape(16.dp))
                        .clickable {
                            if(line.options.isEmpty() || line.options.any{it.priceKrw<=0}) {
                                selectedProductId=product.productId;visit("price")
                            } else runCatching {vm.review(job.menuImportId,line.extractedItemId,
                                job.reviewVersion,MockReviewDecision(MockDecisionKind.SELECT_PRODUCT,
                                    productId=product.productId,
                                    correctedOptions=line.decision?.correctedOptions ?: line.options))}
                                .onSuccess{error=null;next()}.onFailure{error=it.message}
                        }
                        .padding(horizontal=15.dp,vertical=12.dp),
                        verticalAlignment=Alignment.CenterVertically,
                        horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                        St8Bottle()
                        Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(3.dp)) {
                            val visible=product.displayName
                            val split=visible.indexOf(' ')
                            Text(if(split>0) visible.substring(0,split) else visible,
                                color=V4Color.text,fontSize=17.sp,fontWeight=FontWeight.Bold)
                            Text(if(split>0) visible.substring(split+1) else
                                (s.brands.firstOrNull {it.brandId==product.brandId}?.name.orEmpty()),
                                color=V4Color.text,fontSize=15.sp)
                            if(line.sourceText.contains("DR")) Text(
                                "메뉴판의 'DR'을 풀어서 찾았어요",
                                color=V4Color.sub,fontSize=11.sp)
                            else if(product.displayName.contains("Rye",ignoreCase=true) &&
                                !line.sourceText.contains("Rye",ignoreCase=true))
                                Text("메뉴판엔 'Rye'가 안 적혀 있어요",
                                    color=V4Color.sub,fontSize=11.sp)
                            else if(candidates.size>1)
                                Text("메뉴판에 에디션 표기가 없어 함께 찾았어요",
                                    color=V4Color.sub,fontSize=11.sp)
                        }
                    }
                }
                if(candidates.size!=1)
                    St8Secondary("⌕  목록에 없어요") {
                        catalogQuery=""
                        visit("catalog")
                    }
            } else if((screen=="edit" || screen=="new") && pair!=null) {
                val line=pair.second
                var categoryPicker by remember {mutableStateOf(false)}
                var photoOpen by remember {mutableStateOf(false)}
                St8RecognizedStrip(pair.first,line,onLater=onHome){photoOpen=true}
                if(photoOpen)Stage8SourcePhoto(pair.first,line.sourceBox){photoOpen=false}
                St8ReviewHeading(
                    if(screen=="edit")"가격과 용량을 확인해 주세요" else "새로 등록할게요"
                ) {runCatching{vm.review(job.menuImportId,line.extractedItemId,
                        job.reviewVersion,MockReviewDecision(MockDecisionKind.EXCLUDE))}
                        .onSuccess{pendingNewDraftEncoded=null;error=null;next()}
                        .onFailure{error=it.message}}
                val restoredDraft=pendingNewDraft.takeIf {
                    pendingNewDraftLineId==line.extractedItemId
                }
                val previousDraft=line.decision?.newProduct ?: restoredDraft
                var name by rememberSaveable(line.extractedItemId) {
                    // New-product name holds the confirmed distillery, age and edition;
                    // split the suffix to avoid duplicating age/edition on re-entry.
                    val previous=previousDraft?.name.orEmpty()
                    val suffix=listOfNotNull(
                        previousDraft?.ageYears?.let{"${it}년"},
                        previousDraft?.editionName?.takeIf{it.isNotBlank()}
                    ).joinToString(" ")
                    mutableStateOf(if(suffix.isNotEmpty()&&previous.endsWith(" "+suffix))
                        previous.removeSuffix(" "+suffix) else previous)
                }
                var brand by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(previousDraft?.brandName ?:
                        s.brands.firstOrNull {it.brandId==previousDraft?.brandId}?.name.orEmpty())
                }
                var brandId by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(previousDraft?.brandId)
                }
                var age by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(previousDraft?.ageYears?.toString().orEmpty())
                }
                var noAge by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(previousDraft?.ageYears==null)
                }
                var edition by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(previousDraft?.editionName.orEmpty())
                }
                var alcohol by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(previousDraft?.abvPercent?.toString().orEmpty())
                }
                var displayOverride by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(line.decision?.displayNameOverride.orEmpty())
                }
                var subtype by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(previousDraft?.otherAlcoholKind.orEmpty())
                }
                if(screen=="new") {
                    Column(Modifier.fillMaxWidth().background(V4Color.surface,
                        RoundedCornerShape(16.dp)).padding(16.dp),
                        verticalArrangement=Arrangement.spacedBy(11.dp)) {
                        St8NewField("병입사",brand,{brand=it;brandId=null},
                            placeholder="예: Signatory Vintage")
                        s.brands.filter { brand.isNotBlank() &&
                            it.name.contains(brand,ignoreCase=true) }.take(5).forEach{existing->
                            TextButton(onClick={brand=existing.name;brandId=existing.brandId}) {
                                Row(verticalAlignment=Alignment.CenterVertically,
                                    horizontalArrangement=Arrangement.spacedBy(5.dp)) {
                                    if(brandId==existing.brandId)
                                        V4StrokeCheck(Modifier.size(15.dp),V4Color.primary)
                                    Text("기존 병입사: "+existing.name,color=V4Color.primary)
                                }
                            }
                        }
                        HorizontalDivider(color=V4Color.line)
                        St8NewField("증류소",name,{name=it},placeholder="예: Caol Ila")
                        HorizontalDivider(color=V4Color.line)
                        Text("숙성 연수",color=V4Color.sub,fontSize=12.sp)
                        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp),
                            verticalAlignment=Alignment.CenterVertically) {
                            OutlinedTextField(age,{
                                age=it.filter(Char::isDigit);if(age.isNotEmpty())noAge=false
                            },enabled=!noAge,placeholder={Text("예: 13")},
                                keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Number),
                                modifier=Modifier.width(105.dp),singleLine=true,
                                colors=OutlinedTextFieldDefaults.colors(
                                    focusedTextColor=V4Color.text,
                                    unfocusedTextColor=V4Color.text,
                                    focusedContainerColor=V4Color.background,
                                    unfocusedContainerColor=V4Color.background))
                            Box(Modifier.size(width=52.dp,height=46.dp),
                                contentAlignment=Alignment.Center) {
                                Box(Modifier.size(width=43.dp,height=26.dp)
                                    .border(1.dp,if(noAge)V4Color.primary else V4Color.line,
                                        RoundedCornerShape(7.dp))
                                    .clickable {noAge=!noAge;if(noAge)age=""},
                                    contentAlignment=Alignment.Center) {
                                    Text("없음",color=V4Color.primary,fontSize=14.sp)
                                }
                            }
                        }
                        HorizontalDivider(color=V4Color.line)
                        St8NewField("시리즈 (선택)",edition,{edition=it},
                            placeholder="없으면 비워 두세요")
                        if(chosenCategory=="otherAlcohol") St8NewField(
                            "기타 주류 세부 종류",subtype,{subtype=it},
                            placeholder="예: 맥주, 사케, 와인")

                    }
                    Row(Modifier.fillMaxWidth().border(1.dp,V4Color.line,
                        RoundedCornerShape(16.dp)).padding(13.dp),
                        verticalAlignment=Alignment.CenterVertically,
                        horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                        St8Bottle()
                        Column(verticalArrangement=Arrangement.spacedBy(3.dp)) {
                            Text("등록될 이름",fontSize=12.sp,color=V4Color.sub)
                            Text(brand.ifBlank{"병입사 미입력"},fontSize=17.sp,
                                color=V4Color.text,fontWeight=FontWeight.Bold)
                            Text(listOfNotNull(name.ifBlank{null},
                                age.toIntOrNull()?.takeIf{!noAge}?.let{it.toString()+"년"},
                                edition.trim().ifBlank{null}).joinToString(" ").ifBlank{"정보를 입력해 주세요"},
                                color=V4Color.text,fontSize=15.sp)
                        }
                    }
                }
                if(screen=="new") {
                    St8Button("새 제품으로 등록") {
                        val ageValue=if(noAge)null else age.toIntOrNull()
                        if(name.trim().isBlank() || (brandId==null && brand.isBlank()) ||
                            !noAge && ageValue !in 0..200) {
                            error="병입사, 증류소, 숙성 연수를 확인해 주세요."
                        } else {
                            val draft=MockNewProductDraft(
                                name=listOfNotNull(name.trim(),
                                    ageValue?.let{it.toString()+"년"},
                                    edition.trim().ifBlank{null}).joinToString(" "),
                                brandId=brandId,
                                brandName=if(brandId==null)brand.trim() else null,
                                ageYears=ageValue,
                                editionName=edition.trim().ifBlank{null},
                                category=chosenCategory)
                            if(line.options.isEmpty() || line.options.any{it.priceKrw<=0}) {
                                pendingNewDraftEncoded=encodeReviewDraft(draft)
                                pendingNewDraftLineId=line.extractedItemId
                                visit("price")
                            } else runCatching {
                                vm.review(job.menuImportId,line.extractedItemId,
                                    job.reviewVersion,MockReviewDecision(
                                        MockDecisionKind.CREATE_PRODUCT,
                                        correctedOptions=line.options,
                                        newProduct=draft))
                            }.onSuccess {error=null;next()}.onFailure {error=it.message}
                        }
                    }
                }
                if(screen=="edit") {
                val originals=line.decision?.correctedOptions ?: line.options.ifEmpty {
                    listOf(MockMenuOption("local-review-option-"+line.extractedItemId,priceKrw=0))
                }
                var labels by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(originals.map{it.label.orEmpty()})
                }
                var pours by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(originals.map{it.pourMl?.toString().orEmpty()})
                }
                var prices by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(originals.map{if(it.priceKrw>0)it.priceKrw.toString() else ""})
                }
                St8Card {
                    Text("옵션별 가격 · 용량",color=V4Color.text,fontWeight=FontWeight.Bold)
                    originals.forEachIndexed{i,o->
                        St8Field("옵션 라벨",labels[i],{v->
                            labels=labels.toMutableList().apply{set(i,v)}})
                        St8Field("용량 (ml, 없으면 빈칸)",pours[i],{v->
                            pours=pours.toMutableList().apply{set(i,v)}},digits=true)
                        val base=s.bars.firstOrNull{it.barId==barId}?.defaultPourMl
                        if(base!=null && pours[i].isBlank() &&
                            labels[i].trim() !in listOf("병","Bottle")){
                            TextButton(onClick={pours=pours.toMutableList().apply{
                                set(i,base.toString())}}){
                                Text("기본 잔 용량 "+base+"ml 직접 적용",color=V4Color.primary)
                            }
                        }
                        St8Field("가격 (원)",prices[i],{v->
                            prices=prices.toMutableList().apply{set(i,v)}},digits=true)
                        HorizontalDivider(color=V4Color.line)
                    }
                }
                val candidates=(listOfNotNull(line.suggestedProductId)+line.candidateProductIds)
                    .distinct().filter{id->s.products.any{it.productId==id && it.isActive}}
                if(screen=="edit")candidates.forEach{id->
                    TextButton(onClick={selectedProductId=id}){
                        Row(verticalAlignment=Alignment.CenterVertically,
                            horizontalArrangement=Arrangement.spacedBy(5.dp)) {
                            if(selectedProductId==id)
                                V4StrokeCheck(Modifier.size(15.dp),V4Color.primary)
                            Text(s.products.firstOrNull{it.productId==id}?.displayName ?: id,
                                color=V4Color.primary)
                        }
                    }
                }
                St8Button("확인하고 다음으로",enabled=originals.isNotEmpty()){
                    val resolved=originals.mapIndexed{i,o->
                        o.copy(label=labels[i].trim().ifBlank{null},
                            pourMl=pours[i].toIntOrNull(),priceKrw=prices[i].toIntOrNull()?:0)
                    }
                    if(resolved.any{it.priceKrw<=0 ||
                        pours[resolved.indexOf(it)].isNotBlank() && it.pourMl !in 1..32767} ||
                        resolved.map{it.identityKey()}.distinct().size!=resolved.size){
                        error="가격·용량·중복 옵션을 확인해 주세요."
                    } else {
                        if(screen=="new" && (!noAge && age.toIntOrNull()==null ||
                            alcohol.isNotBlank() && alcohol.toDoubleOrNull()==null ||
                            chosenCategory=="otherAlcohol" && subtype.isBlank())) {
                            error="숙성 연수와 도수 값을 확인해 주세요."
                            return@St8Button
                        }
                        val decision=if(screen=="edit")MockReviewDecision(
                            MockDecisionKind.SELECT_PRODUCT,productId=selectedProductId ?: line.decision?.productId,
                            correctedOptions=resolved)
                        else MockReviewDecision(MockDecisionKind.CREATE_PRODUCT,
                            correctedOptions=resolved,displayNameOverride=displayOverride.trim().ifBlank{null},
                            newProduct=MockNewProductDraft(
                                name=listOfNotNull(name.trim(),
                                    age.takeIf { !noAge && it.isNotBlank() &&
                                        !name.contains(it+"년") }?.let{it+"년"}).joinToString(" "),
                                brandId=brandId,brandName=if(brandId==null)brand.trim() else null,
                                category=chosenCategory,
                                ageYears=if(noAge)null else age.toIntOrNull(),
                                editionName=edition.trim().ifBlank{null},
                                abvPercent=alcohol.toDoubleOrNull(),
                                otherAlcoholKind=subtype.trim().ifBlank{null}))
                        runCatching{vm.review(job.menuImportId,line.extractedItemId,
                            job.reviewVersion,decision)}.onSuccess{error=null;next()}
                            .onFailure{error=it.message}
                    }
                }
                }
            } else if(screen=="price" && pair!=null) {
                val (photo,line)=pair
                var openPhoto by remember {mutableStateOf(false)}
                St8RecognizedStrip(photo,line,
                    defaultPourMl=s.bars.firstOrNull{it.barId==barId}?.defaultPourMl,
                    onLater=onHome){openPhoto=true}
                if(openPhoto)Stage8SourcePhoto(photo,line.sourceBox){openPhoto=false}
                St8ReviewHeading("가격을 못 읽었어요") {runCatching{vm.review(job.menuImportId,line.extractedItemId,
                        job.reviewVersion,MockReviewDecision(MockDecisionKind.EXCLUDE))}
                        .onSuccess{pendingNewDraftEncoded=null;error=null;next()}
                        .onFailure{error=it.message}}
                St8Card {
                    Row(verticalAlignment=Alignment.CenterVertically,
                        horizontalArrangement=Arrangement.spacedBy(11.dp)) {
                        St8Bottle()
                        Column {
                            Text("자동으로 찾은 메뉴",color=V4Color.sub,fontSize=11.sp)
                            Text(pendingNewDraft?.name ?:
                                s.products.firstOrNull{it.productId==selectedProductId}?.displayName
                                    ?: line.sourceText,
                                color=V4Color.text,fontSize=16.sp,fontWeight=FontWeight.Bold)
                        }
                    }
                    val options=line.decision?.correctedOptions ?: line.options.ifEmpty {
                        listOf(MockMenuOption("manual-price-${line.extractedItemId}",
                            label="잔",pourMl=30,priceKrw=0))
                    }
                    var prices by rememberSaveable(line.extractedItemId) {
                        mutableStateOf(options.map {if(it.priceKrw>0)it.priceKrw.toString() else ""})
                    }
                    options.forEachIndexed { i,o ->
                        Text((o.label ?: "잔")+" · "+((o.pourMl ?:
                            s.bars.firstOrNull{it.barId==barId}?.defaultPourMl)?.let{"${it}ml"}
                            ?: "용량 미표기")+" 가격",color=V4Color.sub,fontSize=13.sp)
                        OutlinedTextField(prices.getOrElse(i){""},{
                            val filtered=it.filter(Char::isDigit).take(10)
                            prices=prices.toMutableList().apply{set(i,filtered)}
                        },modifier=Modifier.fillMaxWidth(),
                            keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Number),
                            singleLine=true,placeholder={Text("예: 18000")},
                            suffix={Text("원")})
                    }
                    St8Button("저장",enabled=prices.size==options.size &&
                        prices.all{it.toIntOrNull()?.let {p->p>0}==true}) {
                        val corrected=options.mapIndexed{i,o->
                            o.copy(priceKrw=prices[i].toInt(),
                                pourMl=o.pourMl ?: s.bars.firstOrNull{it.barId==barId}
                                    ?.defaultPourMl?.takeIf{ ml->
                                        o.label?.trim() !in listOf("병","Bottle") && ml in 1..999})
                        }
                        val d=if(pendingNewDraft!=null)MockReviewDecision(
                            MockDecisionKind.CREATE_PRODUCT,correctedOptions=corrected,
                            newProduct=pendingNewDraft)
                        else MockReviewDecision(MockDecisionKind.SELECT_PRODUCT,
                            productId=selectedProductId,correctedOptions=corrected)
                        runCatching{vm.review(job.menuImportId,line.extractedItemId,
                            job.reviewVersion,d)}
                            .onSuccess{pendingNewDraftEncoded=null;error=null;next()}
                            .onFailure{error=it.message}
                    }
                }

            } else if(screen=="incomplete") {
                St8PublishSteps(2)
                Text("${counts!!.remaining}줄 남았어요",
                    color=V4Color.text,fontSize=26.sp,fontWeight=FontWeight.Bold)
                Text("확인을 마치면 메뉴를 게시할 수 있어요.",
                    color=V4Color.sub,fontSize=13.sp)
                St8CountCard("추가 예정",all.count {
                    it.second.kind==MockLineKind.PRODUCT &&
                        it.second.decision?.kind in listOf(
                            MockDecisionKind.SELECT_PRODUCT,MockDecisionKind.CREATE_PRODUCT)
                },"확인 필요",counts.remaining)
            } else if(screen=="results") {
                St8PublishSteps(3)
                Text("확인한 메뉴판 내용",color=V4Color.text,
                    fontSize=23.sp,fontWeight=FontWeight.Bold)
                Text("읽은 ${counts!!.lines}줄 · 새로 추가 ${all.count {
                    it.second.decision?.kind in listOf(
                        MockDecisionKind.SELECT_PRODUCT,MockDecisionKind.CREATE_PRODUCT)
                }}개 · 건너뜀 ${all.count {
                    it.second.decision?.kind in listOf(
                        MockDecisionKind.EXCLUDE,MockDecisionKind.CONFIRM_NON_PRODUCT)
                }}개",color=V4Color.sub,fontSize=12.sp)
                St8Card {
                    val auto=all.filter {(_,line)->
                        line.kind==MockLineKind.PRODUCT && line.mockAutoAccepted
                    }
                    Text("자동으로 찾은 신규 메뉴 ${auto.size}줄",color=V4Color.primary,
                        fontWeight=FontWeight.Bold,fontSize=12.sp)
                    auto.forEach {(_,line)->
                        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                            Text(s.products.firstOrNull {it.productId==line.suggestedProductId}
                                ?.displayName ?: line.sourceText,color=V4Color.text,
                                fontSize=12.sp,modifier=Modifier.weight(1f))
                            V4ReviewStateBadge("자동 인식")
                        }
                        HorizontalDivider(color=V4Color.line)
                    }
                    Spacer(Modifier.height(4.dp))
                    Text("검수한 메뉴 ${counts.reviewed}줄",
                        color=V4Color.primary,fontSize=12.sp,fontWeight=FontWeight.Bold)
                    all.filter {it.second.decision!=null}.forEach { (_,line)->
                        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,
                            verticalAlignment=Alignment.CenterVertically) {
                            val name=line.decision?.newProduct?.name ?:
                                s.products.firstOrNull{
                                    it.productId==line.decision?.productId
                                }?.displayName ?: line.sourceText
                            Text(name,color=V4Color.text,fontSize=12.sp,
                                modifier=Modifier.weight(1f))
                            V4ReviewStateBadge(when(line.decision?.kind){
                                MockDecisionKind.SELECT_PRODUCT->"확인됨"
                                MockDecisionKind.CREATE_PRODUCT->"신규 등록"
                                MockDecisionKind.EXCLUDE,MockDecisionKind.CONFIRM_NON_PRODUCT->"건너뜀"
                                else->"확인 필요"
                            })
                        }
                        HorizontalDivider(color=V4Color.line)
                    }
                    Spacer(Modifier.height(4.dp))
                    Text("이미 있는 메뉴 ${counts.existing}줄",
                        color=V4Color.primary,fontSize=12.sp,fontWeight=FontWeight.Bold)
                    val existingIds=s.menuItems.filter{it.barId==job.barId}
                        .map{it.productId}.toSet()
                    all.filter {(_,line)->
                        line.suggestedProductId in existingIds ||
                            line.candidateProductIds.any{it in existingIds}
                    }.forEach {(_,line)->
                        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                            Text(line.sourceText,color=V4Color.text,fontSize=12.sp,
                                modifier=Modifier.weight(1f))
                            V4ReviewStateBadge("건너뜀")
                        }
                        HorizontalDivider(color=V4Color.line)
                    }
                }
            } else if(screen=="publish") {
                St8PublishSteps(3)
                Text("검수 완료",color=V4Color.sub,fontSize=12.sp)
                Text("메뉴 게시",color=V4Color.text,fontSize=26.sp,
                    fontWeight=FontWeight.Bold)
                val selected=all.count {it.second.decision?.kind in listOf(
                    MockDecisionKind.SELECT_PRODUCT,MockDecisionKind.CREATE_PRODUCT)}
                val skipped=all.count {it.second.decision?.kind in listOf(
                    MockDecisionKind.EXCLUDE,MockDecisionKind.CONFIRM_NON_PRODUCT)}
                St8CountCard("새로 추가",selected,"건너뜀",skipped,"개")
                TextButton(onClick={visit("results")}) {
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {
                        Text("줄별 결과 보기",color=V4Color.primary,fontSize=14.sp)
                        Text("›",color=V4Color.primary,fontSize=18.sp)
                    }
                }
            } else if(screen=="done") {
                St8PublishSteps(3)
                Spacer(Modifier.height(80.dp))
                Box(Modifier.align(Alignment.CenterHorizontally).size(72.dp)
                    .background(Color(0xFF245740),RoundedCornerShape(50)),
                    contentAlignment=Alignment.Center) {
                    V4StrokeCheck(Modifier.size(32.dp),Color(0xFFE6FFF2))
                }
                val added=job.publishedAddedCount ?: 0
                val skipped=all.count{it.second.decision?.kind in listOf(
                    MockDecisionKind.EXCLUDE,MockDecisionKind.CONFIRM_NON_PRODUCT)}
                Text("메뉴에 ${added}개를 더했어요",
                    color=V4Color.text,fontSize=23.sp,fontWeight=FontWeight.Bold,
                    modifier=Modifier.align(Alignment.CenterHorizontally))
                Text((s.bars.firstOrNull{it.barId==barId}?.name ?: "매장")+
                    " · 메뉴 게시 완료",color=V4Color.sub,
                    fontSize=13.sp,modifier=Modifier.align(Alignment.CenterHorizontally))
                St8Card {
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                        Text("새로 더한 메뉴",color=V4Color.sub,fontSize=14.sp)
                        Text("${added}개",color=V4Color.text,fontWeight=FontWeight.Bold)
                    }
                    HorizontalDivider(color=V4Color.line)
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                        Text("카탈로그에 새로 등록",color=V4Color.sub,fontSize=14.sp)
                        Text("${job.publishedNewProductCount ?: 0}개",
                            color=V4Color.text,fontWeight=FontWeight.Bold)
                    }
                    HorizontalDivider(color=V4Color.line)
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                        Text("건너뛴 줄",color=V4Color.sub,fontSize=14.sp)
                        Text("${skipped}개",color=V4Color.text,fontWeight=FontWeight.Bold)
                    }
                }
                val changed=all.count { (_,line)->
                    val productId=line.decision?.productId ?: line.suggestedProductId
                    val barPrice=s.menuItems.firstOrNull{
                        it.barId==job.barId && it.productId==productId
                    }?.options?.firstOrNull()?.priceKrw
                    val imported=line.options.firstOrNull()?.priceKrw
                    barPrice!=null && imported!=null && imported>0 && barPrice!=imported
                }
                Row(Modifier.fillMaxWidth()
                    .border(1.dp,Color(0xFF75583D),RoundedCornerShape(12.dp))
                    .background(Color(0xFF302822),RoundedCornerShape(12.dp))
                    .clickable(onClick=onHome).padding(15.dp),
                    verticalAlignment=Alignment.CenterVertically,
                    horizontalArrangement=Arrangement.spacedBy(14.dp)){
                    V4PencilIcon(Modifier.size(24.dp))
                    Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)) {
                        Text("메뉴판과 가격이 다른 메뉴 ${changed}개",
                            color=V4Color.text,fontWeight=FontWeight.Bold,fontSize=14.sp)
                        Text("지금 메뉴 가격을 그대로 두었어요. 눌러서 바꿀 수 있어요.",
                            color=V4Color.sub,fontSize=12.sp)
                    }
                    Text("›",color=V4Color.sub,fontSize=21.sp)
                }
            } else if(screen=="publishFailed") {
                Column(Modifier.fillMaxWidth().background(Color(0xFF492927),
                    RoundedCornerShape(12.dp)).padding(15.dp),
                    verticalArrangement=Arrangement.spacedBy(5.dp)) {
                    Text("ⓘ  메뉴에 더하지 못했어요",color=Color(0xFFFFB4AB),
                        fontSize=15.sp,fontWeight=FontWeight.Bold)
                    Text("인터넷 연결을 확인해 주세요. 확인한 내용은 그대로 있어요.",
                        color=V4Color.text,fontSize=12.sp)
                }
                Text("게시 실패",color=V4Color.text,fontSize=25.sp,
                    fontWeight=FontWeight.Bold)
                St8CountCard("메뉴에 새로 더하는 줄",all.count{
                    it.second.decision?.kind in listOf(
                        MockDecisionKind.SELECT_PRODUCT,MockDecisionKind.CREATE_PRODUCT)},
                    "건너뛰는 줄",all.count{it.second.decision?.kind in listOf(
                        MockDecisionKind.EXCLUDE,MockDecisionKind.CONFIRM_NON_PRODUCT)},"개")
            }
            error?.let{Text(it,color=Color(0xFFFFB4AB),fontSize=12.sp)}
        }
        // Item pages use the source-header home icon for "나중에 하기".
        // Do not allocate an empty bottom bar under New/Product/Price screens.
        if(screen !in listOf("price","edit","new") &&
            (screen!="line" || pair?.second?.let { line ->
                line.kind==MockLineKind.NON_PRODUCT ||
                (listOfNotNull(line.suggestedProductId)+line.candidateProductIds)
                    .distinct().count { id ->
                        s.products.any {it.productId==id && it.isActive}
                    }==1
            }==true))
        Column(Modifier.fillMaxWidth().navigationBarsPadding().imePadding()
            .padding(horizontal=19.dp,vertical=12.dp),
            verticalArrangement=Arrangement.spacedBy(7.dp)) {
            when(screen) {
                "summary"->{
                    St8Button(if(counts!!.reviewed>0)counts.remaining.toString()+"줄 이어서 확인"
                        else counts.remaining.toString()+"줄 확인 시작",
                        enabled=counts.remaining>0) {
                            val first=all.indexOfFirst {it.second.decision==null}
                            if(first>=0)visitLine(first)
                        }
                    if(counts.remaining==0)St8Button("검수 결과 확인"){visit("publish")}
                    TextButton(onClick=onHome,modifier=Modifier.fillMaxWidth()){
                        Text("나중에 하기",color=V4Color.sub)
                    }
                }
                "auto"->St8Button("요약으로") {visit("summary")}
                "existing"->{
                    V4ExistingHint()
                    Spacer(Modifier.height(9.dp))
                    St8Secondary("요약으로") {visit("summary")}
                }
                "catalog"->St8Secondary("찾는 메뉴가 없어요, 새로 등록") {visit("new")}
                "line"->{
                    if(pair!=null) {
                        val line=pair.second
                        val ids=(listOfNotNull(line.suggestedProductId)+
                            line.candidateProductIds).distinct().filter { id ->
                            s.products.any {it.productId==id && it.isActive}
                        }
                        if(line.kind==MockLineKind.NON_PRODUCT) {
                            St8Button("이번 검수에서 제외") {
                                runCatching {vm.review(job.menuImportId,line.extractedItemId,
                                    job.reviewVersion,MockReviewDecision(MockDecisionKind.CONFIRM_NON_PRODUCT))}
                                    .onSuccess {error=null;next()}.onFailure {error=it.message}
                            }
                        } else if(ids.size==1) {
                            St8Button("맞아요") {
                                val id=ids.single()
                                if(line.options.isEmpty() || line.options.any {it.priceKrw<=0}) {
                                    selectedProductId=id;visit("price")
                                } else runCatching {vm.review(job.menuImportId,line.extractedItemId,
                                    job.reviewVersion,MockReviewDecision(MockDecisionKind.SELECT_PRODUCT,
                                        productId=id,correctedOptions=line.options))}
                                    .onSuccess{error=null;next()}.onFailure{error=it.message}
                            }
                            St8Secondary("다른 메뉴예요") {
                                catalogQuery="";visit("catalog")
                            }
                        }
                    }
                }
                "incomplete"->{
                    St8Button("${counts!!.remaining}줄 이어서 확인",enabled=counts.remaining>0){
                        val pos=all.indexOfFirst {it.second.decision==null}
                        if(pos>=0)visitLine(pos)
                    }
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)){
                        Box(Modifier.weight(1f)){
                            St8Secondary("나중에 하기",onHome)
                        }
                        Box(Modifier.weight(1f)){
                            St8Secondary("처음부터 검수") {showRestartWarning=true}
                        }
                    }
                }
                "results"->St8Button("돌아가기"){visit("publish")}
                "publish"->{
                    val accepted=all.count{it.second.decision?.kind in listOf(
                        MockDecisionKind.SELECT_PRODUCT,MockDecisionKind.CREATE_PRODUCT)}
                    St8Button("+  메뉴 ${accepted}개 게시",enabled=counts!!.remaining==0){
                        runCatching{vm.publish(job.menuImportId,job.reviewVersion)}
                            .onSuccess{error=null;visit("done")}
                            .onFailure{error=it.message;visit("publishFailed")}
                    }
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                        Box(Modifier.weight(1f)) {
                            St8Secondary("나중에 하기",onHome)
                        }
                        Box(Modifier.weight(1f)) {
                            St8Secondary("처음부터 검수") {showRestartWarning=true}
                        }
                    }
                }
                "done"->{
                    St8Secondary("메뉴 보기",onHome)
                    TextButton(onClick=onHome,modifier=Modifier.fillMaxWidth()) {
                        Text("닫기",color=V4Color.sub)
                    }
                }
                "publishFailed"->{
                    St8Button("+  다시 시도") {
                        runCatching{vm.publish(job.menuImportId,job.reviewVersion)}
                            .onSuccess{error=null;visit("done")}
                            .onFailure{error=it.message;visit("publishFailed")}
                    }
                    TextButton(onClick=onHome,modifier=Modifier.fillMaxWidth()) {
                        Text("나중에 하기",color=V4Color.sub)
                    }
                }
            }

        }
    }
}

@Composable private fun Stage8SourcePhoto(
    photo: MockPhotoExtraction, box: List<Int>?, dismiss:()->Unit
) {
    val context=LocalContext.current
    val result by produceState<Pair<Boolean,androidx.compose.ui.graphics.ImageBitmap?>>(
        initialValue=false to null,key1=photo.sourceUri) {
        val loaded=withContext(Dispatchers.IO) {
            runCatching {OwnerMenuPhotoStore(context).preview(
                MockPhoto(photo.imageId,photo.sourceUri,MockPhotoKind.MENU_CAPTURE),
                size=1600
            )?.asImageBitmap()}.getOrNull()
        }
        value=true to loaded
    }
    val bitmap=result.second
    Dialog(onDismissRequest=dismiss,
        properties=DialogProperties(usePlatformDefaultWidth=false)) {
        BoxWithConstraints(Modifier.fillMaxSize(),contentAlignment=Alignment.Center) {
            val ratio=bitmap?.let{it.width.toFloat()/it.height.toFloat()} ?: 1f
            val availableHeight=(maxHeight-160.dp).coerceAtLeast(160.dp)
            val imageWidth=if(bitmap==null)220.dp else
                minOf(maxWidth-58.dp,availableHeight*ratio)
            val imageHeight=if(bitmap==null)100.dp else imageWidth/ratio
            Column(Modifier.width(imageWidth+24.dp)
                .background(V4Color.surface,RoundedCornerShape(15.dp))
                .padding(horizontal=12.dp,vertical=11.dp),
                horizontalAlignment=Alignment.CenterHorizontally,
                verticalArrangement=Arrangement.spacedBy(11.dp)) {
                Text("원본 사진 보기",color=V4Color.text,fontSize=15.sp,
                    fontWeight=FontWeight.Bold,textAlign=TextAlign.Center)
                if(bitmap==null) {
                    Box(Modifier.size(imageWidth,imageHeight),
                        contentAlignment=Alignment.Center) {
                        Text(if(result.first)"원본 사진을 열 수 없어요." else
                            "사진을 불러오는 중이에요.",color=V4Color.sub)
                    }
                } else {
                    Box(Modifier.size(imageWidth,imageHeight)) {
                        Image(requireNotNull(bitmap),contentDescription="원본 메뉴판",
                            modifier=Modifier.fillMaxSize(),contentScale=ContentScale.FillBounds)
                        if(box!=null && box.size==4)Canvas(Modifier.fillMaxSize()) {
                            drawRect(Color(0xFFFFBC74),
                                topLeft=Offset(size.width*box[0]/1000f,
                                    size.height*box[1]/1000f),
                                size=Size(size.width*(box[2]-box[0])/1000f,
                                    size.height*(box[3]-box[1])/1000f),
                                style=Stroke(width=3.dp.toPx()))
                        }
                    }
                }
                TextButton(onClick=dismiss) {
                    Text("닫기",color=V4Color.sub,fontSize=14.sp)
                }
            }
        }
    }

}
