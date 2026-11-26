package com.zerotoone.bottlemap.ui.auth

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import androidx.core.content.pm.PackageInfoCompat

/** An allowlist: no account, location, report contents or persistent identifiers. */
internal data class ReportDiagnostics(
    val versionName: String,
    val versionCode: Long,
    val manufacturer: String,
    val model: String,
    val androidVersion: String,
) {
    companion object {
        fun read(context: Context): ReportDiagnostics {
            @Suppress("DEPRECATION")
            val info = context.packageManager.getPackageInfo(context.packageName, 0)
            return ReportDiagnostics(
                info.versionName.orEmpty(), PackageInfoCompat.getLongVersionCode(info),
                Build.MANUFACTURER, Build.MODEL, Build.VERSION.RELEASE,
            )
        }
    }
}

internal const val PROBLEM_REPORT_FORM =
    "https://docs.google.com/forms/d/e/1FAIpQLSfVkgDygNzY2pL45XXu3H10izoblKCRa5LXaIiOS-PARnB1dg/viewform"

internal fun problemReportUri(diagnostics: ReportDiagnostics): Uri =
    Uri.parse(PROBLEM_REPORT_FORM).buildUpon()
        .appendQueryParameter("usp", "pp_url")
        .appendQueryParameter("entry.258607485", "${diagnostics.versionName} (${diagnostics.versionCode})")
        .appendQueryParameter("entry.604351798",
            "${diagnostics.manufacturer} ${diagnostics.model} / Android ${diagnostics.androidVersion}")
        .build()

/** ACTION_VIEW gives the user control of review/submission; no form POST or app navigation. */
internal fun launchProblemReport(context: Context) {
    context.startActivity(Intent(Intent.ACTION_VIEW, problemReportUri(ReportDiagnostics.read(context)))
        .addCategory(Intent.CATEGORY_BROWSABLE)
        .apply { if (context !is android.app.Activity) addFlags(Intent.FLAG_ACTIVITY_NEW_TASK) })
}
