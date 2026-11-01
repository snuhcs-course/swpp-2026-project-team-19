package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zerotoone.bottlemap.data.owner.MockBarMenuItem
import com.zerotoone.bottlemap.data.owner.MockCatalogProduct
import com.zerotoone.bottlemap.data.owner.MockMenuOption
import com.zerotoone.bottlemap.data.owner.manualMenuShortName
import com.zerotoone.bottlemap.ui.common.BmIcon
import com.zerotoone.bottlemap.ui.common.BmIconId

/** All three surfaces use the same fixed slots, so adding a discount cannot shift ml or price. */
internal fun ownerOptionDiscountActive(option: MockMenuOption, atEpochMs: Long): Boolean =
    option.discount?.let { atEpochMs >= it.startAtEpochMs && atEpochMs < it.endAtEpochMs } == true

internal val ownerMenuPriceSlotWidth = 154.dp

@Composable
internal fun OwnerMenuFlatRow(
    item: MockBarMenuItem,
    product: MockCatalogProduct?,
    brandName: String,
    nowEpochMs: Long,
    showStatus: Boolean,
    selected: Boolean = false,
    onSelect: (() -> Unit)? = null,
    onEdit: (() -> Unit)? = null,
    onStock: (() -> Unit)? = null,
) {
    val soldOut = item.soldOut
    val primary = if (soldOut) Color(0xFFB1B1B1) else V4Color.text
    val secondary = if (soldOut) Color(0xFF929292) else V4Color.sub
    val imageBackground = if (soldOut) Color(0xFF363636) else Color(0xFF40352C)
    val imageBottle = if (soldOut) Color(0xFF888888) else Color(0xFF658C7A)
    val imageLabel = if (soldOut) Color(0xFFB7B7B7) else Color(0xFFE1D2B5)
    Box(Modifier.fillMaxWidth().height(74.dp)
        .background(V4Color.background)
        .then(if (onSelect != null) Modifier.ownerQuietClick(onSelect) else Modifier)
        .testTag("manual-menu-row-" + item.barMenuItemId)) {
        Row(Modifier.fillMaxSize().padding(horizontal = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(7.dp)) {
            Box(Modifier.size(width = 37.dp, height = 49.dp)
                .background(imageBackground, RoundedCornerShape(6.dp))
                .border(1.dp, if (soldOut) Color(0xFF686868) else V4Color.line,
                    RoundedCornerShape(6.dp)), contentAlignment = Alignment.Center) {
                Canvas(Modifier.size(width = 27.dp, height = 40.dp)) {
                    val u = size.width / 27f
                    drawRect(if (soldOut) Color(0xFF999999) else Color(0xFF967F58),
                        Offset(10 * u, 0f), Size(7 * u, 7 * u))
                    drawRoundRect(imageBottle, Offset(4 * u, 7 * u), Size(19 * u, 31 * u),
                        cornerRadius = CornerRadius(3 * u))
                    drawRect(imageLabel, Offset(6 * u, 18 * u), Size(15 * u, 12 * u))
                }
            }
            Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                val display = product?.let {
                    manualMenuShortName(it.copy(
                        displayName = item.displayNameOverride ?: it.displayName), brandName)
                } ?: "상품 정보 없음"
                Text(display, modifier = Modifier.weight(1f, fill = false),
                    color = primary, fontSize = 12.sp, fontWeight = FontWeight.Bold,
                    maxLines = 2, overflow = TextOverflow.Ellipsis)
                if (showStatus) {
                    Box(Modifier.border(1.dp, if (soldOut) Color(0xFF737373)
                        else V4Color.line, RoundedCornerShape(4.dp))
                        .padding(horizontal = 3.dp, vertical = 1.dp)) {
                        Text(if (soldOut) "품절" else "판매 중",
                            color = secondary, fontSize = 9.sp, maxLines = 1)
                    }
                }
            }
            Column(Modifier.width(ownerMenuPriceSlotWidth),
                horizontalAlignment = Alignment.End,
                verticalArrangement = Arrangement.spacedBy(3.dp)) {
                item.options.take(3).forEach { option ->
                    OwnerMenuPriceLine(option, nowEpochMs, soldOut)
                }
                if (item.options.isEmpty()) Text("가격 없음", color = secondary, fontSize = 10.sp)
            }
        }
        if (selected && onEdit != null && onStock != null) {
            // Deliberately wider than the total price column: even the discount badge
            // at its leading edge is covered, without changing the product row height.
            Row(Modifier.align(Alignment.CenterEnd).width(ownerMenuPriceSlotWidth + 6.dp)
                .fillMaxHeight().background(V4Color.background)
                .padding(horizontal = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically) {
                OwnerMenuRowAction("수정", BmIconId.REVIEW, onEdit,
                    Modifier.weight(1f).testTag("manual-menu-row-edit"))
                OwnerMenuRowAction(if (soldOut) "재개" else "품절",
                    BmIconId.ERROR, onStock,
                    Modifier.weight(1f).testTag("manual-menu-row-stock"))
            }
        }
    }
}

/** Discount badge is in a reserved leading slot: ml and right-edge prices never move. */
@Composable
internal fun OwnerMenuPriceLine(option: MockMenuOption, atEpochMs: Long, soldOut: Boolean = false) {
    val active = ownerOptionDiscountActive(option, atEpochMs)
    val textColor = if (soldOut) Color(0xFF999999) else V4Color.text
    val priceColor = if (soldOut) Color(0xFF999999) else V4Color.sub
    Row(Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(3.dp)) {
        Box(Modifier.width(28.dp), contentAlignment = Alignment.CenterEnd) {
            if (active) Box(Modifier.background(
                if (soldOut) Color(0xFF414141) else Color(0xFF4B3826),
                RoundedCornerShape(3.dp))
                .border(1.dp, if (soldOut) Color(0xFF666666) else Color(0xFF9C7A52),
                    RoundedCornerShape(3.dp))
                .padding(horizontal = 2.dp)) {
                Text("할인", color = if (soldOut) Color(0xFFB0B0B0)
                    else Color(0xFFF7DFBF), fontSize = 8.sp, maxLines = 1)
            }
        }
        Text(option.pourMl?.toString()?.plus("ml") ?: option.label.orEmpty(),
            modifier = Modifier.width(39.dp), color = textColor,
            fontSize = 10.sp, maxLines = 1)
        Text("%,d원".format(option.displayPrice(atEpochMs)),
            modifier = Modifier.weight(1f),
            color = priceColor, fontSize = 10.sp,
            maxLines = 1, textAlign = TextAlign.End)
    }
}

@Composable
private fun OwnerMenuRowAction(
    label: String, icon: BmIconId, onClick: () -> Unit, modifier: Modifier
) {
    Column(modifier.height(49.dp)
        .background(V4Color.elevated, RoundedCornerShape(7.dp))
        .border(1.dp, V4Color.line, RoundedCornerShape(7.dp))
        .ownerQuietClick(onClick), horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center) {
        BmIcon(icon, null, Modifier.size(16.dp), tint = V4Color.sub)
        Spacer(Modifier.height(2.dp))
        Text(label, color = V4Color.text, fontSize = 10.sp)
    }
}
