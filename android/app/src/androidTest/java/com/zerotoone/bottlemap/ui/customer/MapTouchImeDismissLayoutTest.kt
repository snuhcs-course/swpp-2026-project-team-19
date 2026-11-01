package com.zerotoone.bottlemap.ui.customer

import android.content.Context
import android.view.MotionEvent
import android.view.View
import android.widget.FrameLayout
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MapTouchImeDismissLayoutTest {
    @Test fun nativeMapDownDismissesOnceAndPreservesChildGestureDelivery() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        var dismissed = 0
        var childTouches = 0
        val layout = MapTouchImeDismissLayout(context) { dismissed++ }
        layout.addView(object : View(context) {
            override fun onTouchEvent(event: MotionEvent): Boolean {
                childTouches++
                return true
            }
        }, FrameLayout.LayoutParams(200, 200))
        layout.layout(0, 0, 200, 200)
        val down = MotionEvent.obtain(10L, 20L, MotionEvent.ACTION_DOWN, 50f, 50f, 0)
        val move = MotionEvent.obtain(10L, 35L, MotionEvent.ACTION_MOVE, 60f, 55f, 0)
        val up = MotionEvent.obtain(10L, 45L, MotionEvent.ACTION_UP, 60f, 55f, 0)
        try {
            assertTrue(layout.dispatchTouchEvent(down))
            assertTrue(layout.dispatchTouchEvent(move))
            assertTrue(layout.dispatchTouchEvent(up))
        } finally {
            down.recycle(); move.recycle(); up.recycle()
        }
        assertEquals(1, dismissed)
        assertEquals(3, childTouches)
    }
}
