package com.zerotoone.bottlemap.ui.owner.review

import android.graphics.Bitmap
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotSame
import org.junit.Assert.assertSame
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class ReviewSourceBitmapCacheTest {
    @After fun clear() = ReviewSourceBitmapCache.clearForAccountChange()

    @Test fun groupedCropsLoadOneDecodedPhotoAndPurgeItOnSignout() = runBlocking {
        var downloads = 0
        val url = "https://signed.example/bar/photo"
        val first = ReviewSourceBitmapCache.getOrLoad(url) {
            downloads++
            Bitmap.createBitmap(100, 100, Bitmap.Config.ARGB_8888)
        }
        val second = ReviewSourceBitmapCache.getOrLoad(url) {
            downloads++
            Bitmap.createBitmap(100, 100, Bitmap.Config.ARGB_8888)
        }
        assertEquals(1, downloads)
        assertSame(first, second)

        ReviewSourceBitmapCache.clearForAccountChange()
        val third = ReviewSourceBitmapCache.getOrLoad(url) {
            downloads++
            Bitmap.createBitmap(100, 100, Bitmap.Config.ARGB_8888)
        }
        assertNotSame(first, third)
        assertEquals(2, downloads)
    }
}
