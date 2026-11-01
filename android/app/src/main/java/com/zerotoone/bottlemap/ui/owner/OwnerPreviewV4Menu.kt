package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.draw.clip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zerotoone.bottlemap.data.owner.MockBar
import com.zerotoone.bottlemap.data.owner.MockBrand
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

/** Customer and Owner use identical menu rows; customer never displays sold-out products. */
@Composable
internal fun OwnerPreviewV4Menu(
    bar: MockBar, preview: MockPreview?, brandCatalog: List<MockBrand>, nowEpochMs: Long,
) {
    var query by rememberSaveable { mutableStateOf("") }
    var openCategories by rememberSaveable { mutableStateOf(listOf("위스키")) }
    val details = preview?.visibleMenu.orEmpty().filterNot { it.soldOut }.map { item ->
        val product = preview?.products?.firstOrNull { it.productId == item.productId }
        item to product
    }
    val found = details.filter { (item, product) ->
        val brand = brandCatalog.firstOrNull { it.brandId == product?.brandId }?.name.orEmpty()
        query.isBlank() || listOfNotNull(item.displayNameOverride, product?.displayName, brand)
            .any { it.contains(query.trim(), ignoreCase = true) }
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
            Column(Modifier.fillMaxWidth()) {
                Row(Modifier.fillMaxWidth()
                    .clip(RoundedCornerShape(8.dp))
                    .background(V4Color.surface)
                    .ownerQuietClick {
                        openCategories = if (open) openCategories - category
                            else openCategories + category
                    }.padding(horizontal = 12.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Text(category, color = V4Color.text,
                        fontWeight = FontWeight.Bold, fontSize = 14.sp,
                        modifier = Modifier.weight(1f))
                    Text(if (open) "⌃" else "⌄", color = V4Color.sub, fontSize = 15.sp)
                }
                if (open) {
                    val byBrand = if (category == "위스키" || category == "브랜디") {
                        entries.groupBy { (_, product) ->
                            brandCatalog.firstOrNull { it.brandId == product?.brandId }?.name
                                ?: "기타 브랜드"
                        }
                    } else mapOf("" to entries)
                    byBrand.entries.forEachIndexed { groupIndex, group ->
                        if (category == "위스키" || category == "브랜디") {
                            Text(group.key, modifier = Modifier.padding(
                                start = 4.dp, top = 18.dp, bottom = 8.dp),
                                fontSize = 13.sp, fontWeight = FontWeight.Bold,
                                color = V4Color.primary)
                        } else Spacer(Modifier.height(8.dp))
                        group.value.forEachIndexed { index, (item, product) ->
                            OwnerMenuFlatRow(
                                item = item, product = product, brandName = group.key,
                                nowEpochMs = nowEpochMs, showStatus = false
                            )
                            if (index < group.value.lastIndex)
                                HorizontalDivider(color = V4Color.line, thickness = 1.dp)
                        }
                        if (groupIndex < byBrand.size - 1) {
                            Spacer(Modifier.height(8.dp))
                            HorizontalDivider(color = V4Color.line, thickness = 2.dp)
                        }
                    }
                }
            }
            Spacer(Modifier.height(8.dp))
        }
    }
}
