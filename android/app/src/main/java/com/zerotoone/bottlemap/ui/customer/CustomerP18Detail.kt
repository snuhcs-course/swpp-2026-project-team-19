
package com.zerotoone.bottlemap.ui.customer

import android.content.Intent
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.zerotoone.bottlemap.data.MapBar
import com.zerotoone.bottlemap.data.NearbyCoordinate
import com.zerotoone.bottlemap.network.BarOperatingExceptionDto
import com.zerotoone.bottlemap.network.BarWeeklyHoursDto
import com.zerotoone.bottlemap.ui.common.BmIcon
import com.zerotoone.bottlemap.ui.common.BmIconId
import com.zerotoone.bottlemap.ui.theme.BottleMapPalette
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import java.net.URL
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import java.time.ZonedDateTime
import java.util.Locale

private val KST=ZoneId.of("Asia/Seoul")

internal data class P18BusinessStatus(val text:String,val next:String?=null,
    val note:String?=null, val open:Boolean=false)

/** API §3.15.5: include overnight carryover and current operating exceptions. */
internal fun p18BusinessStatus(
    hours:List<BarWeeklyHoursDto>, exception:BarOperatingExceptionDto?,
    at:ZonedDateTime,
):P18BusinessStatus {
    val day=at.withZoneSameInstant(KST).toLocalDate()
    val now=at.withZoneSameInstant(KST).toLocalTime()
    val prev=day.minusDays(1)
    fun covered(date:LocalDate):Boolean = exception!=null &&
        runCatching{date>=LocalDate.parse(exception.startDate) &&
            date<=LocalDate.parse(exception.endDate)}.getOrDefault(false)
    fun effective(date:LocalDate):Pair<LocalTime,LocalTime>? {
        if(covered(date) && exception!=null) {
            if(exception.kind!="custom_hours")return null
            return runCatching {LocalTime.parse(requireNotNull(exception.openTime)) to
                LocalTime.parse(requireNotNull(exception.closeTime))}.getOrNull()
        }
        val item=hours.firstOrNull{it.dayOfWeek==date.dayOfWeek.value}
        if(item==null || item.closed)return null
        return runCatching {LocalTime.parse(requireNotNull(item.openTime)) to
            LocalTime.parse(requireNotNull(item.closeTime))}.getOrNull()
    }
    val note=if(covered(day) || covered(prev)) exception?.note else null
    if(covered(day) && exception?.kind!="custom_hours")
        return P18BusinessStatus("임시 휴무",note=note)
    val old=effective(prev)
    if(old!=null && old.second<old.first && now<old.second)
        return P18BusinessStatus("영업 중","종료 ${old.second}",note,true)
    val current=effective(day)
    if(current!=null && now>=current.first &&
        (current.second<current.first || now<current.second))
        return P18BusinessStatus("영업 중",
            (if(current.second<current.first)"익일 " else "")+
                current.second.toString()+" 종료",note,true)
    val available=covered(day) && exception?.kind=="custom_hours" ||
        hours.any {it.dayOfWeek==day.dayOfWeek.value}
    return P18BusinessStatus(if(available)"영업 종료" else "영업시간 정보 없음",note=note)
}

