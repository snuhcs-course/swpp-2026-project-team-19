package com.zerotoone.bottlemap.data.owner.review

import android.content.Context
import android.util.AtomicFile
import android.util.Base64
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import com.zerotoone.bottlemap.data.AppAuth
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import com.zerotoone.bottlemap.ui.owner.review.ReviewOption
import java.io.File
import java.security.MessageDigest
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

/**
 * Recover a review after process death without changing the backend reviewVersion.
 * Private, no-backup storage is scoped by auth subject and import ID: never reuse
 * one owner's draft for another account, another bar, or another import.
 *
 * OCR source URLs are short-lived signed links: do not persist them. Read the
 * latest GET /api/menu-imports/{id} on restore and graft fresh source URLs back.
 * A reviewVersion mismatch automatically discards the obsolete local draft.
 */
private fun sanitizeReviewOption(option: ReviewOption): ReviewOption =
    option.copy(price = option.price.takeIf { it.isFinite() } ?: 0.0,
        volume = option.volume.takeIf { it.isFinite() } ?: 0.0)

internal class OwnerPhotoReviewDraftStore(
    context: Context,
    private val accessToken: suspend () -> String? = {
        AppAuth.gateway.currentAccessTokenOrNull()
    },
) {
    private val folder = File(context.applicationContext.noBackupFilesDir, "owner-review-drafts")
    private val json = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
        .adapter(DraftEnvelope::class.java)
    private val lock = Mutex()

    internal data class DraftEnvelope(
        val reviewVersion: Int,
        val itemIds: List<String>,
        val state: PhotoReviewState,
    )

    /** SDK access token remains in Supabase; only its stable JWT subject is hashed. */
    private suspend fun scopedFile(importId: String): File? {
        val jwt = accessToken() ?: return null
        val sub = runCatching {
            val chunk = jwt.split('.').getOrNull(1) ?: return@runCatching null
            val decoded = Base64.decode(chunk, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
            org.json.JSONObject(String(decoded, Charsets.UTF_8)).optString("sub")
                .takeIf { it.isNotBlank() }
        }.getOrNull() ?: return null
        val hash = MessageDigest.getInstance("SHA-256")
            .digest("$sub:$importId".toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
        return File(folder, "$hash.json")
    }

    suspend fun load(importId: String, reviewVersion: Int, itemIds: List<String>): PhotoReviewState? {
        val file = scopedFile(importId) ?: return null
        return lock.withLock {
            withContext(Dispatchers.IO) {
                try {
                    if (!file.isFile || file.length() > 2_000_000L) return@withContext null
                    val data = AtomicFile(file).openRead().bufferedReader().use { it.readText() }
                    val saved = json.fromJson(data)
                    if (saved?.reviewVersion == reviewVersion && saved.itemIds == itemIds) {
                        saved.state
                    } else {
                        file.delete()
                        null
                    }
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (_: Exception) {
                    file.delete()
                    null
                }
            }
        }
    }

    suspend fun save(importId: String, version: Int, state: PhotoReviewState) {
        val file = scopedFile(importId) ?: return
        // Never persist a transient modal or expiring signed image URL. Keep
        // actual owner edits, category decisions, and in-progress field text.
        val persisted = state.copy(
            modal = null, typingSnapshots = emptyMap(),
            items = state.items.map { item ->
                item.copy(
                    sourcePhotoUrl = null,
                    mergeSources = item.mergeSources.map { it.copy(sourcePhotoUrl = null) },
                    price = item.price.takeIf { it.isFinite() } ?: 0.0,
                    volume = item.volume.takeIf { it.isFinite() } ?: 0.0,
                    options = item.options.map(::sanitizeReviewOption),
                    preMergeOptions = item.preMergeOptions.map(::sanitizeReviewOption),
                    volumeChoices = item.volumeChoices.map(::sanitizeReviewOption),
                    classificationSnapshot = item.classificationSnapshot?.let { snapshot ->
                        snapshot.copy(
                            volume = snapshot.volume.takeIf { it.isFinite() } ?: 0.0,
                            primaryPrice = snapshot.primaryPrice?.takeIf { it.isFinite() },
                            options = snapshot.options.map(::sanitizeReviewOption),
                        )
                    },
                )
            },
        )
        val bytes = json.toJson(DraftEnvelope(version, state.items.map { it.id }, persisted))
            .toByteArray(Charsets.UTF_8)
        require(bytes.size <= 2_000_000) { "임시 검수 기록이 너무 커요." }
        lock.withLock {
            withContext(Dispatchers.IO) {
                folder.mkdirs()
                val atomic = AtomicFile(file)
                val output = atomic.startWrite()
                try {
                    output.write(bytes)
                    output.fd.sync()
                    atomic.finishWrite(output)
                } catch (cancelled: CancellationException) {
                    atomic.failWrite(output)
                    throw cancelled
                } catch (error: Exception) {
                    atomic.failWrite(output)
                    throw error
                }
            }
        }
    }

    suspend fun clear(importId: String) {
        val file = scopedFile(importId) ?: return
        lock.withLock {
            withContext(Dispatchers.IO) {
                AtomicFile(file).delete()
            }
        }
    }
}
