package com.zerotoone.bottlemap.data.owner

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class OwnerMenuIdentityContractTest {
    private val canonicalId = "11111111-1111-4111-8111-111111111111"

    @Test fun canonicalProductOnlyInFreshLookupStillUsesProductId() {
        val staged = MockCatalogProduct(canonicalId, "brand", "라가불린 16년",
            category = "whisky", catalogMatched = true)
        assertEquals(mapOf("productId" to canonicalId),
            ownerAddMenuIdentity(canonicalId, staged, null))
    }

    @Test fun canonicalProductFromPublishedSnapshotUsesProductId() {
        val saved = MockCatalogProduct(canonicalId, "brand", "위스키", catalogMatched = true)
        assertEquals(mapOf("productId" to canonicalId),
            ownerAddMenuIdentity(canonicalId, null, saved))
    }

    @Test fun unmatchedWhiskyOnlySendsKind() {
        val item = MockCatalogProduct("local-unverified-test", "", "위스키 1",
            category = "whisky", catalogMatched = false)
        assertEquals(mapOf("kind" to "whisky"),
            ownerAddMenuIdentity(item.productId, item, null))
    }

    @Test fun nonWhiskyOnlySendsOtherWithoutCatalogId() {
        val beer = MockCatalogProduct("local-unverified-beer", "", "맥주 1",
            category = "맥주", catalogMatched = false)
        assertEquals(mapOf("kind" to "other"),
            ownerAddMenuIdentity(beer.productId, beer, null))
        val published = beer.copy(productId = "unlinked:bar-item-id")
        assertEquals(mapOf("kind" to "other"),
            ownerAddMenuIdentity(published.productId, null, published))
    }

    @Test fun missingOrSyntheticCatalogIdentityFailsBeforeSending() {
        assertThrows(IllegalStateException::class.java) {
            ownerAddMenuIdentity(canonicalId, null, null)
        }
        assertThrows(IllegalArgumentException::class.java) {
            ownerAddMenuIdentity("unlinked:row", MockCatalogProduct(
                "unlinked:row", "", "위스키", catalogMatched = true), null)
        }
        assertThrows(IllegalArgumentException::class.java) {
            ownerAddMenuIdentity("wrong", MockCatalogProduct(
                canonicalId, "", "위스키", catalogMatched = true), null)
        }
    }
}
