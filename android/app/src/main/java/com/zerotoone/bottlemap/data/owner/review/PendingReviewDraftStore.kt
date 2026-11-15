package com.zerotoone.bottlemap.data.owner.review

import android.content.Context
import android.util.AtomicFile
import android.util.Base64
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.zerotoone.bottlemap.data.AppAuth
import com.zerotoone.bottlemap.network.ReviewDraftDto
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * A failure-only safety copy for §5.9 server Draft saves.
 *
 * Written BEFORE every attempted network save and removed after the server
 * acknowledges the matching content. Files are private, not cloud-backed,
 * keyed by JWT subject + import ID (never by the currently selected bar).
 * A pending copy can only be replayed when the remote CAS draftVersion and
 * reviewVersion still match. A remote edit must never be overwritten.
 */
internal class PendingReviewDraftStore(
    context: Context,
    private val token: suspend () -> String? = { AppAuth.gateway.currentAccessTokenOrNull() },
) {
    internal data class Envelope(
        val reviewVersion: Int,
        val expectedDraftVersion: Int,
        val itemIds: List<String>,
        val content: Map<String, Any?>,
    ) {
        fun canReplay(remote: ReviewDraftDto?, activeReviewVersion: Int): Boolean =
            reviewVersion == activeReviewVersion &&
                (remote == null || remote.reviewVersion == activeReviewVersion) &&
                expectedDraftVersion == (remote?.draftVersion ?: 0)
    }

    private val directory = File(context.applicationContext.noBackupFilesDir,
        "pending-owner-review-drafts")
    private val adapter = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
        .adapter(Envelope::class.java)

    private suspend fun fileFor(importId: String): File? {
        val jwt = token() ?: return null
        val subject = runCatching {
            val payload = jwt.split('.').getOrNull(1) ?: return@runCatching null
            val decoded = Base64.decode(payload,
                Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
            org.json.JSONObject(String(decoded, Charsets.UTF_8)).optString("sub")
                .takeIf { it.isNotBlank() }
        }.getOrNull() ?: return null
        val hash = MessageDigest.getInstance("SHA-256")
            .digest("pending:$subject:$importId".toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
        return File(directory, "$hash.json")
    }

    suspend fun write(importId: String, envelope: Envelope) {
        val file = fileFor(importId)
            ?: error("계정 확인이 안 되어 이 기기에 검수 초안을 저장할 수 없어요.")
        val json = adapter.toJson(envelope).toByteArray(Charsets.UTF_8)
        check(json.size <= 350_000) { "기기 검수 초안이 너무 커서 저장할 수 없어요." }
        withContext(Dispatchers.IO) {
            check(directory.isDirectory || directory.mkdirs()) {
                "검수 초안 저장 공간을 만들 수 없어요."
            }
            val atomic = AtomicFile(file)
            var stream: FileOutputStream? = null
            try {
                stream = atomic.startWrite()
                stream.write(json)
                atomic.finishWrite(stream)
            } catch (error: Exception) {
                stream?.let(atomic::failWrite)
                throw error
            }
        }
    }

    suspend fun read(importId: String): Envelope? {
        val file = fileFor(importId) ?: return null
        return withContext(Dispatchers.IO) {
            if (!file.exists() || file.length() > 350_000L) return@withContext null
            runCatching {
                AtomicFile(file).openRead().bufferedReader().use {
                    adapter.fromJson(it.readText())
                }
            }.getOrNull()
        }
    }

    suspend fun clear(importId: String) {
        val file = fileFor(importId) ?: return
        withContext(Dispatchers.IO) { AtomicFile(file).delete() }
    }
}
