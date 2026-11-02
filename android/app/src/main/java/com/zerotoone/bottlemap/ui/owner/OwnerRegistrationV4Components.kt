package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Screen-specific ACTION_FIRST v4 CSS port. All sizes are dp equivalents of
 * the 360-wide HTML phone, not default Material outlined-field/alert styling. */
internal fun Modifier.registrationDashedBorder(radius:Dp=16.dp):Modifier =
    this.drawWithContent {
        drawContent()
        drawRoundRect(color=RegistrationV4.muted,
            cornerRadius=CornerRadius(radius.toPx()),
            style=Stroke(width=1.5.dp.toPx(),
                pathEffect=PathEffect.dashPathEffect(
                    floatArrayOf(4.dp.toPx(),4.dp.toPx()))))
    }

internal object RegistrationV4 {
    val bg=Color(0xFF211E1B)
    val surface=Color(0xFF302B27)
    val elevated=Color(0xFF3A332E)
    val primary=Color(0xFFC99D6B)
    val onPrimary=Color(0xFF211A14)
    val text=Color(0xFFF2EDE8)
    val secondary=Color(0xFFC7BBB0)
    val muted=Color(0xFFB9AEA4)
    val border=Color(0xFF51473F)
    val error=Color(0xFFFFB4AB)
}
@Composable
internal fun RegistrationBackBar(back:()->Unit) {
    Row(Modifier.fillMaxWidth().height(52.dp).padding(start=8.dp),
        verticalAlignment=Alignment.CenterVertically) {
        Box(Modifier.size(48.dp).ownerQuietClick(onClick=back)
            .semantics { contentDescription="뒤로가기" }.testTag("registration-back"),
            contentAlignment=Alignment.Center) {
            Canvas(Modifier.size(20.dp)) {
                val p=Path().apply {
                    moveTo(size.width*0.62f,size.height*0.18f)
                    lineTo(size.width*0.31f,size.height*0.50f)
                    lineTo(size.width*0.62f,size.height*0.82f)
                }
                drawPath(p, RegistrationV4.text,
                    style=Stroke(1.75.dp.toPx(),cap=StrokeCap.Round,join=StrokeJoin.Round))
            }
        }
    }
}
@Composable
internal fun RegistrationProgress(stage:Int) {
    Row(Modifier.fillMaxWidth().padding(horizontal=20.dp),horizontalArrangement=Arrangement.spacedBy(4.dp)) {
        repeat(4) { i ->
            Box(Modifier.weight(1f).height(3.dp)
                .background(if(i<stage) RegistrationV4.primary else RegistrationV4.border,
                    RoundedCornerShape(3.dp)))
        }
    }
    Text("$stage/4 "+listOf("사업자 정보","매장 정보","메뉴판","확인")[stage-1],
        color=RegistrationV4.secondary,fontSize=12.sp,lineHeight=18.sp,
        modifier=Modifier.padding(start=20.dp,top=8.dp))
}
@Composable
internal fun RegistrationHeading(title:String, subtitle:String?=null) {
    Column(Modifier.fillMaxWidth().padding(top=8.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
        Text(title,style=androidx.compose.material3.MaterialTheme.typography.headlineSmall,
            color=RegistrationV4.text,lineHeight=32.sp)
        if(!subtitle.isNullOrBlank())
            Text(subtitle,color=RegistrationV4.secondary,fontSize=14.sp,lineHeight=21.sp)
    }
}
@Composable
internal fun RegistrationButton(title:String,enabled:Boolean=true,onClick:()->Unit) {
    Box(Modifier.fillMaxWidth().heightIn(min=56.dp)
        .clip(RoundedCornerShape(12.dp))
        .background(if(enabled)RegistrationV4.primary else Color(0xFF403832))
        .ownerQuietClick(enabled=enabled,onClick=onClick)
        .testTag("registration-primary"),
        contentAlignment=Alignment.Center) {
        Text(title,color=if(enabled)RegistrationV4.onPrimary else RegistrationV4.muted,
            fontWeight=FontWeight.SemiBold,fontSize=16.sp,lineHeight=24.sp)
    }
}
@Composable
internal fun RegistrationGlyph(kind:String,modifier:Modifier=Modifier,color:Color=RegistrationV4.primary,size:Dp=22.dp) {
    Canvas(modifier.size(size)) {
        val w=this.size.width; val h=this.size.height
        val path=Path()
        fun stroke() { drawPath(path,color,style=Stroke(1.65.dp.toPx(),
            cap=StrokeCap.Round,join=StrokeJoin.Round)) }
        when(kind) {
            "document" -> {
                path.moveTo(w*.22f,h*.08f);path.lineTo(w*.66f,h*.08f)
                path.lineTo(w*.82f,h*.25f);path.lineTo(w*.82f,h*.92f)
                path.lineTo(w*.22f,h*.92f);path.close()
                path.moveTo(w*.65f,h*.08f);path.lineTo(w*.65f,h*.27f);path.lineTo(w*.82f,h*.27f)
                path.moveTo(w*.34f,h*.51f);path.lineTo(w*.68f,h*.51f)
                path.moveTo(w*.34f,h*.68f);path.lineTo(w*.68f,h*.68f);stroke()
            }
            "picture" -> {
                path.moveTo(w*.12f,h*.19f);path.lineTo(w*.88f,h*.19f)
                path.lineTo(w*.88f,h*.84f);path.lineTo(w*.12f,h*.84f);path.close()
                path.moveTo(w*.14f,h*.76f);path.lineTo(w*.39f,h*.49f)
                path.lineTo(w*.53f,h*.63f);path.lineTo(w*.67f,h*.46f)
                path.lineTo(w*.86f,h*.66f);stroke()
                drawCircle(color,2.dp.toPx(),center=androidx.compose.ui.geometry.Offset(w*.34f,h*.35f))
            }
            "menu" -> {
                path.moveTo(w*.2f,h*.08f);path.lineTo(w*.8f,h*.08f)
                path.lineTo(w*.8f,h*.91f);path.lineTo(w*.2f,h*.91f);path.close()
                for(y in listOf(.32f,.49f,.66f)) {
                    path.moveTo(w*.36f,h*y);path.lineTo(w*.66f,h*y)
                };stroke()
            }
            "camera" -> {
                path.moveTo(w*.08f,h*.31f);path.lineTo(w*.28f,h*.31f)
                path.lineTo(w*.36f,h*.20f);path.lineTo(w*.62f,h*.20f)
                path.lineTo(w*.70f,h*.31f);path.lineTo(w*.91f,h*.31f)
                path.lineTo(w*.91f,h*.83f);path.lineTo(w*.08f,h*.83f);path.close();stroke()
                drawCircle(color,4.dp.toPx(),center=androidx.compose.ui.geometry.Offset(w*.5f,h*.56f),
                    style=Stroke(1.65.dp.toPx()))
            }
            "pen" -> {
                path.moveTo(w*.19f,h*.73f);path.lineTo(w*.72f,h*.20f)
                path.lineTo(w*.83f,h*.31f);path.lineTo(w*.30f,h*.84f)
                path.lineTo(w*.19f,h*.84f);path.close();stroke()
            }
            "check" -> {
                path.moveTo(w*.13f,h*.52f);path.lineTo(w*.40f,h*.77f)
                path.lineTo(w*.87f,h*.23f);stroke()
            }
            "search" -> {
                drawCircle(color,5.dp.toPx(),center=androidx.compose.ui.geometry.Offset(w*.42f,h*.42f),
                    style=Stroke(1.65.dp.toPx()))
                path.moveTo(w*.63f,h*.65f);path.lineTo(w*.85f,h*.88f);stroke()
            }
            "chevron" -> {
                path.moveTo(w*.41f,h*.18f);path.lineTo(w*.69f,h*.50f)
                path.lineTo(w*.41f,h*.82f);stroke()
            }
            "plus" -> {
                path.moveTo(w*.5f,h*.17f);path.lineTo(w*.5f,h*.83f)
                path.moveTo(w*.17f,h*.5f);path.lineTo(w*.83f,h*.5f);stroke()
            }
            "store" -> {
                path.moveTo(w*.13f,h*.38f);path.lineTo(w*.22f,h*.16f)
                path.lineTo(w*.78f,h*.16f);path.lineTo(w*.88f,h*.38f)
                path.lineTo(w*.84f,h*.49f);path.lineTo(w*.18f,h*.49f);path.close()
                path.moveTo(w*.24f,h*.49f);path.lineTo(w*.24f,h*.86f)
                path.lineTo(w*.76f,h*.86f);path.lineTo(w*.76f,h*.49f)
                path.moveTo(w*.41f,h*.86f);path.lineTo(w*.41f,h*.65f)
                path.lineTo(w*.60f,h*.65f);path.lineTo(w*.60f,h*.86f);stroke()
            }
            "user" -> {
                drawCircle(color,w*.17f,center=androidx.compose.ui.geometry.Offset(w*.5f,h*.29f),
                    style=Stroke(1.65.dp.toPx()))
                path.moveTo(w*.20f,h*.84f)
                path.quadraticTo(w*.21f,h*.55f,w*.5f,h*.57f)
                path.quadraticTo(w*.79f,h*.55f,w*.80f,h*.84f);stroke()
            }
            "info" -> {
                drawCircle(color,w*.38f,center=androidx.compose.ui.geometry.Offset(w*.5f,h*.5f),
                    style=Stroke(1.65.dp.toPx()))
                path.moveTo(w*.5f,h*.46f);path.lineTo(w*.5f,h*.72f);stroke()
                drawCircle(color,w*.045f,center=androidx.compose.ui.geometry.Offset(w*.5f,h*.30f))
            }
            "delete" -> {
                path.moveTo(w*.875f,h*.25f);path.lineTo(w*.333f,h*.25f)
                path.lineTo(w*.125f,h*.5f);path.lineTo(w*.333f,h*.75f)
                path.lineTo(w*.875f,h*.75f);path.close()
                path.moveTo(w*.5f,h*.4167f);path.lineTo(w*.6667f,h*.5833f)
                path.moveTo(w*.6667f,h*.4167f);path.lineTo(w*.5f,h*.5833f);stroke()
            }
            "remove" -> {
                path.moveTo(w*.25f,h*.25f);path.lineTo(w*.75f,h*.75f)
                path.moveTo(w*.75f,h*.25f);path.lineTo(w*.25f,h*.75f);stroke()
            }
        }
    }
}
@Composable
internal fun RegistrationIntro() {
    Column(Modifier.fillMaxWidth()) {
    RegistrationHeading("매장 등록은\n이렇게 진행돼요",
        "10분 정도 걸려요. 중간에 멈춰도 입력한 내용은 남아 있어요.")
    Spacer(Modifier.height(32.dp))
    val steps=listOf(
        "사업자 정보 확인" to "사업자등록번호, 대표자 성명, 개업일",
        "매장 정보 입력" to "이름, 사진, 주소, 연락처",
        "메뉴판 사진 올리기" to "최대 15장",
        "운영팀 승인" to "승인 전에는 손님에게 보이지 않아요"
    )
    Column(Modifier.fillMaxWidth().testTag("registration-intro-steps")) {
        steps.forEachIndexed { i,(title,subtitle)->
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                Box(Modifier.width(32.dp).height(64.dp),contentAlignment=Alignment.TopCenter) {
                    if(i<3) Box(Modifier.width(2.dp).height(32.dp).offset(y=32.dp)
                        .background(RegistrationV4.border))
                    Box(Modifier.size(32.dp).background(RegistrationV4.elevated,CircleShape),
                        contentAlignment=Alignment.Center) {
                        Text((i+1).toString(),fontSize=14.sp,fontWeight=FontWeight.SemiBold,
                            color=RegistrationV4.secondary)
                    }
                }
                Column(Modifier.padding(top=2.dp),verticalArrangement=Arrangement.spacedBy(2.dp)) {
                    Text(title,fontSize=16.sp,lineHeight=24.sp,fontWeight=FontWeight.SemiBold,
                        color=RegistrationV4.text)
                    Text(subtitle,fontSize=14.sp,lineHeight=20.sp,color=RegistrationV4.secondary)
                }
            }
        }
    }
    Column(Modifier.fillMaxWidth().padding(top=4.dp)
        .background(RegistrationV4.surface,RoundedCornerShape(16.dp)).padding(16.dp),
        verticalArrangement=Arrangement.spacedBy(12.dp)) {
        Text("미리 준비해 주세요",fontSize=14.sp,fontWeight=FontWeight.SemiBold,
            color=RegistrationV4.text,lineHeight=21.sp)
        listOf("document" to "사업자등록증","picture" to "가게 사진 1장",
            "menu" to "메뉴판 사진").forEach { (kind,text)->
            Row(verticalAlignment=Alignment.CenterVertically,
                horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                RegistrationGlyph(kind)
                Text(text,fontSize=14.sp,lineHeight=21.sp,color=RegistrationV4.secondary)
            }
        }
    }
    }
}
@Composable
internal fun RegistrationChoice(
    icon:String,title:String,subtitle:String,tag:String?=null,onClick:()->Unit,
) {
    Row(Modifier.fillMaxWidth().heightIn(min=88.dp)
        .background(RegistrationV4.surface,RoundedCornerShape(16.dp))
        .border(1.dp,RegistrationV4.border,RoundedCornerShape(16.dp))
        .ownerQuietClick(onClick=onClick).padding(horizontal=16.dp,vertical=20.dp),
        verticalAlignment=Alignment.CenterVertically,
        horizontalArrangement=Arrangement.spacedBy(16.dp)) {
        Box(Modifier.size(44.dp).background(RegistrationV4.elevated,RoundedCornerShape(12.dp)),
            contentAlignment=Alignment.Center) {
            if(icon=="pen") V4PencilIcon(Modifier.size(22.dp),RegistrationV4.primary)
            else RegistrationGlyph(icon)
        }
        Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment=Alignment.CenterVertically,
                horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                Text(title,color=RegistrationV4.text,fontWeight=FontWeight.SemiBold,
                    fontSize=16.sp,lineHeight=24.sp)
                if(tag!=null) Box(Modifier.background(Color(0xFF503C29),RoundedCornerShape(12.dp))
                    .padding(horizontal=8.dp,vertical=1.dp)) {
                    Text(tag,color=Color(0xFFF7DFBF),fontSize=12.sp,lineHeight=18.sp)
                }
            }
            Text(subtitle,color=RegistrationV4.secondary,fontSize=14.sp,lineHeight=20.sp)
        }
        RegistrationGlyph("chevron",color=RegistrationV4.secondary)
    }
}
@Composable
internal fun RegistrationInput(
    value:String,onChange:(String)->Unit,placeholder:String,
    modifier:Modifier=Modifier,label:String?=null,
    keyboard:KeyboardType=KeyboardType.Text,readonly:Boolean=false,
    onClick:(()->Unit)?=null,tag:String?=null,highlight:Boolean=false,
) {
    var focused by androidx.compose.runtime.remember { androidx.compose.runtime.mutableStateOf(false) }
    Column(modifier.fillMaxWidth(),verticalArrangement=Arrangement.spacedBy(8.dp)) {
        if(label!=null) Text(label,color=RegistrationV4.secondary,fontSize=12.sp,lineHeight=18.sp)
        if(readonly) {
            Box(Modifier.fillMaxWidth().heightIn(min=56.dp)
                .background(RegistrationV4.surface,RoundedCornerShape(12.dp))
                .border(1.dp,RegistrationV4.primary,RoundedCornerShape(12.dp))
                .then(if(onClick!=null)Modifier.ownerQuietClick(onClick=onClick) else Modifier)
                .padding(horizontal=16.dp),contentAlignment=Alignment.CenterStart) {
                Text(value.ifEmpty{placeholder},color=if(value.isEmpty())RegistrationV4.muted
                    else RegistrationV4.text,fontSize=16.sp,lineHeight=24.sp)
            }
        } else {
            BasicTextField(value=value,onValueChange=onChange,singleLine=true,
                keyboardOptions=KeyboardOptions(keyboardType=keyboard),
                modifier=Modifier.fillMaxWidth().heightIn(min=56.dp)
                    .then(if(tag!=null)Modifier.testTag(tag) else Modifier)
                    .background(RegistrationV4.surface,RoundedCornerShape(12.dp))
                    .border(1.dp,if(focused||highlight)RegistrationV4.primary else RegistrationV4.border,
                        RoundedCornerShape(12.dp))
                    .onFocusChanged { focused=it.isFocused }
                    .padding(horizontal=16.dp),
                textStyle=TextStyle(color=RegistrationV4.text,fontSize=16.sp,lineHeight=24.sp),
                decorationBox={inner->
                    Box(Modifier.fillMaxWidth().height(56.dp),contentAlignment=Alignment.CenterStart) {
                        if(value.isEmpty())Text(placeholder,color=RegistrationV4.muted,
                            fontSize=16.sp,lineHeight=24.sp)
                        inner()
                    }
                })
        }
    }
}
@Composable
internal fun RegistrationDigitsKeypad(
    onDigit:(String)->Unit,onDelete:()->Unit,
) {
    val rows=listOf(listOf("1","2","3"),listOf("4","5","6"),
        listOf("7","8","9"),listOf("","0","⌫"))
    Column(Modifier.fillMaxWidth().padding(start=12.dp,end=12.dp,bottom=8.dp)) {
        rows.forEach { row ->
            Row(Modifier.fillMaxWidth()) {
                row.forEach { key ->
                    Box(Modifier.weight(1f).height(54.dp)
                        .then(if(key.isNotEmpty())Modifier.ownerQuietClick(onClick={
                            if(key=="⌫") onDelete() else onDigit(key)
                        }) else Modifier),
                        contentAlignment=Alignment.Center) {
                        if(key=="⌫")RegistrationGlyph("delete",color=RegistrationV4.text,size=22.dp)
                        else Text(key,color=RegistrationV4.text,fontSize=20.sp,
                            fontWeight=FontWeight.Medium,lineHeight=28.sp)
                    }
                }
            }
        }
    }
}
@Composable
internal fun RegistrationRow(label:String,value:String,onEdit:(()->Unit)?=null) {
    Row(Modifier.fillMaxWidth().heightIn(min=48.dp),
        verticalAlignment=Alignment.CenterVertically,
        horizontalArrangement=Arrangement.spacedBy(8.dp)) {
        Text(label,modifier=Modifier.width(92.dp),color=RegistrationV4.secondary,
            fontSize=14.sp,lineHeight=21.sp)
        Text(value,modifier=Modifier.weight(1f),fontSize=15.sp,
            color=RegistrationV4.text,lineHeight=22.sp,textAlign=TextAlign.End)
        if(onEdit!=null) Box(Modifier.size(width=48.dp,height=48.dp)
            .ownerQuietClick(onClick=onEdit),contentAlignment=Alignment.Center) {
            Text("수정",fontSize=14.sp,color=RegistrationV4.primary)
        }
    }
    Box(Modifier.fillMaxWidth().height(1.dp).background(RegistrationV4.border))
}
@Composable
internal fun RegistrationSuccessMark() {
    Box(Modifier.size(64.dp).background(RegistrationV4.primary,CircleShape),
        contentAlignment=Alignment.Center) {
        RegistrationGlyph("check",color=RegistrationV4.onPrimary,size=32.dp)
    }
}

