package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zerotoone.bottlemap.data.owner.*

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
@Composable private fun St8Field(text: String, value: String, change:(String)->Unit, digits:Boolean=false) {
    OutlinedTextField(value=value,onValueChange={change(if(digits)it.filter(Char::isDigit) else it)},
        label={Text(text)},singleLine=true,modifier=Modifier.fillMaxWidth(),
        colors=OutlinedTextFieldDefaults.colors(focusedTextColor=V4Color.text,
            unfocusedTextColor=V4Color.text,focusedBorderColor=V4Color.primary))
}
@Composable private fun St8Card(content:@Composable ColumnScope.()->Unit) {
    Column(Modifier.fillMaxWidth().background(V4Color.surface,RoundedCornerShape(12.dp))
        .border(1.dp,V4Color.line,RoundedCornerShape(12.dp)).padding(14.dp),
        verticalArrangement=Arrangement.spacedBy(9.dp),content=content)
}
/** Every count and item comes from the Stage 7 persisted import. No fixed PDF example data. */
@Composable internal fun OwnerPhotoStage8Screen(
    state: MockOwnerLoadState, vm: OwnerMockViewModel,
    onBack:()->Unit, onHome:()->Unit,
) {
    val s=reviewSnap(state)
    val barId=s?.selectedBarId ?: s?.bars?.firstOrNull()?.barId
    val job=s?.imports?.lastOrNull { it.barId==barId }
    val all=job?.images?.flatMap { photo->photo.lines.map { photo to it } }.orEmpty()
    val counts=if(job!=null && s!=null)stage8Counts(job,s) else null
    var screen by rememberSaveable(job?.menuImportId){mutableStateOf("summary")}
    var position by rememberSaveable(job?.menuImportId){mutableIntStateOf(0)}
    var error by rememberSaveable {mutableStateOf<String?>(null)}
    var publishConfirmed by rememberSaveable {mutableStateOf(false)}
    var selectedProductId by rememberSaveable(job?.menuImportId) { mutableStateOf<String?>(null) }
    var chosenCategory by rememberSaveable(job?.menuImportId) { mutableStateOf("whisky") }
    val pair=all.getOrNull(position)
    LaunchedEffect(pair?.second?.extractedItemId) {
        selectedProductId=pair?.second?.decision?.productId
        chosenCategory=pair?.second?.decision?.newProduct?.category ?: "whisky"
    }
    fun next() {
        selectedProductId=null
        val target=all.indices.firstOrNull{it>position && all[it].second.decision==null}
            ?: all.indices.firstOrNull{all[it].second.decision==null}
        if(target==null)screen="publish" else {position=target;screen="line"}
    }
    Column(Modifier.fillMaxSize().background(V4Color.background)) {
        V4Toolbar(null, {
            when(screen) {
                "line","publish","auto","existing" -> screen="summary"
                "edit","new" -> screen="line"
                "done"->onHome()
                else->onBack()
            }
        })
        if (s==null || job==null || job.status !in
            listOf(MockImportStatus.READY_FOR_REVIEW,MockImportStatus.APPLIED)) {
            Box(Modifier.weight(1f),contentAlignment=Alignment.Center) {
                Text("검수 가능한 메뉴판 작업이 없어요.",color=V4Color.text)
            }
            St8Button("내 매장으로 돌아가기",click=onHome)
            return@Column
        }
        LaunchedEffect(job.status) {
            if(job.status==MockImportStatus.APPLIED)screen="done"
        }
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(19.dp),
            verticalArrangement=Arrangement.spacedBy(15.dp)) {
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
                        TextButton(onClick={
                            val n=pour.toIntOrNull()
                            if(bar!=null && (pour.isBlank() || n!=null && n in 1..999)){
                                vm.saveBar(bar.copy(defaultPourMl=n));error=null
                            }else error="1~999ml로 입력해 주세요."
                        }){Text("저장",color=V4Color.primary)}
                    }
                    Text("용량 표시가 없는 잔에 적용",color=V4Color.sub,fontSize=11.sp)
                }
                St8Card {
                    Text("자동 인식 신규 메뉴 "+counts.newCandidates+"줄 ›",
                        color=V4Color.text,fontWeight=FontWeight.Bold,
                        modifier=Modifier.fillMaxWidth().clickable {screen="auto"})
                }
                St8Card {
                    Text("이미 등록된 메뉴 "+counts.existing+"줄 ›",
                        color=V4Color.text,fontWeight=FontWeight.Bold,
                        modifier=Modifier.fillMaxWidth().clickable {screen="existing"})
                }
                Text("확인한 줄 "+counts.reviewed+"개 · 남은 줄 "+counts.remaining+"개",
                    color=V4Color.sub,fontSize=12.sp)
            } else if(screen=="auto" || screen=="existing") {
                Text(if(screen=="auto")"새로 더할 메뉴 "+counts!!.newCandidates+"줄"
                    else "이미 있는 메뉴 "+counts!!.existing+"줄",
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
                if(subset.isEmpty())Text("해당하는 메뉴가 없어요.",color=V4Color.sub)
                subset.forEach{entry->
                    Column(Modifier.fillMaxWidth().clickable{
                        position=entry.index;screen="line"
                    }.padding(vertical=10.dp)) {
                        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,
                            verticalAlignment=Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(entry.value.second.sourceText,color=V4Color.text,fontSize=15.sp)
                                Text("메뉴판 "+entry.value.first.imageOrder+" · "+
                                    (if(screen=="existing")"기존 등록 메뉴" else "신규 등록 후보"),
                                    color=V4Color.sub,fontSize=12.sp)
                            }
                            val price=entry.value.second.decision?.correctedOptions?.firstOrNull()?.priceKrw
                                ?: entry.value.second.options.firstOrNull()?.priceKrw
                            Text(if(price!=null && price>0)"%,d원".format(price) else "가격 확인 필요",
                                color=V4Color.text,fontSize=13.sp)
                        }
                        HorizontalDivider(color=V4Color.line)
                    }
                }
            } else if(screen=="line" && pair!=null) {
                val (photo,line)=pair
                Text((position+1).toString()+" / "+counts!!.lines,
                    color=V4Color.sub,modifier=Modifier.align(Alignment.CenterHorizontally))
                Text("메뉴판 "+photo.imageOrder+" · "+(position+1)+"번째 줄",
                    color=V4Color.sub,fontSize=12.sp)
                Box(Modifier.fillMaxWidth().background(Color(0xFFE8DDC9),
                    RoundedCornerShape(8.dp)).padding(14.dp)){
                    Text(line.sourceText,color=Color(0xFF261E18),fontSize=18.sp,
                        fontWeight=FontWeight.Bold)
                }
                var openPhoto by remember {mutableStateOf(false)}
                TextButton(onClick={openPhoto=true},modifier=Modifier.align(Alignment.End)){
                    Text("원본 사진 보기",color=V4Color.sub)
                }
                if(openPhoto)Stage8SourcePhoto(photo,line.sourceBox){openPhoto=false}
                Text("이 메뉴가 맞나요?",color=V4Color.text,fontSize=23.sp,
                    fontWeight=FontWeight.Bold)
                var categoryPopup by remember {mutableStateOf(false)}
                TextButton(onClick={categoryPopup=true}){Text("위스키가 아니에요",color=V4Color.sub)}
                if(categoryPopup)AlertDialog(onDismissRequest={categoryPopup=false},
                    title={Text("메뉴 종류 선택")},text={Column{
                        listOf("cocktail" to "칵테일","food" to "안주",
                            "otherAlcohol" to "기타 주류").forEach{(v,label)->
                            TextButton(onClick={chosenCategory=v;categoryPopup=false}){Text(label)}
                        }
                    }},confirmButton={TextButton(onClick={categoryPopup=false}){Text("닫기")}})
                val candidates=(listOfNotNull(line.suggestedProductId)+line.candidateProductIds)
                    .distinct().mapNotNull{id->s.products.firstOrNull{
                        it.productId==id && it.isActive}}
                if(chosenCategory=="whisky")candidates.forEach{product->
                    St8Card {
                        Text(product.displayName,color=V4Color.text,fontWeight=FontWeight.Bold)
                        Text(s.brands.firstOrNull{it.brandId==product.brandId}?.name.orEmpty(),
                            color=V4Color.sub,fontSize=12.sp)
                        St8Button("맞아요") {
                            selectedProductId=product.productId
                            screen="edit"
                        }
                    }
                }
                if(candidates.isEmpty())Text("일치하는 상품 후보가 없어요.",
                    color=V4Color.sub,fontSize=13.sp)
                var searchExpanded by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(false)
                }
                var searchTerm by rememberSaveable(line.extractedItemId) {
                    mutableStateOf("")
                }
                TextButton(onClick={searchExpanded=!searchExpanded}) {
                    Text("⌕ 카탈로그에서 찾기",color=V4Color.primary)
                }
                if(searchExpanded) {
                    St8Field("상품 이름 검색",searchTerm,{searchTerm=it})
                    s.products.filter { product -> product.isActive &&
                        product.displayName.contains(searchTerm,ignoreCase=true) }
                        .take(12).forEach {product ->
                            TextButton(onClick={
                                selectedProductId=product.productId
                                screen="edit"
                            }) {
                                Text(product.displayName,color=V4Color.primary)
                            }
                        }
                }

                candidates.forEach{p->
                    TextButton(onClick={selectedProductId=p.productId;screen="edit"}){
                        Text(if(selectedProductId==p.productId)"✓ "+p.displayName else p.displayName,
                            color=V4Color.primary)
                    }
                }
                St8Button("다른 메뉴예요 · 새 제품으로 등록") {screen="new"}
                St8Button("메뉴가 아니에요 · 제외"){
                    runCatching {vm.review(job.menuImportId,line.extractedItemId,
                        job.reviewVersion,MockReviewDecision(MockDecisionKind.CONFIRM_NON_PRODUCT))}
                        .onSuccess{error=null;next()}.onFailure{error=it.message}
                }
            } else if((screen=="edit" || screen=="new") && pair!=null) {
                val line=pair.second
                Text(if(screen=="edit")"가격과 용량을 확인해 주세요" else "새로 등록할게요",
                    color=V4Color.text,fontSize=24.sp,fontWeight=FontWeight.Bold)
                var name by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(line.decision?.newProduct?.name.orEmpty())
                }
                var brand by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(line.decision?.newProduct?.brandName.orEmpty())
                }
                var brandId by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(line.decision?.newProduct?.brandId)
                }
                var age by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(line.decision?.newProduct?.ageYears?.toString().orEmpty())
                }
                var noAge by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(line.decision?.newProduct?.ageYears==null)
                }
                var edition by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(line.decision?.newProduct?.editionName.orEmpty())
                }
                var alcohol by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(line.decision?.newProduct?.abvPercent?.toString().orEmpty())
                }
                var displayOverride by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(line.decision?.displayNameOverride.orEmpty())
                }
                var subtype by rememberSaveable(line.extractedItemId) {
                    mutableStateOf(line.decision?.newProduct?.otherAlcoholKind.orEmpty())
                }
                if(screen=="new") St8Card {
                    St8Field("상품 이름",name,{name=it})
                    St8Field("매장 표시명 (선택)",displayOverride,{displayOverride=it})
                    St8Field("브랜드",brand,{brand=it;brandId=null})
                    s.brands.filter { brand.isNotBlank() &&
                        it.name.contains(brand,ignoreCase=true) }.take(5).forEach { existing ->
                        TextButton(onClick={brand=existing.name;brandId=existing.brandId}) {
                            Text((if(brandId==existing.brandId)"✓ " else "")+
                                "기존 브랜드: "+existing.name,color=V4Color.primary)
                        }
                    }
                    var expanded by remember {mutableStateOf(false)}
                    TextButton(onClick={expanded=true}){
                        Text("분류: "+chosenCategory+" ▾",color=V4Color.primary)
                    }
                    if(expanded)AlertDialog(onDismissRequest={expanded=false},title={Text("분류")},
                        text={Column{listOf("whisky","cocktail","food","otherAlcohol",
                            "gin","brandy","rum","wine").forEach{kind->
                            TextButton(onClick={chosenCategory=kind;expanded=false}){Text(kind)}
                        }}},confirmButton={TextButton(onClick={expanded=false}){Text("닫기")}})
                    Row(verticalAlignment=Alignment.CenterVertically){
                        Checkbox(noAge,{noAge=it});Text("숙성 연수 없음",color=V4Color.text)
                    }
                    if(!noAge)St8Field("숙성 연수",age,{age=it},digits=true)
                    St8Field("에디션 (선택)",edition,{edition=it})
                    St8Field("도수 (선택)",alcohol,{alcohol=it})
                    if(chosenCategory=="otherAlcohol")St8Field("기타 주류 종류",subtype,{subtype=it})
                }
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
                        Text((if(selectedProductId==id)"✓ " else "")+
                            (s.products.firstOrNull{it.productId==id}?.displayName ?: id),
                            color=V4Color.primary)
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
                            alcohol.isNotBlank() && alcohol.toDoubleOrNull()==null)) {
                            error="숙성 연수와 도수 값을 확인해 주세요."
                            return@St8Button
                        }
                        val decision=if(screen=="edit")MockReviewDecision(
                            MockDecisionKind.SELECT_PRODUCT,productId=selectedProductId ?: line.decision?.productId,
                            correctedOptions=resolved)
                        else MockReviewDecision(MockDecisionKind.CREATE_PRODUCT,
                            correctedOptions=resolved,displayNameOverride=displayOverride.trim().ifBlank{null},
                            newProduct=MockNewProductDraft(
                                name=name.trim(),brandId=brandId,brandName=if(brandId==null)brand.trim() else null,
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
            } else if(screen=="publish") {
                Text(if(counts!!.remaining==0)"검수를 마쳤어요" else "검수 미완료",
                    color=V4Color.text,fontSize=24.sp,fontWeight=FontWeight.Bold)
                Text(counts.reviewed.toString()+" / "+counts.lines+"줄 확인",color=V4Color.sub)
                all.forEach{(photo,line)->
                    Text("사진 "+photo.imageOrder+": "+line.sourceText.take(90)+" · "+
                        (line.decision?.kind?.name?:"미확인"),color=V4Color.text,fontSize=12.sp)
                }
                Row(verticalAlignment=Alignment.CenterVertically){
                    Checkbox(publishConfirmed,{publishConfirmed=it})
                    Text("검수 결과를 확인했어요 (Mock 게시)",color=V4Color.text)
                }
            } else if(screen=="done") {
                Spacer(Modifier.height(90.dp))
                Text("메뉴가 추가됐어요",color=V4Color.text,fontSize=26.sp,
                    fontWeight=FontWeight.Bold,modifier=Modifier.align(Alignment.CenterHorizontally))
                Text("기존 메뉴와 가격은 그대로 유지했어요.",color=V4Color.sub)
            }
            error?.let{Text(it,color=Color(0xFFFFB4AB),fontSize=12.sp)}
        }
        Column(Modifier.fillMaxWidth().navigationBarsPadding()
            .padding(horizontal=19.dp,vertical=12.dp),
            verticalArrangement=Arrangement.spacedBy(7.dp)) {
            when(screen) {
                "summary"->{
                    St8Button(if(counts!!.reviewed>0)counts.remaining.toString()+"줄 이어서 확인"
                        else counts.remaining.toString()+"줄 확인 시작",
                        enabled=counts.remaining>0) {next()}
                    if(counts.remaining==0)St8Button("검수 결과 확인"){screen="publish"}
                    TextButton(onClick=onHome,modifier=Modifier.fillMaxWidth()){
                        Text("나중에 하기",color=V4Color.sub)
                    }
                }
                "auto","existing"->St8Button("요약으로") {screen="summary"}
                "line"->{
                    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){
                        TextButton(onClick={if(position>0)position-- else screen="summary"}){
                            Text("‹ 이전",color=V4Color.sub)
                        }
                        Text("남은 확인 "+counts!!.remaining+"개",color=V4Color.sub)
                        TextButton(onClick={if(position+1<all.size)position++ else screen="summary"}){
                            Text("다음 ›",color=V4Color.primary)
                        }
                    }
                }
                "edit","new"->TextButton(onClick={screen="line"}){
                    Text("이전",color=V4Color.sub)
                }
                "publish"->{
                    St8Button("메뉴 더하기",enabled=counts!!.remaining==0 && publishConfirmed){
                        runCatching{vm.publish(job.menuImportId,job.reviewVersion)}
                            .onSuccess{error=null;screen="done"}.onFailure{error=it.message}
                    }
                    TextButton(onClick={screen="summary"}){Text("계속 확인",color=V4Color.sub)}
                }
                "done"->St8Button("내 매장으로 돌아가기",click=onHome)
            }
        }
    }
}

