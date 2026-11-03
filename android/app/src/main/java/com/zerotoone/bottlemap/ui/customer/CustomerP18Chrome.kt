package com.zerotoone.bottlemap.ui.customer

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zerotoone.bottlemap.ui.common.BmIcon
import com.zerotoone.bottlemap.ui.common.BmIconId
import com.zerotoone.bottlemap.ui.theme.BottleMapPalette
import kotlin.math.min

/** P18 02: three staggered ice cubes fall into an amber-filled outlined tumbler (2.4s loop). */
@Composable
internal fun P18IceGlass(modifier: Modifier = Modifier) {
    val transition = rememberInfiniteTransition(label = "p18-ice")
    val phase by transition.animateFloat(
        initialValue = 0f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(2400, easing = LinearEasing)),
        label = "threeIceDrops",
    )
    Canvas(modifier.size(64.dp).testTag("customer-animated-glass")) {
        val unit = min(size.width, size.height) / 24f
        val ox = (size.width - 24f * unit) / 2f
        val oy = (size.height - 24f * unit) / 2f
        withTransform({ translate(ox, oy); scale(unit, unit, pivot = Offset.Zero) }) {
            val inner = Path().apply {
                moveTo(3.5f,6.5f); lineTo(4.75f,19.25f)
                quadraticTo(4.75f,21f,6.5f,21f); lineTo(17.5f,21f)
                quadraticTo(19.25f,21f,19.25f,19.25f); lineTo(20.5f,6.5f); close()
            }
            clipPath(inner) {
                val rising = when {
                    phase < .19f -> 0f
                    phase < .80f -> -(phase - .19f) / .61f * 1.05f
                    else -> -(1f - phase) / .2f * 1.05f
                }
                val wave = Path().apply {
                    moveTo(-3f,12.8f + rising)
                    for (i in 0..15) {
                        val x = -3f + i * 2.5f
                        quadraticTo(x + 1.25f,12.45f + rising,x + 2.5f,12.8f + rising)
                    }
                    lineTo(40f,24f); lineTo(-3f,24f); close()
                }
                drawPath(wave,P18Gold)
            }
            val cubes = listOf(Offset(8.9f,16.75f),Offset(15.1f,16.75f),Offset(12f,10.8f))
            cubes.forEachIndexed { index, target ->
                val start = index * .20f
                val local = (phase - start) / .20f
                val falling = local.coerceIn(0f,1f)
                val visible = phase >= start && phase < .94f
                if (visible) {
                    val y = target.y - (1f - falling) * 7f
                    withTransform({ rotate(listOf(-5f,6f,12f)[index],Offset(target.x,y)) }) {
                        drawRoundRect(
                            color=P18Muted, topLeft=Offset(target.x-1.9f,y-1.9f),
                            size=Size(3.8f,3.8f), cornerRadius=CornerRadius(.9f,.9f),
                            style=Stroke(width=1.5f,cap=StrokeCap.Round),
                        )
                    }
                }
            }
            val outline = Path().apply {
                moveTo(3.5f,6.5f); lineTo(4.75f,19.25f)
                quadraticTo(4.75f,21f,6.5f,21f); lineTo(17.5f,21f)
                quadraticTo(19.25f,21f,19.25f,19.25f);lineTo(20.5f,6.5f)
            }
            drawPath(outline,P18Muted,style=Stroke(width=1.5f,cap=StrokeCap.Round))
        }
    }
}

@Composable
internal fun P18LoadingBody(text:String, modifier:Modifier=Modifier) {
    Column(modifier.fillMaxSize().padding(bottom=120.dp),
        horizontalAlignment=Alignment.CenterHorizontally,
        verticalArrangement=Arrangement.Center) {
        P18IceGlass()
        Spacer(Modifier.height(16.dp))
        Text(text,color=P18Text,fontSize=16.sp,lineHeight=24.sp)
    }
}

/** 48dp touch target, 20dp glyph, HTML P18 four-point inner padding. */
@Composable
internal fun P18ModeButton(
    mode:String, onClick:()->Unit, dark:Boolean=false, modifier:Modifier=Modifier,
) {
    Row(modifier.height(48.dp)
        .background(if(dark)P18Bg else P18Surface,RoundedCornerShape(12.dp))
        .then(if(dark) Modifier else Modifier.border(1.dp,P18Line,RoundedCornerShape(12.dp)))
        .clickable(onClick=onClick)
        .padding(horizontal=12.dp),verticalAlignment=Alignment.CenterVertically,
        horizontalArrangement=Arrangement.spacedBy(4.dp)) {
        if(mode=="지도") BmIcon(BmIconId.MAP,null,Modifier.size(20.dp),tint=P18Text)
        else Canvas(Modifier.size(20.dp)) {
            val line = P18Text
            val stroke=1.5.dp.toPx()
            for(y in listOf(.28f,.5f,.72f)) {
                drawCircle(line,radius=stroke*.7f,center=Offset(size.width*.18f,size.height*y))
                drawLine(line,Offset(size.width*.35f,size.height*y),
                    Offset(size.width*.85f,size.height*y),strokeWidth=stroke,cap=StrokeCap.Round)
            }
        }
        Text(mode,color=P18Text,fontSize=13.sp,fontWeight=FontWeight.SemiBold)
    }
}

