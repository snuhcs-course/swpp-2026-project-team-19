package com.zerotoone.bottlemap.ui.customer

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.draw.clip
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
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zerotoone.bottlemap.data.MapBar
import com.zerotoone.bottlemap.data.NearbyCoordinate
import com.zerotoone.bottlemap.ui.common.servingDisplayLabel
import com.zerotoone.bottlemap.ui.theme.BottleMapPalette
import java.time.Instant
import java.time.ZonedDateTime

/** Same 22dp centered chevron and gold 2dp round strokes as the Owner hours toggle. */
@Composable
internal fun P18DetailCategoryChevron(open:Boolean) {
    // Mirror vertically around its own CENTER. Rotating 180 degrees used to
    // make the arms travel sideways and looked unlike the hours toggle.
    val flip by animateFloatAsState(
        targetValue=if(open)-1f else 1f,
        animationSpec=tween(durationMillis=160),label="categoryChevronFlip")
    Canvas(Modifier.size(22.dp).graphicsLayer { scaleY=flip }) {
        val w=2.dp.toPx()
        drawLine(P18Gold,Offset(size.width*.18f,size.height*.35f),
            Offset(size.width*.5f,size.height*.65f),strokeWidth=w,cap=StrokeCap.Round)
        drawLine(P18Gold,Offset(size.width*.5f,size.height*.65f),
            Offset(size.width*.82f,size.height*.35f),strokeWidth=w,cap=StrokeCap.Round)
    }
}

/** Directly mirrors OwnerPreviewHtmlV4Screen.V4PreviewGlyph dimensions/path. */
@Composable
internal fun P18PreviewGlyph(kind:String,modifier:Modifier=Modifier,accent:Boolean=false) {
    Canvas(modifier) {
        val u=size.minDimension/24f
        val tint=if(accent)P18Gold else P18Muted
        val path=Path()
        if(kind=="location") {
            path.moveTo(12*u,22*u)
            path.cubicTo(9*u,18*u,4*u,13*u,4*u,9*u)
            path.cubicTo(4*u,4*u,7*u,2*u,12*u,2*u)
            path.cubicTo(17*u,2*u,20*u,4*u,20*u,9*u)
            path.cubicTo(20*u,13*u,15*u,18*u,12*u,22*u)
            drawPath(path,tint,style=Stroke(width=1.8.dp.toPx(),
                cap=StrokeCap.Round,join=StrokeJoin.Round))
            drawCircle(tint,radius=2.5f*u,center=Offset(12*u,9*u),
                style=Stroke(width=1.8.dp.toPx()))
        } else {
            path.moveTo(5*u,4.5f*u)
            path.lineTo(8.5f*u,8*u)
            path.lineTo(6.8f*u,10*u)
            path.cubicTo(8.4f*u,13.6f*u,10.4f*u,15.6f*u,14*u,17.2f*u)
            path.lineTo(16*u,15.5f*u)
            path.lineTo(19.5f*u,19*u)
            path.cubicTo(20.6f*u,20.3f*u,19.1f*u,21.7f*u,17.5f*u,21*u)
            path.cubicTo(10*u,20*u,4*u,14*u,3*u,6.5f*u)
            path.cubicTo(2.7f*u,4.7f*u,3.5f*u,3.8f*u,5*u,4.5f*u)
            path.close()
            drawPath(path,tint,style=Stroke(width=1.8.dp.toPx(),
                cap=StrokeCap.Round,join=StrokeJoin.Round))
        }
    }
}

/** Matches Owner preview: 7dp corner, 7px-ish inline padding, 15dp line icon. */
@Composable
internal fun P18PreviewSmallButton(label:String,kind:String,onClick:()->Unit) {
    Row(Modifier.background(P18Surface,RoundedCornerShape(7.dp))
        .border(1.dp,P18Line,RoundedCornerShape(7.dp))
        .clickable(onClick=onClick)
        .padding(horizontal=7.dp,vertical=7.dp),
        verticalAlignment=Alignment.CenterVertically,
        horizontalArrangement=Arrangement.spacedBy(4.dp)) {
        P18PreviewGlyph(kind,Modifier.size(15.dp))
        Text(label,fontSize=11.sp,color=P18Text,maxLines=1)
    }
}

