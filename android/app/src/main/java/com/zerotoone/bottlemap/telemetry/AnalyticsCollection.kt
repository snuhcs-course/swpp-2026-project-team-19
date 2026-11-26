package com.zerotoone.bottlemap.telemetry

/** SDK calls stay ordered: collection-disabled Analytics discards custom user properties.
 * This is called only after the app's consent/build gate permits collection.
 * Consent (including denied advertising storage) must precede enabling Analytics.
 */
internal fun enableConsentedAnalytics(
    grantConsent: () -> Unit,
    enableCollection: () -> Unit,
    setReleaseChannel: () -> Unit,
) {
    grantConsent()
    enableCollection()
    setReleaseChannel()
}