/** PDF 4, 9, 10 and 19: centered and intentionally free of debug labels. */
@Composable
internal fun RegistrationCenterContent(
    title:String,subtitle:String,loading:Boolean=false,success:Boolean=true,
) {
    Column(Modifier.fillMaxWidth().testTag("registration-result"),
        horizontalAlignment=Alignment.CenterHorizontally,
        verticalArrangement=Arrangement.spacedBy(8.dp)) {
        if(loading) {
            MenuPhotoProcessingIllustration(diameter=88.dp)
            /* Disabled static illustration, preserved only for v4 comparison. */
            /*Canvas(Modifier.size(88.dp)) {
                val w=size.width;val h=size.height
                val glass=Path().apply {
                    moveTo(w*.25f,h*.15f);lineTo(w*.31f,h*.77f)
                    quadraticTo(w*.32f,h*.85f,w*.4f,h*.85f)
                    lineTo(w*.62f,h*.85f)
                    quadraticTo(w*.70f,h*.85f,w*.71f,h*.77f)
                    lineTo(w*.77f,h*.15f)
                }
                val liquid=Path().apply {
                    moveTo(w*.32f,h*.55f);lineTo(w*.69f,h*.55f)
                    lineTo(w*.66f,h*.78f)
                    quadraticTo(w*.64f,h*.81f,w*.60f,h*.81f)
                    lineTo(w*.42f,h*.81f)
                    quadraticTo(w*.38f,h*.81f,w*.37f,h*.77f)
                    close()
                }
                drawPath(liquid,RegistrationV4.primary)
                drawPath(glass,RegistrationV4.secondary,
                    style=Stroke(2.5.dp.toPx(),cap=StrokeCap.Round,join=StrokeJoin.Round))
            }*/
        } else {
            RegistrationSuccessMark()
        }
        Spacer(Modifier.height(8.dp))
        Text(title,color=RegistrationV4.text,
            style=androidx.compose.material3.MaterialTheme.typography.headlineSmall,
            lineHeight=32.sp,textAlign=TextAlign.Center)
        Text(subtitle,color=RegistrationV4.secondary,
            fontSize=14.sp,lineHeight=21.sp,textAlign=TextAlign.Center)
    }
}

@Composable
internal fun RegistrationHint(text:String) {
    Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.Top,
        horizontalArrangement=Arrangement.spacedBy(8.dp)) {
        RegistrationGlyph("check",color=Color(0xFFB9DFC8),size=16.dp)
        Text(text,color=RegistrationV4.secondary,fontSize=14.sp,lineHeight=20.sp)
    }
}
@Composable
internal fun RegistrationVisibility(public:Boolean) {
    Row(Modifier.background(if(public)Color(0xFF503C29) else RegistrationV4.elevated,
        RoundedCornerShape(20.dp)).padding(horizontal=8.dp,vertical=5.dp),
        verticalAlignment=Alignment.CenterVertically,
        horizontalArrangement=Arrangement.spacedBy(4.dp)) {
        val color=if(public)Color(0xFFF7DFBF) else RegistrationV4.secondary
        RegistrationGlyph(if(public)"store" else "user",color=color,size=16.dp)
        Text(if(public)"손님에게 보여요" else "운영팀만 봐요",
            color=color,fontSize=12.sp,lineHeight=18.sp)
    }
}
