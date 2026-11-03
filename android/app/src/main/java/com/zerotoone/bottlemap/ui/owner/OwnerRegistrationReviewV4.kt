package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** A single visual hierarchy for the editable application review and read-only
 * application details. These are already-existing DTO fields, not an API schema. */
internal data class RegistrationReviewValues(
    val number:String,
    val representative:String,
    val openingDate:String,
    val name:String,
    val representativePhotoCount:Int?,
    val address:String?,
    val phone:String?,
    val menuPhotoCount:Int,
    val contact:String,
)

@Composable
internal fun RegistrationReviewDetails(
    values:RegistrationReviewValues,
    readOnly:Boolean,
    onEdit:(String)->Unit,
    businessVerified:Boolean=true,
) {
    val edit:(String)->(() -> Unit)? = { key ->
        if(readOnly) null else ({onEdit(key)})
    }
    Column(verticalArrangement=Arrangement.spacedBy(4.dp),
        modifier=Modifier.fillMaxWidth().testTag("registration-review-business")) {
        Row(verticalAlignment=Alignment.CenterVertically,
            horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            Text("사업자 정보",color=RegistrationV4.secondary,fontSize=14.sp)
            androidx.compose.foundation.layout.Box(
                Modifier.background(if(businessVerified)Color(0xFF244C38) else Color(0xFF503C29),
                    RoundedCornerShape(20.dp))
                    .padding(horizontal=8.dp,vertical=3.dp)) {
                Text(if(businessVerified)"확인 완료" else "운영팀이 확인 예정",
                    color=if(businessVerified)Color(0xFFB9DFC8) else Color(0xFFF7DFBF),
                    fontSize=12.sp)
            }
        }
        RegistrationRow("등록번호",values.number)
        RegistrationRow("대표자",values.representative)
        RegistrationRow("개업일",values.openingDate)
    }
    Column(verticalArrangement=Arrangement.spacedBy(4.dp),
        modifier=Modifier.fillMaxWidth().testTag("registration-review-details")) {
        Text("매장 정보",color=RegistrationV4.secondary,fontSize=14.sp)
        RegistrationRow("이름",values.name,edit("barname"))
        if(values.representativePhotoCount!=null) {
            RegistrationRow("대표 사진","${values.representativePhotoCount}장",edit("barphoto"))
            RegistrationRow("주소",values.address.orEmpty(),edit("address"))
            RegistrationRow("전화번호",values.phone?.ifBlank { "없음" } ?: "없음",edit("barphone"))
        }
        // Menu and contact ARE rows, not another section/empty-label row. This
        // gives them the exact 48dp min height and vertical center of photo.
        RegistrationRow("메뉴판","${values.menuPhotoCount}장",edit("menus"))
        RegistrationRow("연락처",values.contact,edit("contact"))
    }
    Row(Modifier.fillMaxWidth().heightIn(min=56.dp)
        .background(RegistrationV4.surface,RoundedCornerShape(12.dp))
        .padding(horizontal=12.dp,vertical=8.dp)
        .testTag("registration-review-notice"),
        horizontalArrangement=Arrangement.Center,
        verticalAlignment=Alignment.CenterVertically) {
        RegistrationGlyph("info",color=RegistrationV4.primary,size=20.dp)
        androidx.compose.foundation.layout.Spacer(Modifier.padding(start=6.dp))
        Text("운영팀 승인 전에는 매장과 메뉴가 손님에게 보이지 않아요.",
            color=RegistrationV4.secondary,fontSize=14.sp,lineHeight=20.sp,
            textAlign=TextAlign.Center)
    }
}