@Composable private fun Stage8SourcePhoto(
    photo: MockPhotoExtraction, box: List<Int>?, dismiss:()->Unit
) {
    val context=LocalContext.current
    val bitmap=remember(photo.sourceUri){
        runCatching{OwnerMenuPhotoStore(context).preview(
            MockPhoto(photo.imageId,photo.sourceUri,MockPhotoKind.MENU_CAPTURE)
        )?.asImageBitmap()}.getOrNull()
    }
    AlertDialog(onDismissRequest=dismiss,title={Text("원본 사진 보기")},
        text={if(bitmap==null)Text("사진을 열 수 없어요.")
            else Box(Modifier.fillMaxWidth().aspectRatio(
                bitmap.width.toFloat()/bitmap.height.toFloat())){
                Image(bitmap,contentDescription="원본 메뉴판",modifier=Modifier.fillMaxSize(),
                    contentScale=ContentScale.FillBounds)
                if(box!=null && box.size==4)Canvas(Modifier.fillMaxSize()){
                    drawRect(Color(0xFFFFBC74),
                        topLeft=androidx.compose.ui.geometry.Offset(
                            size.width*box[0]/1000f,size.height*box[1]/1000f),
                        size=androidx.compose.ui.geometry.Size(
                            size.width*(box[2]-box[0])/1000f,
                            size.height*(box[3]-box[1])/1000f),
                        style=Stroke(width=3.dp.toPx()))
                }
            }},
        confirmButton={TextButton(onClick=dismiss){Text("닫기")}})
}
