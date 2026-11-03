package com.zerotoone.bottlemap.ui.customer

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.Dp

/** Pixel geometry and fill colors directly transcribed from P18 HTML SVG 40×64.
 * No guessed whisky photograph or catalog product imagery is involved.
 */
private data class P18BottleShape(
    val d:String?=null, val x:Float=0f, val y:Float=0f,
    val w:Float=0f, val h:Float=0f, val rx:Float=0f, val fill:Color,
)
private val P18BottleShapes=listOf(
    listOf(
        P18BottleShape(d="M17.4 9.5 H22.6 V15 C22.6 18 29.5 18.5 29.5 22.5 V23.2 H10.5 V22.5 C10.5 18.5 17.4 18 17.4 15 Z",fill=Color(0xFF6F9079)),
        P18BottleShape(d="M10.5 23 H29.5 L28.6 59 Q28.6 61.5 26.6 61.5 H13.4 Q11.4 61.5 11.4 59 Z",fill=Color(0xFF1F4A2E)),
        P18BottleShape(d="M11.9 42 H28.1 L27.8 56 H12.2 Z",fill=Color(0xFFF0E6CC)),
        P18BottleShape(d="M11.9 43 H28.1 L28.08 43.8 H11.92 Z",fill=Color(0xFFB06A35)),
        P18BottleShape(x=17.4f,y=12.4f,w=5.2f,h=1.5f,rx=0f,fill=Color(0xFFD69458)),
        P18BottleShape(d="M17.8 2 H22.2 Q23.3 2 23.3 3.1 V10.2 H16.7 V3.1 Q16.7 2 17.8 2 Z",fill=Color(0xFFD69458)),
    ),
    listOf(
        P18BottleShape(d="M17.7 9 H22.3 V16.5 C22.3 20 29.5 20.5 29.5 25.5 V27.5 H10.5 V25.5 C10.5 20.5 17.7 20 17.7 16.5 Z",fill=Color(0xFF9CC294)),
        P18BottleShape(d="M10.5 27.5 H29.5 V59.5 Q29.5 61.5 27.5 61.5 H12.5 Q10.5 61.5 10.5 59.5 Z",fill=Color(0xFF4F7A2A)),
        P18BottleShape(x=11.1f,y=31f,w=17.8f,h=23f,rx=0.6f,fill=Color(0xFFF6F7F2)),
        P18BottleShape(x=11.1f,y=50.6f,w=17.8f,h=1f,rx=0f,fill=Color(0xFF2F7A3E)),
        P18BottleShape(d="M18 2.5 H22 Q23.1 2.5 23.1 3.6 V9.4 H16.9 V3.6 Q16.9 2.5 18 2.5 Z",fill=Color(0xFF2F6A3A)),
    ),
    listOf(
        P18BottleShape(d="M17.2 12 H22.8 V16.6 C23.29 18.73 31.17 19.38 34 25 H6 C8.83 19.38 16.71 18.73 17.2 16.6 Z",fill=Color(0xFFD2C6B2)),
        P18BottleShape(d="M6 25 H34 C34.62 26.24 35 27.71 35 29.5 C35 41 34.4 52 33.6 58.6 Q33.2 61.5 30.4 61.5 H9.6 Q6.8 61.5 6.4 58.6 C5.6 52 5 41 5 29.5 C5 27.71 5.38 26.24 6 25 Z",fill=Color(0xFFB0702A)),
        P18BottleShape(x=8.5f,y=34f,w=23f,h=18f,rx=1f,fill=Color(0xFFF4EDDC)),
        P18BottleShape(x=8.5f,y=49f,w=23f,h=0.9f,rx=0f,fill=Color(0xFFB06A3A)),
        P18BottleShape(d="M16.2 4.6 H23.8 Q25 4.6 25 5.8 V10.2 Q25 10.8 24.4 10.8 H15.6 Q15 10.8 15 10.2 V5.8 Q15 4.6 16.2 4.6 Z",fill=Color(0xFFC77A48)),
        P18BottleShape(x=16.6f,y=10.8f,w=6.8f,h=1.6f,rx=0f,fill=Color(0xFFC77A48)),
    ),
    listOf(
        P18BottleShape(d="M17.5 9.5 H22.5 V14.5 Q22.5 16 24.5 17.6 L27.6 20.3 Q29 21.5 29 23.5 V59 Q29 61.5 26.5 61.5 H13.5 Q11 61.5 11 59 V23.5 Q11 21.5 12.4 20.3 L15.5 17.6 Q17.5 16 17.5 14.5 Z",fill=Color(0xFFCFC4BB)),
        P18BottleShape(d="M11.7 21 H28.3 Q29 21.9 29 23.5 V59 Q29 61.5 26.5 61.5 H13.5 Q11 61.5 11 59 V23.5 Q11 21.9 11.7 21 Z",fill=Color(0xFF933C1C)),
        P18BottleShape(x=11.8f,y=29f,w=16.4f,h=26f,rx=0.6f,fill=Color(0xFFF6F3EE)),
        P18BottleShape(x=11.8f,y=29f,w=16.4f,h=1.1f,rx=0f,fill=Color(0xFF3A332E)),
        P18BottleShape(d="M17 3.2 H23 Q24 3.2 24 4.2 V10.2 H16 V4.2 Q16 3.2 17 3.2 Z",fill=Color(0xFF3A3532)),
    ),
)
@Composable
internal fun P18ExactBottle(name:String, width:Dp, height:Dp) {
    val normalized=name.lowercase(java.util.Locale.ROOT)
    val index=when {
        normalized.contains("glenfiddich")||normalized.contains("글렌피딕")->0
        normalized.contains("laphroaig")||normalized.contains("라프로익")->1
        normalized.contains("balvenie")||normalized.contains("발베니")->2
        normalized.contains("macallan")||normalized.contains("맥캘란")->3
        else->2 // neutral reference silhouette only; product photos are never invented.
    }
    val shapes=P18BottleShapes[index]
    val parsed=remember(index){shapes.map {it.d?.let {d->PathParser().parsePathString(d).toPath()}}}
    Canvas(Modifier.size(width,height).testTag("customer-bottle")) {
        val sx=size.width/40f
        val sy=size.height/64f
        scale(sx,sy,pivot=Offset.Zero) {
            shapes.forEachIndexed{ i,shape ->
                val path=parsed[i]
                if(path!=null)drawPath(path,color=shape.fill)
                else drawRoundRect(shape.fill,
                    topLeft=Offset(shape.x,shape.y),size=Size(shape.w,shape.h),
                    cornerRadius=CornerRadius(shape.rx,shape.rx))
            }
        }
    }
}
