package com.zerotoone.bottlemap.ui.owner

import android.net.Uri
import androidx.core.content.FileProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class OwnerRegistrationCaptureCleanupTest {
    @Test fun removedFirstRegistrationCaptureIsDeletedViaFileProvider() {
        val context=InstrumentationRegistry.getInstrumentation().targetContext
        val dir=File(context.filesDir,"owner-menu-captures").apply { mkdirs() }
        val capture=File.createTempFile("registration-menu-", ".jpg",dir)
        val unrelated=File.createTempFile("menu-capture-", ".jpg",dir)
        try {
            capture.writeBytes(byteArrayOf(0xFF.toByte(),0xD8.toByte(),0xFF.toByte()))
            unrelated.writeBytes(byteArrayOf(1,2,3))
            val authority="${context.packageName}.owner.camera.provider"
            val captureUri=FileProvider.getUriForFile(context,authority,capture)
            val unrelatedUri=FileProvider.getUriForFile(context,authority,unrelated)
            assertFalse(deleteOwnedRegistrationMenuCapture(context,unrelatedUri))
            assertTrue(unrelated.exists())
            assertFalse(deleteOwnedRegistrationMenuCapture(context,Uri.fromFile(capture)))
            assertTrue(capture.exists())
            assertTrue(deleteOwnedRegistrationMenuCapture(context,captureUri))
            assertFalse(capture.exists())
            assertFalse(deleteOwnedRegistrationMenuCapture(context,captureUri))
        } finally {
            capture.delete()
            unrelated.delete()
        }
    }
}
