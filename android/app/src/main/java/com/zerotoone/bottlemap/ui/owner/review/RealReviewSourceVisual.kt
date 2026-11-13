package com.zerotoone.bottlemap.ui.owner.review

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.zerotoone.bottlemap.data.owner.sampledBitmapSize
import com.zerotoone.bottlemap.ui.common.UxColor
import com.zerotoone.bottlemap.ui.common.uxText
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL

/**
 * Actual server-signed photo in the same visual bounds as the v20 SourceVisual.
 * Never attach the Owner bearer token to a signed CDN URL. Decode a sampled
 * 1600px bitmap, with a strict 10MiB download cap.
 */
@Composable
internal fun RealReviewSourceVisual(
    sourceUrl: String,
    box: List<Int>?,
    height: Dp,
    large: Boolean,
    modifier: Modifier = Modifier,
) {
    val image by produceState<Bitmap?>(
        initialValue = null, key1 = sourceUrl, key2 = box, key3 = large,
    ) {
        value = withContext(Dispatchers.IO) {
            runCatching { retrieveSignedReviewBitmap(sourceUrl, if (large) null else box) }
                .getOrNull()
        }
    }
    val shape = RoundedCornerShape(8.dp)
    Box(
        modifier.fillMaxWidth().height(height)
            .clip(shape)
            .background(UxColor.surface)
            .border(1.dp, ReviewColor.sourceBorder, shape),
        contentAlignment = Alignment.Center,
    ) {
        if (image != null) {
            Image(
                bitmap = requireNotNull(image).asImageBitmap(),
                contentDescription = "원본 메뉴판 사진",
                modifier = Modifier.fillMaxSize(),
                contentScale = if (large) ContentScale.Fit else ContentScale.Crop,
            )
        } else {
            Text("원본 사진을 불러오고 있어요.",
                style = uxText(11f, 400, UxColor.sub))
        }
    }
}

/** HTTP(S) URLs only; server returns short-lived signed links (API §5.4). */
private fun retrieveSignedReviewBitmap(
    sourceUrl: String, normalizedBox: List<Int>?,
): Bitmap? {
    if (!sourceUrl.startsWith("https://") && !sourceUrl.startsWith("http://")) return null
    val connection = URL(sourceUrl).openConnection() as HttpURLConnection
    connection.connectTimeout = 10_000
    connection.readTimeout = 20_000
    connection.instanceFollowRedirects = false
    try {
        if (connection.responseCode != 200) return null
        val sizeCap = 10 * 1024 * 1024
        val data = connection.inputStream.use { input ->
            val output = java.io.ByteArrayOutputStream()
            val buffer = ByteArray(16_384)
            var total = 0
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                total += count
                if (total > sizeCap) return null
                output.write(buffer, 0, count)
            }
            output.toByteArray()
        }
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(data, 0, data.size, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
        val decoded = BitmapFactory.decodeByteArray(data, 0, data.size,
            BitmapFactory.Options().apply {
                inSampleSize = sampledBitmapSize(bounds.outWidth, bounds.outHeight, 1600)
            }) ?: return null
        if (normalizedBox == null || normalizedBox.size != 4) return decoded
        val left = (normalizedBox[0].coerceIn(0, 1000) * decoded.width / 1000)
            .coerceIn(0, decoded.width - 1)
        val top = (normalizedBox[1].coerceIn(0, 1000) * decoded.height / 1000)
            .coerceIn(0, decoded.height - 1)
        val right = (normalizedBox[2].coerceIn(0, 1000) * decoded.width / 1000)
            .coerceIn(left + 1, decoded.width)
        val bottom = (normalizedBox[3].coerceIn(0, 1000) * decoded.height / 1000)
            .coerceIn(top + 1, decoded.height)
        return Bitmap.createBitmap(decoded, left, top, right - left, bottom - top)
    } finally {
        connection.disconnect()
    }
}
