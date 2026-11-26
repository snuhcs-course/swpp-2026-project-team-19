package com.zerotoone.bottlemap.ui.auth

import android.os.SystemClock
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import com.zerotoone.bottlemap.telemetry.AppTelemetry
import com.zerotoone.bottlemap.telemetry.Telemetry
import com.zerotoone.bottlemap.telemetry.TelemetryEvent

internal enum class ReportLaunchResult { OPENED, FAILED, IGNORED }

internal class ProblemReportViewModel(
    private val savedState: SavedStateHandle = SavedStateHandle(),
    private val telemetry: Telemetry = AppTelemetry.current,
    private val clock: () -> Long = { SystemClock.elapsedRealtime() },
) : ViewModel() {
    /** Survives rotation; a failed attempt permits immediate explicit retry. */
    fun open(launch: () -> Unit): ReportLaunchResult {
        val now = clock()
        val last = savedState.get<Long>(LAST_LAUNCH)
        if (last != null && now >= last && now - last < 1_000) return ReportLaunchResult.IGNORED
        savedState[LAST_LAUNCH] = now
        try {
            launch()
        } catch (_: RuntimeException) {
            // No exception prose or URL is logged: external handlers may include private data.
            savedState.remove<Long>(LAST_LAUNCH)
            return ReportLaunchResult.FAILED
        }
        // Accepted browser launch only; neither form rendering nor submission is observable.
        telemetry.log(TelemetryEvent.ReportProblemOpened)
        return ReportLaunchResult.OPENED
    }

    private companion object { const val LAST_LAUNCH = "problem-report-last-launch" }
}
