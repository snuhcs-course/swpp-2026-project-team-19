// AI-generated with ChatGPT (Hojin Nam, 2026-10-06, PR #15). Reviewed by Hojin Nam.
package com.zerotoone.bottlemap.ui.owner

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.viewModelScope
import com.zerotoone.bottlemap.data.ImageUploadPreparer
import com.zerotoone.bottlemap.data.PreparedMenuImage
import com.zerotoone.bottlemap.data.MenuPhotoPreparationException
import com.zerotoone.bottlemap.data.MAX_MENU_PHOTOS
import com.zerotoone.bottlemap.data.appendMenuPhotos
import com.zerotoone.bottlemap.data.removeMenuPhoto
import com.zerotoone.bottlemap.data.prepareMenuBatch
import com.zerotoone.bottlemap.data.OwnerRepositories
import com.zerotoone.bottlemap.network.BarDto
import com.zerotoone.bottlemap.network.BottleMapApiException
import java.util.UUID
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class MenuUploadViewModel(
    application: Application,
    private val savedStateHandle: SavedStateHandle,
) : AndroidViewModel(application) {
    private val repository = OwnerRepositories.owner
    private val imagePreparer = ImageUploadPreparer(application.contentResolver)

    private val _state = MutableStateFlow(MenuUploadUiState())
    val state: StateFlow<MenuUploadUiState> = _state.asStateFlow()

    private var pendingIdempotencyKey: String? = null
    // Same key and exact photo bytes reused on a failed HTTP transport retry.
    private var cachedPreparedImages: List<PreparedMenuImage>? = null
    private var selectionGeneration = 0L
    private val savedPhotoKey = "ownerMenuPhotoUris"

    init {
        loadBars()
        restoreSelectedImages()
    }

    private fun rememberPhotos() {
        savedStateHandle[savedPhotoKey] = ArrayList(_state.value.selectedImages.map { it.uri })
    }

    private fun invalidateDraft() {
        pendingIdempotencyKey = null
        cachedPreparedImages = null
        _state.value = _state.value.copy(
            extractionProgress = null,
            imagePreparation = emptyMap(),
            failedImportRequiresNewAttempt = false,
        )
    }

    private fun restoreSelectedImages() {
        val uris = savedStateHandle.get<ArrayList<String>>(savedPhotoKey).orEmpty()
        if (uris.isEmpty()) return
        addImages(uris.map(Uri::parse))
    }

    fun loadBars() {
        _state.value = _state.value.copy(
            loadingBars = true,
            errorMessage = null,
        )
        viewModelScope.launch {
            runCatching { repository.getBars() }
                .onSuccess { bars ->
                    val mapped = bars.map { it.toUiModel() }
                    val selected = _state.value.selectedBarId
                        ?.takeIf { id -> mapped.any { it.barId == id } }
                        ?: mapped.firstOrNull()?.barId
                    _state.value = _state.value.copy(
                        loadingBars = false,
                        bars = mapped,
                        selectedBarId = selected,
                    )
                }
                .onFailure { error ->
                    _state.value = _state.value.copy(
                        loadingBars = false,
                        errorMessage = error.message ?: "Failed to load operator bars.",
                    )
                }
        }
    }

    fun selectBar(barId: String) {
        if (_state.value.working || _state.value.selectionBusy) return
        if (_state.value.selectedBarId == barId) return
        _state.value = _state.value.copy(selectedBarId = barId, selectedImages = emptyList(),
            statusMessage = null, errorMessage = null)
        rememberPhotos()
        invalidateDraft()
    }

    fun setMode(mode: ImportModeUi) {
        if (_state.value.working || _state.value.selectionBusy || _state.value.mode == mode) return
        _state.value = _state.value.copy(mode = mode, errorMessage = null)
        invalidateDraft()
    }

    fun addImages(uris: List<Uri>) {
        if (uris.isEmpty() || _state.value.working || _state.value.selectionBusy) return
        val existing = _state.value.selectedImages.mapTo(mutableSetOf()) { it.uri }
        val newUris = uris.distinctBy { it.toString() }.filterNot { it.toString() in existing }
        val duplicates = uris.size - newUris.size
        val remaining = (MAX_MENU_PHOTOS - existing.size).coerceAtLeast(0)
        val accepted = newUris.take(remaining)
        val overLimit = newUris.size - accepted.size
        if (accepted.isEmpty()) {
            _state.value = _state.value.copy(errorMessage = when {
                overLimit > 0 -> "Maximum 5 photos. Remove one first."
                duplicates > 0 -> "These photos are already selected."
                else -> null
            })
            return
        }
        val generation = ++selectionGeneration
        _state.value = _state.value.copy(selectionBusy = true, errorMessage = null)
        viewModelScope.launch {
            val described = mutableListOf<com.zerotoone.bottlemap.data.SelectedMenuImage>()
            val errors = mutableListOf<String>()
            accepted.forEachIndexed { index, uri ->
                try {
                    described.add(imagePreparer.describe(uri))
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (error: Exception) {
                    errors.add("Photo #" + (index + 1) + ": " + (error.message ?: "unreadable"))
                }
            }
            if (generation != selectionGeneration) return@launch
            val result = appendMenuPhotos(_state.value.selectedImages, described)
            val messages = errors + listOfNotNull(
                duplicates.takeIf { it > 0 }?.let { it.toString() + " duplicate(s) ignored." },
                overLimit.takeIf { it > 0 }?.let { it.toString() + " photo(s) over the limit." },
            )
            _state.value = _state.value.copy(selectionBusy = false, selectedImages = result.images,
                errorMessage = messages.joinToString(" ").ifBlank { null })
            if (described.isNotEmpty()) {
                rememberPhotos()
                invalidateDraft()
            }
        }
    }

    fun removeImage(uri: String) {
        if (_state.value.working || _state.value.selectionBusy) return
        val remaining = removeMenuPhoto(_state.value.selectedImages, uri)
        if (remaining.size == _state.value.selectedImages.size) return
        _state.value = _state.value.copy(selectedImages = remaining, errorMessage = null)
        rememberPhotos()
        invalidateDraft()
    }

    fun startNewAttemptAfterFailure() {
        if (_state.value.working || !_state.value.failedImportRequiresNewAttempt) return
        invalidateDraft()
        _state.value = _state.value.copy(statusMessage = null,
            errorMessage = "New attempt ready. All selected photos will be resubmitted together.")
    }

    fun continueActiveImport() {
        val active = selectedBar()?.activeImportId ?: return
        startPolling(active, initialDelayMs = 0L)
    }

    fun upload() {
        val snapshot = _state.value
        val bar = selectedBar() ?: return
        if (snapshot.working || snapshot.selectionBusy || snapshot.selectedImages.isEmpty()) return
        if (snapshot.failedImportRequiresNewAttempt) {
            _state.value = snapshot.copy(
                errorMessage = "Server extraction failed. Choose New attempt before resubmitting the batch."
            )
            return
        }
        _state.value = snapshot.copy(
            working = true, statusMessage = "Preparing photos...", errorMessage = null,
            extractionProgress = null,
        )
        viewModelScope.launch {
            try {
                // Validate the complete immutable selection before any HTTP request.
                // Reuse exact compressed bytes after a network/timeout failure.
                val prepared = cachedPreparedImages ?: prepareMenuBatch(
                    snapshot.selectedImages,
                    prepare = { photo -> imagePreparer.prepare(Uri.parse(photo.uri)) },
                    onPrepared = { order ->
                        val photo = snapshot.selectedImages[order - 1]
                        _state.value = _state.value.copy(
                            imagePreparation = _state.value.imagePreparation + (photo.uri to "Ready"),
                            statusMessage = "Prepared " + order + "/" + snapshot.selectedImages.size,
                        )
                    },
                ).also { cachedPreparedImages = it }
                val key = pendingIdempotencyKey ?: UUID.randomUUID().toString().also {
                    pendingIdempotencyKey = it
                }
                _state.value = _state.value.copy(
                    statusMessage = "Uploading all " + prepared.size + " photos together...",
                )
                val accepted = repository.uploadMenuImport(
                    barId = bar.barId,
                    images = prepared,
                    mode = snapshot.mode.apiValue,
                    idempotencyKey = key,
                )
                require(accepted.imageCount == prepared.size) {
                    "Server accepted an unexpected number of images."
                }
                startPollingInCurrentJob(accepted.menuImportId, accepted.pollAfterMs)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: MenuPhotoPreparationException) {
                val photo = snapshot.selectedImages[error.imageOrder - 1]
                _state.value = _state.value.copy(
                    working = false, statusMessage = null,
                    imagePreparation = _state.value.imagePreparation +
                        (photo.uri to ("Failed: " + (error.cause?.message ?: "invalid image"))),
                    errorMessage = (error.message ?: "Unable to prepare an image.") +
                        " No photos were uploaded. Remove or replace this photo and retry.",
                )
            } catch (error: BottleMapApiException) {
                if (error.code == "ACTIVE_IMPORT_EXISTS") {
                    val existing = error.details?.get("menuImportId") as? String
                    if (existing != null) {
                        _state.value = _state.value.copy(
                            statusMessage = "Continuing existing import, not uploading again.",
                        )
                        startPollingInCurrentJob(existing, 0L)
                        return@launch
                    }
                }
                if (error.code == "IDEMPOTENCY_KEY_REUSED") pendingIdempotencyKey = null
                _state.value = _state.value.copy(
                    working = false, statusMessage = null,
                    errorMessage = when (error.code) {
                        "IDEMPOTENCY_KEY_REUSED" -> "Request key conflict; submit with a fresh key."
                        "NETWORK_ERROR" -> "Network interrupted. Retry uses the same images and key."
                        else -> error.message
                    },
                )
            } catch (error: Exception) {
                _state.value = _state.value.copy(
                    working = false, statusMessage = null,
                    errorMessage = error.message ?: "Upload failed. Try again with the same request.",
                )
            }
        }
    }

    fun consumeReviewNavigation() {
        _state.value = _state.value.copy(openReviewImportId = null)
    }

    private fun startPolling(menuImportId: String, initialDelayMs: Long) {
        if (_state.value.working) return
        _state.value = _state.value.copy(
            working = true,
            statusMessage = "Checking existing menu import…",
            failedImportRequiresNewAttempt = false,
            errorMessage = null,
        )
        viewModelScope.launch {
            startPollingInCurrentJob(menuImportId, initialDelayMs)
        }
    }

    private suspend fun startPollingInCurrentJob(
        menuImportId: String,
        initialDelayMs: Long,
    ) {
        var waitMs = initialDelayMs
        while (true) {
            if (waitMs > 0) {
                delay(waitMs)
            }
            try {
                val status = repository.getMenuImport(menuImportId)
                when (status.status) {
                    "uploaded", "processing" -> {
                        val progress = status.progress
                        val progressText = if (progress != null) {
                            "Extracting menu… " +
                                progress.completedImages + "/" +
                                progress.totalImages + " image(s)"
                        } else {
                            "Extracting menu…"
                        }
                        _state.value = _state.value.copy(
                            working = true,
                            statusMessage = progressText,
                            extractionProgress = progress,
                            errorMessage = null,
                        )
                        waitMs = (status.pollAfterMs ?: 3000L).coerceIn(1000L, 10000L)
                    }

                    "ready_for_review" -> {
                        pendingIdempotencyKey = null
                        _state.value = _state.value.copy(
                            working = false,
                            statusMessage = null,
                            errorMessage = null,
                            openReviewImportId = menuImportId,
                            extractionProgress = status.progress,
                        )
                        return
                    }

                    "failed" -> {
                        // No per-photo retry API: extraction stops on the first failure.
                        _state.value = _state.value.copy(
                            working = false,
                            statusMessage = null,
                            extractionProgress = status.progress,
                            failedImportRequiresNewAttempt = true,
                            errorMessage = (status.failure?.message ?: "Menu extraction failed.") +
                                " This entire import is terminal: " +
                                (status.progress?.completedImages ?: 0) + "/" +
                                (status.progress?.totalImages ?: 0) + " extracted, " +
                                (status.progress?.failedImages ?: 0) + " failed. " +
                                "Review the selected pages before starting a NEW batch.",
                        )
                        return
                    }

                    "applied" -> {
                        pendingIdempotencyKey = null
                        _state.value = _state.value.copy(
                            working = false,
                            statusMessage = null,
                            errorMessage = "This import was already published. Refresh the bar list to start another upload.",
                        )
                        loadBars()
                        return
                    }

                    else -> {
                        _state.value = _state.value.copy(
                            working = false,
                            statusMessage = null,
                            errorMessage = "Unknown import status: " + status.status,
                        )
                        return
                    }
                }
            } catch (error: BottleMapApiException) {
                if (error.code == "NETWORK_ERROR") {
                    _state.value = _state.value.copy(
                        working = true,
                        statusMessage = "Connection lost while checking extraction. Retrying…",
                    )
                    waitMs = 3000L
                    continue
                }
                _state.value = _state.value.copy(
                    working = false,
                    statusMessage = null,
                    errorMessage = error.message,
                )
                return
            }
        }
    }

    private fun selectedBar(): OwnerBarUiModel? =
        _state.value.bars.firstOrNull { it.barId == _state.value.selectedBarId }
}

private fun BarDto.toUiModel(): OwnerBarUiModel =
    OwnerBarUiModel(
        barId = barId,
        name = name,
        address = address,
        activeImportId = activeMenuImport?.menuImportId,
        activeImportStatus = activeMenuImport?.status,
    )
