package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.background
import androidx.compose.foundation.Canvas
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zerotoone.bottlemap.data.owner.MockBar
import com.zerotoone.bottlemap.data.owner.MockBarMenuItem
import com.zerotoone.bottlemap.data.owner.MockBrand
import com.zerotoone.bottlemap.data.owner.MockCatalogProduct
import com.zerotoone.bottlemap.data.owner.MockPreview

internal fun ownerV4Category(category: String): String = when (category.lowercase()) {
    "whisky", "whiskey" -> "위스키"
    "brandy" -> "브랜디"
    "cocktail" -> "칵테일"
    "snack" -> "안주"
    "otheralcohol" -> "기타 주류"
    "gin" -> "진"
    "rum" -> "럼"
    "wine" -> "와인"
    "beer" -> "맥주"
    "other" -> "기타"
    else -> category
}

/** The menu/category/brand grouping follows HTML menuGroups(true) without inventing items. */
@Composable
internal fun OwnerPreviewV4Menu(
    bar: MockBar,
    preview: MockPreview?,
    brandCatalog: List<MockBrand>,
    nowEpochMs: Long,
) {
    var query by rememberSaveable { mutableStateOf("") }
    var openCategories by rememberSaveable { mutableStateOf(listOf("위스키")) }
    val details = preview?.visibleMenu.orEmpty().map { item ->
        val product = preview?.products?.firstOrNull { it.productId == item.productId }
        item to product
    }
    val found = details.filter { (_, product) ->
        val brand = brandCatalog.firstOrNull { it.brandId == product?.brandId }?.name.orEmpty()
        query.isBlank() || (product?.displayName.orEmpty() + " " + brand)
            .contains(query.trim(), ignoreCase = true)
    }
    Column(verticalArrangement = Arrangement.spacedBy(11.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically) {
            Text("메뉴", color = V4Color.text, fontSize = 16.sp,
                fontWeight = FontWeight.Bold)
            Text("최근 갱신 " + ownerDisplayDate(bar.lastMenuPublishedAtEpochMs),
                color = V4Color.sub, fontSize = 11.sp)
        }
        V4SearchField(query, { query = it }, "owner-preview-menu-search", "메뉴 검색")
        if (found.isEmpty()) {
            Text(if (query.isBlank()) "등록된 메뉴가 없어요." else "검색 결과가 없어요.",
                color = V4Color.sub, fontSize = 12.sp)
        }
        val groups = found.groupBy { (_, product) ->
            ownerV4Category(product?.category ?: "기타")
        }
        groups.forEach { (category, entries) ->
            val open = query.isNotBlank() || category in openCategories
            Column(Modifier.fillMaxWidth().border(1.dp, V4Color.line,
                RoundedCornerShape(10.dp)).background(Color(0xFF292522),
                RoundedCornerShape(10.dp))) {
                Row(Modifier.fillMaxWidth().background(V4Color.elevated,
                    RoundedCornerShape(10.dp)).clickable {
                    openCategories = if (open) openCategories - category
                        else openCategories + category
                }.padding(horizontal = 12.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Text(category, color = V4Color.text,
                        fontWeight = FontWeight.Bold, fontSize = 14.sp,
                        modifier = Modifier.weight(1f))
                    Text(if (open) "⌃" else "⌄", color = V4Color.text, fontSize = 17.sp)
                }
                if (open) {
                    val byBrand = entries.groupBy { (_, product) ->
                        brandCatalog.firstOrNull { it.brandId == product?.brandId }?.name
                            ?: "기타 브랜드"
                    }
                    byBrand.forEach { (brandName, products) ->
                        if (category == "위스키" || category == "브랜디") {
                            Text(brandName, modifier = Modifier.padding(
                                start = 11.dp, top = 12.dp, bottom = 3.dp),
                                fontSize = 14.sp, fontWeight = FontWeight.Bold,
                                color = V4Color.primary)
                        }
                        products.forEach { (item, product) ->
                            OwnerPreviewV4MenuRow(item, product, nowEpochMs, brandName)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun OwnerPreviewV4MenuRow(
    item: MockBarMenuItem, product: MockCatalogProduct?, nowEpochMs: Long,
    brandName: String
) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 7.dp, vertical = 4.dp)
        .background(V4Color.surface, RoundedCornerShape(9.dp))
        .border(1.dp, V4Color.line, RoundedCornerShape(9.dp))
        .padding(6.dp), verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(7.dp)) {
        Box(Modifier.size(43.dp).background(V4Color.elevated,
            RoundedCornerShape(5.dp)), contentAlignment = Alignment.Center) {
            Canvas(Modifier.size(width = 30.dp, height = 38.dp)) {
                val unit = size.width / 30f
                drawRoundRect(Color(0xFF967F58),
                    topLeft = Offset(11f * unit, 1f * unit),
                    size = Size(8f * unit, 7f * unit),
                    cornerRadius = CornerRadius(2f * unit))
                drawRoundRect(Color(0xFF658C7A),
                    topLeft = Offset(5f * unit, 7f * unit),
                    size = Size(20f * unit, 30f * unit),
                    cornerRadius = CornerRadius(4f * unit))
                drawRect(Color(0xFFE1D2B5),
                    topLeft = Offset(7f * unit, 18f * unit),
                    size = Size(16f * unit, 13f * unit))
                drawRect(Color(0xFFC99D6B),
                    topLeft = Offset(11f * unit, 20f * unit),
                    size = Size(8f * unit, 2f * unit))
            }
        }
        Text(product?.let {
                if (ownerV4Category(it.category) == "위스키") {
                    val rest = it.displayName.removePrefix(brandName).trim()
                    if (rest.isNotBlank() && it.displayName.startsWith(brandName)) rest
                    else it.displayName
                } else it.displayName
            } ?: "상품 정보 없음",
            modifier = Modifier.weight(1f), color = V4Color.text,
            fontWeight = FontWeight.Bold, fontSize = 12.sp)
        Column(verticalArrangement = Arrangement.spacedBy(4.dp),
            horizontalAlignment = Alignment.End) {
            item.options.forEach { option ->
                Row(horizontalArrangement = Arrangement.spacedBy(5.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    val discounted = option.discount?.let {
                        nowEpochMs >= it.startAtEpochMs && nowEpochMs < it.endAtEpochMs
                    } == true
                    if (discounted) Text("할인", color = V4Color.primary, fontSize = 9.sp,
                        modifier = Modifier.border(1.dp, V4Color.primary,
                            RoundedCornerShape(4.dp)).padding(horizontal = 3.dp))
                    Text(option.pourMl?.toString()?.plus("ml") ?: option.label.orEmpty(),
                        color = V4Color.text, fontSize = 10.sp)
                    Text("%,d원".format(option.displayPrice(nowEpochMs)),
                        color = V4Color.sub, fontSize = 10.sp)
                }
            }
            if (item.options.isEmpty()) {
                Text("가격 없음", color = V4Color.sub, fontSize = 10.sp)
            }
        }
    }
}
