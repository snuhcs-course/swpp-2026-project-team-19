package com.zerotoone.bottlemap.data.owner

import com.zerotoone.bottlemap.network.BarMenuResponseDto
import java.time.Instant

private fun ackTimestamp(value: String?): Long? = value?.let {
    runCatching { Instant.parse(it).toEpochMilli() }.getOrNull()
}
private fun ackUnlinkedUiId(id: String) = "unlinked:$id"

/** Publish server acknowledgements before a best-effort aggregate GET. Never stage a request as success. */
internal fun ownerSnapshotAfterBarCommit(current: MockOwnerSnapshot, bar: MockBar): MockOwnerSnapshot =
    current.copy(bars = if (current.bars.any { it.barId == bar.barId })
        current.bars.map { if (it.barId == bar.barId) bar else it } else current.bars + bar)

internal fun ownerMenuRows(barId: String, menu: BarMenuResponseDto): List<MockBarMenuItem> =
        menu.items.map { entry ->
            MockBarMenuItem(
                barMenuItemId = entry.barMenuItemId, barId = barId,
                productId = entry.productId ?: ackUnlinkedUiId(entry.barMenuItemId), soldOut = entry.soldOut,
                displayNameOverride = entry.displayName,
                options = entry.options.map { option ->
                    MockMenuOption(
                        optionId = option.menuEntryOptionId,
                        label = option.optionLabel, pourMl = option.pourMl,
                        priceKrw = option.priceKrw,
                        discount = option.discount?.let { discount ->
                            val start = ackTimestamp(discount.startsAt)
                            val end = ackTimestamp(discount.endsAt)
                            if(start != null && end != null)
                                MockDiscount(discount.discountedPriceKrw, start, end)
                            else null
                        },
                    )
                },
            )
        }

internal fun ownerSnapshotAfterMenuCommit(
    current: MockOwnerSnapshot, barId: String, menu: BarMenuResponseDto,
): MockOwnerSnapshot {
    require(menu.barId == barId)
    val brands = menu.items.mapNotNull { item ->
        item.brandId?.let { MockBrand(it, item.brandName ?: item.displayName) }
    }
    val products = menu.items.map { item ->
        MockCatalogProduct(
            productId = item.productId ?: ackUnlinkedUiId(item.barMenuItemId),
            brandId = item.brandId ?: "", displayName = item.productName ?: item.displayName,
            category = item.category ?: if (item.kind == "whisky") "whisky" else "otherAlcohol",
            catalogMatched = item.productId != null,
        )
    }
    return current.copy(
        menuItems = current.menuItems.filterNot { it.barId == barId } + ownerMenuRows(barId, menu),
        products = (products + current.products).distinctBy { it.productId },
        brands = (brands + current.brands).distinctBy { it.brandId },
        bars = current.bars.map { if (it.barId == barId)
            it.copy(lastMenuPublishedAtEpochMs = ackTimestamp(menu.publishedAt)) else it },
    )
}
