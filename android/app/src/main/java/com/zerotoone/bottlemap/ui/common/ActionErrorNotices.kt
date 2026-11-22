package com.zerotoone.bottlemap.ui.common

import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.network.menuWriteErrorText
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.asSharedFlow

/** Shared owner-network notice. Customer search and photo review retain their own handling. */
object ActionErrorNotices {
    const val NETWORK_MESSAGE = "인터넷 연결을 확인하고 다시 시도해 주세요."
    private val _networkErrors = MutableSharedFlow<Unit>(
        extraBufferCapacity = 1, onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )
    val networkErrors = _networkErrors.asSharedFlow()

    internal fun reportNetworkError() { _networkErrors.tryEmit(Unit) }
}

internal fun Throwable.isNetworkFailure(): Boolean =
    (this is BottleMapApiException && code == "NETWORK_ERROR") ||
        this is ConnectException || this is SocketTimeoutException || this is UnknownHostException

/** Return true only when a network failure was consumed by the common toast. */
internal fun Throwable.notifyNetworkError(): Boolean {
    if (!isNetworkFailure()) return false
    ActionErrorNotices.reportNetworkError()
    return true
}

/** Null clears inline errors; the failed action's finally block releases its busy state.
 * No connectivity latch, automatic retry, navigation, or draft mutation is introduced.
 */
fun Throwable.actionErrorMessage(
    fallback: String = "처리하지 못했어요. 잠시 후 다시 시도해 주세요.",
): String? = if (isNetworkFailure()) {
    ActionErrorNotices.reportNetworkError()
    null
} else userMessage(fallback)

fun menuWriteActionErrorText(error: Throwable): String? = if (error.isNetworkFailure()) {
    ActionErrorNotices.reportNetworkError()
    null
} else menuWriteErrorText(error)