/** The Owner preview uses a separate bordered elevated '복사' button. */
@Composable
internal fun P18PreviewCopy(onClick:()->Unit,enabled:Boolean=true) {
    Box(Modifier.background(P18Elevated,RoundedCornerShape(7.dp))
        .border(1.dp,P18Line,RoundedCornerShape(7.dp))
        .clickable(enabled=enabled,onClick=onClick)
        .padding(horizontal=10.dp,vertical=7.dp)) {
        Text("복사",fontSize=11.sp,color=if(enabled)P18Gold else P18Muted)
    }
}

/** Real Kakao native map using the coordinates from the *published* bar-detail API. */
@Composable
internal fun P18PublishedBarMap(bar:BarDetailUiModel) {
    P18InlineBarMap(bar.barId,bar.name,bar.address,bar.latitude,bar.longitude)
}

/** A single map implementation shared by live Customer detail and local Owner preview. */
@Composable
internal fun P18InlineBarMap(
    barId:String, name:String, address:String,latitude:Double?,longitude:Double?,
) {
    val location=latitude?.let { lat ->
        longitude?.let { lng -> NearbyCoordinate(lat,lng) }
    }?.takeIf { it.isValid() }
    Box(Modifier.fillMaxWidth().height(190.dp)
        .clip(RoundedCornerShape(9.dp))
        .background(P18Soft,RoundedCornerShape(9.dp))
        .testTag("customer-detail-native-map"),
        contentAlignment=Alignment.Center) {
        if(location==null) {
            Text("매장 위치 정보가 없습니다.",color=P18Muted,fontSize=12.sp)
        } else {
            NearbyKakaoMap(
                origin=location,
                bars=listOf(MapBar(barId,name,address,location)),
                selectedBarId=barId,focusTarget=null,focusBarId=null,
                initialCamera=null,listCovered=false,
                searchedPlace=null,focusSearchedPlace=null,
                onSearchedPlaceFocusApplied={},onFocusApplied={},
                onCameraChanged={_,_->},onMapCameraMoving={},
                onMapViewportUnavailable={},viewportRetryToken=0,
                onSelectBar={},onViewportChanged={},recenterToken=0,
                onMapViewChanged={},modifier=Modifier.fillMaxSize(),
                p18SimplePins=false,showOriginMarker=false,
            )
        }
    }
}

private fun customerDiscountActive(
    option:BarMenuOptionUiModel,now:Instant,
):Boolean = option.discount?.let {
    runCatching {now>=Instant.parse(it.startsAt) && now<Instant.parse(it.endsAt)}
        .getOrDefault(false)
}==true