@Composable
internal fun P18SortTrigger(label:String,onClick:()->Unit,modifier:Modifier=Modifier) {
    Row(modifier.heightIn(min=48.dp).clickable(onClick=onClick)
        .padding(end=8.dp),verticalAlignment=Alignment.CenterVertically,
        horizontalArrangement=Arrangement.spacedBy(6.dp)) {
        Text(label,color=P18Text,fontSize=14.sp,fontWeight=FontWeight.Medium)
        Canvas(Modifier.size(width=17.dp,height=13.dp).offset(y=(-2).dp)) {
            val w=1.7.dp.toPx()
            drawLine(P18Text,Offset(size.width*.12f,size.height*.30f),
                Offset(size.width*.50f,size.height*.73f),strokeWidth=w,cap=StrokeCap.Round)
            drawLine(P18Text,Offset(size.width*.50f,size.height*.73f),
                Offset(size.width*.88f,size.height*.30f),strokeWidth=w,cap=StrokeCap.Round)
        }
    }
}

@Composable
internal fun P18SortTick() {
    Canvas(Modifier.size(22.dp)) {
        val w=3.dp.toPx()
        drawLine(P18Gold,Offset(size.width*.15f,size.height*.52f),
            Offset(size.width*.40f,size.height*.76f),strokeWidth=w,cap=StrokeCap.Round)
        drawLine(P18Gold,Offset(size.width*.40f,size.height*.76f),
            Offset(size.width*.86f,size.height*.23f),strokeWidth=w,cap=StrokeCap.Round)
    }
}

/** Source screens 03-e1/e2/e3 and 05-e1: icon/main top and separate bottom action. */
@Composable
internal fun P18FailureBody(
    title:String, description:String, button:String, icon:BmIconId,
    onAction:()->Unit, modifier:Modifier=Modifier,
    productName:String?=null, primary:Boolean=false, topInset:Int=112,
) {
    Column(modifier.fillMaxSize(),horizontalAlignment=Alignment.CenterHorizontally) {
        Column(Modifier.weight(1f).fillMaxWidth()
            .padding(start=32.dp,end=32.dp,top=topInset.dp),
            horizontalAlignment=Alignment.CenterHorizontally,
            verticalArrangement=Arrangement.spacedBy(12.dp)) {
            if(productName!=null) {
                P18Bottle(productName)
                Text(productName,color=P18Muted,fontSize=14.sp,
                    fontWeight=FontWeight.SemiBold)
            } else if(icon == BmIconId.SEARCH) {
                // 03-e1: crossed magnifier, not a generic empty-state icon.
                Canvas(Modifier.size(48.dp)) {
                    val stroke=1.2.dp.toPx()
                    val center=Offset(size.width*.42f,size.height*.44f)
                    drawCircle(P18Muted,size.width*.27f,center,
                        style=Stroke(width=stroke,cap=StrokeCap.Round))
                    drawLine(P18Muted,Offset(size.width*.61f,size.height*.63f),
                        Offset(size.width*.85f,size.height*.85f),
                        strokeWidth=stroke,cap=StrokeCap.Round)
                    drawLine(P18Muted,Offset(size.width*.33f,size.height*.34f),
                        Offset(size.width*.51f,size.height*.52f),
                        strokeWidth=stroke,cap=StrokeCap.Round)
                    drawLine(P18Muted,Offset(size.width*.51f,size.height*.34f),
                        Offset(size.width*.33f,size.height*.52f),
                        strokeWidth=stroke,cap=StrokeCap.Round)
                }
            } else BmIcon(icon,null,Modifier.size(48.dp),
                tint=if(icon==BmIconId.ERROR) BottleMapPalette.error else P18Muted)
            Text(title,color=P18Text,
                style=MaterialTheme.typography.headlineSmall,
                fontSize=22.sp,lineHeight=30.sp,textAlign=TextAlign.Center)
            Text(description,color=P18Muted,fontSize=15.sp,lineHeight=23.sp,
                textAlign=TextAlign.Center)
        }
        Box(Modifier.fillMaxWidth().padding(start=20.dp,end=20.dp,bottom=24.dp,top=12.dp)) {
            Row(Modifier.fillMaxWidth().height(56.dp)
                .background(if(primary)P18Gold else P18Surface,RoundedCornerShape(12.dp))
                .then(if(primary)Modifier else Modifier.border(1.dp,P18Line,RoundedCornerShape(12.dp)))
                .clickable(onClick=onAction),
                horizontalArrangement=Arrangement.spacedBy(8.dp,Alignment.CenterHorizontally),
                verticalAlignment=Alignment.CenterVertically) {
                if(primary && button=="다시 시도") {
                    BmIcon(BmIconId.RETRY,null,Modifier.size(22.dp),
                        tint=BottleMapPalette.onPrimary)
                }
                Text(button,fontSize=16.sp,lineHeight=23.sp,
                    fontWeight=FontWeight.SemiBold,
                    color=if(primary)BottleMapPalette.onPrimary else P18Text)
            }
        }
    }
}

@Composable
internal fun P18LocationBanner(onEnable:()->Unit,modifier:Modifier=Modifier) {
    Row(modifier.fillMaxWidth()
        .background(P18Surface,RoundedCornerShape(12.dp))
        .padding(start=14.dp,top=6.dp,bottom=6.dp,end=6.dp),
        verticalAlignment=Alignment.CenterVertically,
        horizontalArrangement=Arrangement.spacedBy(10.dp)) {
        BmIcon(BmIconId.BAR_PIN,null,Modifier.size(20.dp),tint=P18Muted)
        Text("위치를 켜면 거리와 가까운 순을 볼 수 있어요",
            Modifier.weight(1f),color=P18Text,fontSize=14.sp,lineHeight=20.sp)
        Box(Modifier.heightIn(min=48.dp)
            .background(P18Gold,RoundedCornerShape(10.dp))
            .clickable(onClick=onEnable).padding(horizontal=14.dp),
            contentAlignment=Alignment.Center) {
            Text("위치 켜기",color=BottleMapPalette.onPrimary,fontSize=14.sp,
                fontWeight=FontWeight.SemiBold)
        }
    }
}
