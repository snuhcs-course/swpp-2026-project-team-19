package com.zerotoone.bottlemap.telemetry

/** Central gate, also prevents tests and disabled debug builds from queuing events. */
class ConsentTelemetry(private val delegate: Telemetry, private val buildAllowed: Boolean) : Telemetry {
    private var enabled = false
    private var screen = ScreenRoute.UNKNOWN
    @Synchronized override fun setEnabled(enabled: Boolean) {
        val allowed = enabled && buildAllowed
        delegate.setEnabled(allowed)
        this.enabled = allowed
        if (allowed) delegate.setScreen(screen)
    }
    @Synchronized override fun log(event: TelemetryEvent) { if (enabled) delegate.log(event) }
    @Synchronized override fun setScreen(route: ScreenRoute) {
        screen = route
        if (enabled) delegate.setScreen(route)
    }
}
