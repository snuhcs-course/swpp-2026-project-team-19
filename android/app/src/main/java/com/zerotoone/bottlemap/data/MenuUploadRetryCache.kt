// I2-A14: preserve multipart bytes and Idempotency-Key after an ambiguous HTTP error.
package com.zerotoone.bottlemap.data

import java.util.UUID

internal class MenuUploadRetryCache {
    private var prepared: List<PreparedMenuImage>? = null
    private var requestKey: String? = null

    suspend fun prepareIfNeeded(
        photos: List<SelectedMenuImage>,
        prepare: suspend (SelectedMenuImage) -> PreparedMenuImage,
        onPrepared: (Int) -> Unit = {},
    ): List<PreparedMenuImage> {
        prepared?.let { return it }
        val images = prepareMenuBatch(photos, prepare, onPrepared)
        prepared = images
        return images
    }

    fun key(generator: () -> String = { UUID.randomUUID().toString() }): String =
        requestKey ?: generator().also { requestKey = it }

    /** A 409 key conflict explicitly requires a different key. */
    fun discardKey() {
        requestKey = null
    }

    /** Selection / mode / bar changed, or user explicitly starts a new server import. */
    fun clear() {
        requestKey = null
        prepared = null
    }
}
