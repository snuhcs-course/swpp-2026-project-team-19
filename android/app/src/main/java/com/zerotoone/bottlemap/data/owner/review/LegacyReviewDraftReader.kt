package com.zerotoone.bottlemap.data.owner.review

import android.content.Context
import android.util.AtomicFile
import android.util.Base64
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.zerotoone.bottlemap.data.AppAuth
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import java.io.File
import java.security.MessageDigest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Upgrade-only reader for drafts written before PR #171.
 * This code NEVER writes a device-local draft. It reads only the old JWT-sub
 * and import-scoped no-backup file, and deletes it AFTER a server save succeeds
 * (or when an existing server draft takes precedence).
 */
internal class LegacyReviewDraftReader(
    context: Context,
    private val token: suspend () -> String? = {
        AppAuth.gateway.currentAccessTokenOrNull()
    },
) {
    private val directory = File(context.applicationContext.noBackupFilesDir, "owner-review-drafts")
    private val adapter = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
        .adapter(Envelope::class.java)

    internal data class Envelope(
        val reviewVersion: Int,
        val itemIds: List<String>,
        val state: PhotoReviewState,
    )

    private suspend fun fileFor(importId: String): File? {
        val jwt = token() ?: return null
        val subject = runCatching {
            val middle = jwt.split('.').getOrNull(1) ?: return@runCatching null
            val decoded = Base64.decode(middle,
                Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
            org.json.JSONObject(String(decoded, Charsets.UTF_8)).optString("sub")
                .takeIf { it.isNotBlank() }
        }.getOrNull() ?: return null
        val key = MessageDigest.getInstance("SHA-256")
            .digest("$subject:$importId".toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
        return File(directory, "$key.json")
    }

    suspend fun read(importId: String, version: Int, itemIds: List<String>): PhotoReviewState? {
        val file = fileFor(importId) ?: return null
        return withContext(Dispatchers.IO) {
            if (!file.isFile || file.length() > 2_000_000L) return@withContext null
            val envelope = runCatching {
                AtomicFile(file).openRead().bufferedReader().use {
                    adapter.fromJson(it.readText())
                }
            }.getOrNull()
            envelope?.takeIf {
                it.reviewVersion == version && it.itemIds == itemIds
            }?.state
        }
    }

    suspend fun hasLegacyFile(importId: String): Boolean {
        val file = fileFor(importId) ?: return false
        return withContext(Dispatchers.IO) { file.isFile }
    }

    suspend fun clear(importId: String) {
        val file = fileFor(importId) ?: return
        withContext(Dispatchers.IO) { AtomicFile(file).delete() }
    }
}