@Composable
internal fun P18RemoteBarPhoto(url:String?,modifier:Modifier=Modifier) {
    val bitmap by produceState<androidx.compose.ui.graphics.ImageBitmap?>(null,url) {
        value=if(url.isNullOrBlank())null else withContext(Dispatchers.IO) {
            runCatching {
                val connection=URL(url).openConnection()
                connection.connectTimeout=10000
                connection.readTimeout=10000
                connection.getInputStream().use {stream->
                    BitmapFactory.decodeStream(stream,null,BitmapFactory.Options().apply {
                        inSampleSize=2
                    })?.asImageBitmap()
                }
            }.getOrNull()
        }
    }
    if(bitmap!=null) Image(requireNotNull(bitmap),null,
        modifier=modifier,contentScale=ContentScale.Crop)
    else Box(modifier.background(P18Soft),contentAlignment=Alignment.Center) {
        BmIcon(BmIconId.BAR,"매장 사진 없음",Modifier.size(32.dp),tint=P18Muted)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun CustomerP18BarDetail(
    bar:BarDetailUiModel,
    empty:EmptyMenuReason?,
    onBack:()->Unit,
    highlightProductId:String?,
) {
    val context=LocalContext.current
    var photoIndex by rememberSaveable(bar.barId) {mutableIntStateOf(0)}
    var photoFull by rememberSaveable {mutableStateOf(false)}
    var hoursVisible by remember {mutableStateOf(false)}
    var mapVisible by rememberSaveable {mutableStateOf(false)}
    var phoneVisible by rememberSaveable {mutableStateOf(false)}
    var menuQuery by rememberSaveable(bar.barId) {mutableStateOf("")}
    var collapsed by rememberSaveable(bar.barId) {mutableStateOf(setOf("cocktail","food"))}
    var at by remember {mutableStateOf(ZonedDateTime.now(KST))}
    LaunchedEffect(bar.barId) { while(true) { at=ZonedDateTime.now(KST);delay(30000) } }
    val open=p18BusinessStatus(bar.weeklyHours,bar.operatingException,at)
    val photos=bar.photos
    val selectedPhoto=photos.getOrNull(if(photos.isEmpty())0 else photoIndex.mod(photos.size))
    if(hoursVisible) ModalBottomSheet(onDismissRequest={hoursVisible=false},
        containerColor=P18Surface,contentColor=P18Text) {
        Column(Modifier.fillMaxWidth().padding(horizontal=20.dp,vertical=12.dp),
            verticalArrangement=Arrangement.spacedBy(12.dp)) {
            Text("영업시간",fontSize=20.sp,fontWeight=FontWeight.Bold,color=P18Text)
            val names=listOf("월","화","수","목","금","토","일")
            (1..7).forEach { d ->
                val h=bar.weeklyHours.firstOrNull{it.dayOfWeek==d}
                Row(Modifier.fillMaxWidth().heightIn(min=36.dp),
                    horizontalArrangement=Arrangement.SpaceBetween) {
                    Text(names[d-1],color=P18Muted,fontSize=14.sp)
                    Text(when {
                        h==null->"정보 없음"
                        h.closed->"휴무"
                        else->"${h.openTime} ~ ${if(h.closeTime.orEmpty()<h.openTime.orEmpty())"익일 " else ""}${h.closeTime}"
                    },color=P18Text,fontSize=14.sp)
                }
            }
            P18Action("닫기",{hoursVisible=false},modifier=Modifier.fillMaxWidth())
            Spacer(Modifier.height(12.dp))
        }
    }
    if(photoFull && selectedPhoto!=null) Dialog(onDismissRequest={photoFull=false},
        properties=DialogProperties(usePlatformDefaultWidth=false)) {
        Column(Modifier.fillMaxWidth().fillMaxHeight(.82f)
            .background(P18Bg,RoundedCornerShape(14.dp)).padding(16.dp)) {
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.End) {
                TextButton(onClick={photoFull=false}){Text("닫기 ×",color=P18Text)}
            }
            P18RemoteBarPhoto(selectedPhoto.imageUrl,Modifier.fillMaxWidth().weight(1f))
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween,
                verticalAlignment=Alignment.CenterVertically) {
                TextButton(onClick={photoIndex=(photoIndex+photos.size-1)%photos.size}) {
                    Text("‹ 이전",color=P18Gold)
                }
                Text("${photoIndex+1}/${photos.size}",color=P18Text)
                TextButton(onClick={photoIndex=(photoIndex+1)%photos.size}) {
                    Text("다음 ›",color=P18Gold)
                }
            }
        }
    }
    Column(Modifier.fillMaxSize().background(P18Bg).testTag("customer-bar-detail")) {
        Row(Modifier.fillMaxWidth().height(50.dp).padding(start=6.dp,end=16.dp),
            verticalAlignment=Alignment.CenterVertically) {P18Back(onBack)}
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(start=20.dp,end=20.dp,top=13.dp,bottom=24.dp),
            verticalArrangement=Arrangement.spacedBy(10.dp)) {
            Text(bar.name,fontSize=22.sp,lineHeight=30.sp,
                style=MaterialTheme.typography.headlineSmall,color=P18Text)
            var dragDistance by remember {mutableStateOf(0f)}
            Box(Modifier.fillMaxWidth().height(185.dp)
                .clip(RoundedCornerShape(11.dp))
                .background(P18Soft)
                .pointerInput(photos.size) {
                    detectHorizontalDragGestures(onDragStart={dragDistance=0f},
                        onHorizontalDrag={c,d->dragDistance+=d;c.consume()},
                        onDragEnd={
                            if(photos.size>1) {
                                if(dragDistance>55)photoIndex=(photoIndex+photos.size-1)%photos.size
                                if(dragDistance< -55)photoIndex=(photoIndex+1)%photos.size
                            }
                            dragDistance=0f
                        })
                }
                .clickable(enabled=photos.isNotEmpty()){photoFull=true},
                contentAlignment=Alignment.Center) {
                P18RemoteBarPhoto(selectedPhoto?.imageUrl,Modifier.fillMaxSize())
                if(photos.isNotEmpty()) Text("${photoIndex+1}/${photos.size}",
                    Modifier.align(Alignment.BottomEnd).padding(10.dp)
                        .background(P18Bg.copy(alpha=.85f),RoundedCornerShape(6.dp))
                        .padding(horizontal=8.dp,vertical=4.dp),
                    color=P18Text,fontSize=11.sp)
            }
            if(photos.size>1) Row(Modifier.fillMaxWidth(),
                horizontalArrangement=Arrangement.Center) {
                photos.forEachIndexed{ i,_->
                    Box(Modifier.padding(horizontal=4.dp).size(7.dp)
                        .background(if(i==photoIndex)P18Gold else BottleMapPalette.outline,
                            CircleShape))
                }
            }
            if(!bar.description.isNullOrBlank())
                Text(bar.description,color=P18Muted,fontSize=12.sp,lineHeight=19.sp)
            if(bar.tags.isNotEmpty()) {
                Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                    horizontalArrangement=Arrangement.spacedBy(6.dp)) {
                    bar.tags.forEach { tag ->
                        Box(Modifier.heightIn(min=25.dp)
                            .background(P18Elevated,RoundedCornerShape(50))
                            .border(1.dp,P18Line,RoundedCornerShape(50))
                            .padding(horizontal=9.dp,vertical=3.dp)) {
                            Text(tag,color=P18Text,fontSize=11.sp)
                        }
                    }
                }
            }
            Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically,
                horizontalArrangement=Arrangement.SpaceBetween) {
                Row(Modifier.weight(1f),verticalAlignment=Alignment.CenterVertically,
                    horizontalArrangement=Arrangement.spacedBy(6.dp)) {
                    Text(open.text,color=if(open.open)BottleMapPalette.success else P18Muted,
                        fontSize=14.sp,fontWeight=FontWeight.Bold)
                    open.next?.let {Text(it,fontSize=11.sp,color=P18Muted)}
                    Text("⌄",Modifier.size(32.dp).clickable{hoursVisible=true},
                        color=P18Gold,textAlign=TextAlign.Center)
                }
                P18Action("지도",{mapVisible=!mapVisible})
                Spacer(Modifier.width(6.dp))
                if(!bar.phone.isNullOrBlank()) P18Action("전화",{
                    phoneVisible=!phoneVisible
                })
            }
            open.note?.let {Text(it,color=P18Muted,fontSize=12.sp)}
            if(phoneVisible && !bar.phone.isNullOrBlank()) {
                Row(Modifier.fillMaxWidth().heightIn(min=48.dp)
                    .background(P18Surface,RoundedCornerShape(10.dp))
                    .padding(horizontal=12.dp),
                    horizontalArrangement=Arrangement.SpaceBetween,
                    verticalAlignment=Alignment.CenterVertically) {
                    Text(bar.phone,color=P18Text,fontSize=14.sp)
                    TextButton(onClick={
                        val dial=Intent(Intent.ACTION_DIAL,Uri.parse("tel:"+bar.phone))
                        runCatching {context.startActivity(dial)}
                    }) {Text("전화 걸기",color=P18Gold)}
                }
            }
            if(mapVisible) {
                val location=bar.latitude?.let{lat->
                    bar.longitude?.let{lng->NearbyCoordinate(lat,lng)}
                }?.takeIf{it.isValid()}
                if(location!=null) {
                    NearbyKakaoMap(origin=location,
                        bars=listOf(MapBar(bar.barId,bar.name,bar.address,location)),
                        selectedBarId=bar.barId,focusTarget=null,focusBarId=null,
                        initialCamera=null,listCovered=false,searchedPlace=null,
                        focusSearchedPlace=null,onSearchedPlaceFocusApplied={},
                        onFocusApplied={},onCameraChanged={_,_->},
                        onMapCameraMoving={},onMapViewportUnavailable={},
                        viewportRetryToken=0,onSelectBar={},
                        onViewportChanged={},recenterToken=0,
                        onMapViewChanged={},
                        modifier=Modifier.fillMaxWidth().height(230.dp)
                            .clip(RoundedCornerShape(12.dp)))
                }
                Text(bar.address,color=P18Muted,fontSize=13.sp)
            }
            Row(Modifier.fillMaxWidth().padding(top=6.dp),
                horizontalArrangement=Arrangement.SpaceBetween,
                verticalAlignment=Alignment.CenterVertically) {
                Text("메뉴",color=P18Text,fontSize=16.sp,fontWeight=FontWeight.Bold)
                Text(bar.publishedAtText?.replace("갱신","최근 갱신")
                    ?: "최근 갱신 기록 없음",color=P18Muted,fontSize=11.sp)
            }
            P18SearchField(menuQuery,{menuQuery=it},{},
                placeholder="메뉴 검색",modifier=Modifier.fillMaxWidth().height(48.dp),
                focused=false)
            if(empty!=null) Text(if(empty==EmptyMenuReason.NO_PUBLISHED_MENU)
                "등록된 메뉴가 없습니다" else "현재 판매 중인 메뉴가 없습니다",
                modifier=Modifier.fillMaxWidth().padding(16.dp),
                color=P18Muted,textAlign=TextAlign.Center)
            val filtered=bar.items.filter {
                menuQuery.isBlank() || it.menuDisplayName.contains(menuQuery,true) ||
                    it.brandName.orEmpty().contains(menuQuery,true)
            }
            val categories=filtered.groupBy{it.category.ifBlank{"whisky"}}
            categories.forEach { (category,menu)->
                val label=when(category.lowercase(Locale.ROOT)) {
                    "whisky"->"위스키"
                    "cocktail"->"칵테일"
                    "food"->"안주"
                    else->category
                }
                Row(Modifier.fillMaxWidth().heightIn(min=35.dp)
                    .background(P18Surface,RoundedCornerShape(7.dp))
                    .clickable {
                        collapsed=if(category in collapsed)collapsed-category
                        else collapsed+category
                    }.padding(horizontal=12.dp,vertical=6.dp),
                    horizontalArrangement=Arrangement.SpaceBetween,
                    verticalAlignment=Alignment.CenterVertically) {
                    Text(label,color=P18Text,fontSize=14.sp,fontWeight=FontWeight.Bold)
                    Text(if(category in collapsed)"⌄" else "⌃",color=P18Muted)
                }
                if(category !in collapsed) {
                    menu.groupBy{it.brandName.orEmpty()}.forEach { (brand,items)->
                        if(brand.isNotBlank()) Text(brand,
                            modifier=Modifier.padding(start=4.dp,top=6.dp),
                            color=P18Gold,fontSize=13.sp,fontWeight=FontWeight.Bold)
                        items.forEach { item ->
                            val highlighted=highlightProductId!=null &&
                                highlightProductId==item.productId
                            Row(Modifier.fillMaxWidth()
                                .then(if(highlighted)Modifier.background(P18Elevated,
                                    RoundedCornerShape(10.dp))
                                    .border(1.5.dp,P18Gold,RoundedCornerShape(10.dp))
                                    else Modifier)
                                .padding(horizontal=5.dp,vertical=9.dp),
                                verticalAlignment=Alignment.CenterVertically,
                                horizontalArrangement=Arrangement.spacedBy(9.dp)) {
                                Box(Modifier.width(41.dp).height(53.dp)
                                    .background(P18Soft,RoundedCornerShape(7.dp))
                                    .border(1.dp,BottleMapPalette.outline,
                                        RoundedCornerShape(7.dp)),contentAlignment=Alignment.Center) {
                                    P18Bottle(item.menuDisplayName,24.dp,42.dp)
                                }
                                Column(Modifier.weight(1f),
                                    verticalArrangement=Arrangement.spacedBy(4.dp)) {
                                    Text(item.menuDisplayName,color=P18Text,fontSize=12.sp,
                                        fontWeight=FontWeight.Bold,lineHeight=16.sp)
                                    if(highlighted) Box(Modifier.background(P18Gold,
                                        RoundedCornerShape(20.dp))
                                        .padding(horizontal=6.dp,vertical=1.dp)) {
                                        Text("찾은 메뉴",fontSize=10.sp,
                                            color=BottleMapPalette.onPrimary)
                                    }
                                }
                                Column(Modifier.widthIn(min=116.dp),
                                    verticalArrangement=Arrangement.spacedBy(3.dp)) {
                                    item.options.forEach { option ->
                                        val active=option.discount?.let {
                                            runCatching {
                                                val now=at.toInstant()
                                                now>=Instant.parse(it.startsAt) &&
                                                    now<Instant.parse(it.endsAt)
                                            }.getOrDefault(false)
                                        }==true
                                        Row(horizontalArrangement=Arrangement.spacedBy(7.dp),
                                            verticalAlignment=Alignment.CenterVertically) {
                                            Text(option.pourMl?.let{"${it}ml"} ?:
                                                option.label.orEmpty(),fontSize=11.sp,
                                                color=P18Text,modifier=Modifier.width(44.dp),
                                                textAlign=TextAlign.End)
                                            Column(horizontalAlignment=Alignment.End) {
                                                val cost=option.priceKrw?.let {
                                            p18EffectivePrice(it,option.discount,at.toInstant())
                                        }
                                                Text(cost?.let(::p18Price) ?: option.text,
                                                    fontSize=11.sp,color=P18Muted)
                                                if(active && option.priceKrw!=null)
                                                    Text(p18Price(option.priceKrw),
                                                        textDecoration=TextDecoration.LineThrough,
                                                        color=P18Muted,fontSize=9.sp)
                                            }
                                        }
                                    }
                                }
                            }
                            Box(Modifier.fillMaxWidth().height(1.dp).background(P18Line))
                        }
                    }
                }
            }
        }
    }
}
