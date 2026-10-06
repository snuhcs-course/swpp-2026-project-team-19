package com.zerotoone.bottlemap.ui.owner

import android.app.Application
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.zerotoone.bottlemap.data.ImageUploadPreparer
import com.zerotoone.bottlemap.data.Repositories
import com.zerotoone.bottlemap.network.BarDto
import com.zerotoone.bottlemap.network.BottleMapApiException
import java.util.UUID
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class MenuUploadViewModel(
    application: Application,
) : AndroidViewModel(application) {
    private val repository = Repositories.owner
    private val imagePreparer = ImageUploadPreparer(application.contentResolver)

    private val _state = MutableStateFlow(MenuUploadUiState())
    val state: StateFlow<MenuUploadUiState> = _state.asStateFlow()

    private var pendingIdempotencyKey: String? = null

    init {
        loadBars()
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
        if (_state.value.working) return
        _state.value = _state.value.copy(
            selectedBarId = barId,
            selectedImage = null,
            statusMessage = null,
            errorMessage = null,
        )
        pendingIdempotencyKey = null
    }

    fun setMode(mode: ImportModeUi) {
        if (_state.value.working) return
        if (_state.value.mode == mode) return
        _state.value = _state.value.copy(mode = mode)
        pendingIdempotencyKey = null
    }

    fun selectImage(uri: Uri) {
        if (_state.value.working) return
        viewModelScope.launch {
            runCatching { imagePreparer.describe(uri) }
                .onSuccess { selected ->
                    _state.value = _state.value.copy(
                        selectedImage = selected,
                        errorMessage = null,
                    )
                    pendingIdempotencyKey = null
                }
                .onFailure { error ->
                    _state.value = _state.value.copy(
                        errorMessage = error.message ?: "Unable to use this image.",
                    )
                }
        }
    }

    fun clearImage() {
        if (_state.value.working) return
        _state.value = _state.value.copy(selectedImage = null, errorMessage = null)
        pendingIdempotencyKey = null
    }

    fun continueActiveImport() {
        val active = selectedBar()?.activeImportId ?: return
        startPolling(active, initialDelayMs = 0L)
    }

    fun upload() {
        val snapshot = _state.value
        val bar = selectedBar() ?: return
        val selected = snapshot.selectedImage ?: return
        if (snapshot.working) return

        val key = pendingIdempotencyKey ?: UUID.randomUUID().toString().also {
            pendingIdempotencyKey = it
        }

        _state.value = snapshot.copy(
            working = true,
            statusMessage = "Preparing menu photo…",
            errorMessage = null,
        )
        viewModelScope.launch {
            try {
                val prepared = imagePreparer.prepare(Uri.parse(selected.uri))
                _state.value = _state.value.copy(statusMessage = "Uploading menu…")
                val accepted = repository.uploadMenuImport(
                    barId = bar.barId,
                    image = prepared,
                    mode = snapshot.mode.apiValue,
                    idempotencyKey = key,
                )
                startPollingInCurrentJob(
                    accepted.menuImportId,
                    accepted.pollAfterMs,
                )
            } catch (error: BottleMapApiException) {
                if (error.code == "ACTIVE_IMPORT_EXISTS") {
                    val existing = error.details?.get("menuImportId") as? String
                    if (existing != null) {
                        startPollingInCurrentJob(existing, 0L)
                        return@launch
                    }
                }
                if (error.code == "IDEMPOTENCY_KEY_REUSED") {
                    pendingIdempotencyKey = null
                }
                _state.value = _state.value.copy(
                    working = false,
                    statusMessage = null,
                    errorMessage = if (error.code == "IDEMPOTENCY_KEY_REUSED") {
                        "This upload key was already used with different content. Tap Upload again to start a new submit attempt."
                    } else {
                        error.message
                    },
                )
            } catch (error: Throwable) {
                _state.value = _state.value.copy(
                    working = false,
                    statusMessage = null,
                    errorMessage = error.message ?: "Menu upload failed.",
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
                            errorMessage = null,
                        )
                        waitMs = status.pollAfterMs ?: 3000L
                    }

                    "ready_for_review" -> {
                        pendingIdempotencyKey = null
                        _state.value = _state.value.copy(
                            working = false,
                            statusMessage = null,
                            errorMessage = null,
                            openReviewImportId = menuImportId,
                        )
                        return
                    }

                    "failed" -> {
                        pendingIdempotencyKey = null
                        _state.value = _state.value.copy(
                            working = false,
                            statusMessage = null,
                            errorMessage = status.failure?.message ?: "Menu extraction failed.",
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