/** OwnerSharedMenuRow geometry: 37x49 photo, 129dp price slot, 30dp ml, 10sp price. */
@Composable
internal fun P18OwnerParityMenuRow(
    item:BarMenuItemUiModel,highlighted:Boolean,now:ZonedDateTime,
) {
    val measurer=rememberTextMeasurer()
    val density=LocalDensity.current
    val timestamp=now.toInstant()
    val measuredPricePx=item.options.maxOfOrNull { option ->
        measurer.measure(
            p18Price(option.priceKrw?.let{
                p18EffectivePrice(it,option.discount,timestamp)
            } ?: 0),
            style=TextStyle(fontSize=10.sp),maxLines=1,
        ).size.width
    } ?: 0
    val priceWidth=with(density) {
        maxOf(129.dp,measuredPricePx.toDp()+27.dp+30.dp+10.dp)
    }
    // Owner's currently published menu and Customer use the same compact row.
    val rowHeight=maxOf(66,item.options.size*16+10).dp
    BoxWithConstraints(Modifier.fillMaxWidth().height(rowHeight)) {
        if(highlighted) {
            // Extend the highlight BEYOND the fixed content slots, not into them.
            // Avoids a gold border visually colliding with price/volume or bottle.
            Box(Modifier.offset(x=(-8).dp).width(maxWidth+16.dp)
                .fillMaxHeight()
                .background(P18Elevated,RoundedCornerShape(9.dp))
                .border(1.5.dp,P18Gold,RoundedCornerShape(9.dp)))
        } else Box(Modifier.fillMaxSize().background(P18Bg))
        Row(Modifier.fillMaxSize().padding(horizontal=4.dp),
            verticalAlignment=Alignment.CenterVertically,
            horizontalArrangement=Arrangement.spacedBy(7.dp)) {
            Box(Modifier.size(width=37.dp,height=49.dp)
                .background(Color(0xFF40352C),RoundedCornerShape(6.dp))
                .border(1.dp,P18Line,RoundedCornerShape(6.dp)),
                contentAlignment=Alignment.Center) {
                Canvas(Modifier.size(width=27.dp,height=40.dp)) {
                    val u=size.width/27f
                    drawRect(Color(0xFF967F58),Offset(10*u,0f),
                        Size(7*u,7*u))
                    drawRoundRect(Color(0xFF658C7A),Offset(4*u,7*u),
                        Size(19*u,31*u),cornerRadius=CornerRadius(3*u))
                    drawRect(Color(0xFFE1D2B5),Offset(6*u,18*u),
                        Size(15*u,12*u))
                }
            }
            Column(Modifier.weight(1f),
                verticalArrangement=Arrangement.spacedBy(4.dp)) {
                Text(item.menuDisplayName,color=P18Text,fontSize=12.sp,
                    fontWeight=FontWeight.Bold,maxLines=2,
                    overflow=TextOverflow.Ellipsis)
                if(highlighted) {
                    Box(Modifier.background(P18Gold,RoundedCornerShape(20.dp))
                        .padding(horizontal=6.dp,vertical=1.dp)) {
                        Text("찾은 메뉴",fontSize=10.5.sp,
                            lineHeight=15.sp,fontWeight=FontWeight.Bold,
                            color=BottleMapPalette.onPrimary)
                    }
                }
            }
            Column(Modifier.width(priceWidth),
                horizontalAlignment=Alignment.End,
                verticalArrangement=Arrangement.spacedBy(3.dp)) {
                item.options.forEach { option ->
                    val active=customerDiscountActive(option,timestamp)
                    Row(Modifier.fillMaxWidth(),
                        verticalAlignment=Alignment.CenterVertically,
                        horizontalArrangement=Arrangement.spacedBy(3.dp)) {
                        Box(Modifier.width(27.dp),
                            contentAlignment=Alignment.CenterEnd) {
                            if(active) Box(Modifier.background(Color(0xFF4B3826),
                                RoundedCornerShape(3.dp))
                                .border(1.dp,Color(0xFF9C7A52),RoundedCornerShape(3.dp))
                                .padding(3.dp)) {
                                Text("할인",color=Color(0xFFF7DFBF),
                                    fontSize=8.sp,lineHeight=8.sp,maxLines=1)
                            }
                        }
                        Text(servingDisplayLabel(option.pourMl,option.label),
                            Modifier.width(30.dp),color=P18Text,fontSize=10.sp,
                            maxLines=1,textAlign=TextAlign.End)
                        Text(option.priceKrw?.let{
                            p18Price(p18EffectivePrice(it,option.discount,timestamp))
                        } ?: option.text,
                            modifier=Modifier.weight(1f),color=P18Muted,fontSize=10.sp,
                            maxLines=1,textAlign=TextAlign.End)
                    }
                }
                if(item.options.isEmpty())
                    Text("가격 없음",color=P18Muted,fontSize=10.sp)
            }
        }
    }
}
