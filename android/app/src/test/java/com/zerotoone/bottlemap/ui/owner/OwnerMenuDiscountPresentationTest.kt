package com.zerotoone.bottlemap.ui.owner

import com.zerotoone.bottlemap.data.owner.MockDiscount
import com.zerotoone.bottlemap.data.owner.MockMenuOption
import org.junit.Assert.*
import org.junit.Test

class OwnerMenuDiscountPresentationTest {
    @Test fun discountBelongsToItsOptionAndRespectsHalfOpenPeriod() {
        val discount = MockMenuOption("pour30", pourMl = 30, priceKrw = 10000,
            discount = MockDiscount(5000, 100L, 200L))
        val regular = MockMenuOption("bottle", label = "Bottle", priceKrw = 120000)
        // The same active time interval gates BOTH badge and effective price.
        assertFalse(ownerOptionDiscountActive(discount, 99L))
        assertTrue(ownerOptionDiscountActive(discount, 100L))
        assertTrue(ownerOptionDiscountActive(discount, 199L))
        assertFalse(ownerOptionDiscountActive(discount, 200L))
        assertFalse(ownerOptionDiscountActive(regular, 150L))
        assertEquals(10000, discount.displayPrice(99L))
        assertEquals(5000, discount.displayPrice(150L))
        assertEquals(10000, discount.displayPrice(200L))
        assertEquals(120000, regular.displayPrice(150L))
    }
}
