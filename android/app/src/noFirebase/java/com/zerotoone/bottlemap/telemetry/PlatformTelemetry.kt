package com.zerotoone.bottlemap.telemetry
import android.content.Context
internal fun createPlatformTelemetry(context: Context, initiallyEnabled: Boolean): Telemetry = NoOpTelemetry
