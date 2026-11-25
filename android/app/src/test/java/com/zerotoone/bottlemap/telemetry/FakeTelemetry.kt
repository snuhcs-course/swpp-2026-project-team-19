package com.zerotoone.bottlemap.telemetry

class FakeTelemetry : Telemetry {
    val events = mutableListOf<TelemetryEvent>()
    val enabledChanges = mutableListOf<Boolean>()
    val screens = mutableListOf<ScreenRoute>()
    override fun log(event: TelemetryEvent) { events += event }
    override fun setEnabled(enabled: Boolean) { enabledChanges += enabled }
    override fun setScreen(route: ScreenRoute) { screens += route }
}
