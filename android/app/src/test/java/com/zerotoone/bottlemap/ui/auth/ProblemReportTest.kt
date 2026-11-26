package com.zerotoone.bottlemap.ui.auth

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import androidx.lifecycle.SavedStateHandle
import com.zerotoone.bottlemap.telemetry.ConsentTelemetry
import com.zerotoone.bottlemap.telemetry.FakeTelemetry
import com.zerotoone.bottlemap.telemetry.TelemetryEvent
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class ProblemReportTest {
    @Test fun onlyDiagnosticFieldsArePrefilledWithEncodedRuntimeValues() {
        val diagnostics = ReportDiagnostics("2.7 & beta+한글", 9876543210L,
            "Test & Co", "Model/+한글?", "17 preview")
        val uri = problemReportUri(diagnostics)
        assertEquals("https", uri.scheme)
        assertEquals("docs.google.com", uri.host)
        assertEquals("/forms/d/e/1FAIpQLSfVkgDygNzY2pL45XXu3H10izoblKCRa5LXaIiOS-PARnB1dg/viewform", uri.path)
        assertEquals(setOf("usp", "entry.258607485", "entry.604351798"), uri.queryParameterNames)
        assertEquals("2.7 & beta+한글 (9876543210)", uri.getQueryParameter("entry.258607485"))
        assertEquals("Test & Co Model/+한글? / Android 17 preview", uri.getQueryParameter("entry.604351798"))
        assertTrue(uri.toString().contains("%26"))
        for (field in listOf("1151544135", "399876014", "777503106", "57279747")) {
            assertNull(uri.getQueryParameter("entry.$field"))
        }
    }

    @Test fun launchReadsInstalledPackageAndDeviceWithoutAccountOrLocationData() {
        val context: Context = RuntimeEnvironment.getApplication()
        @Suppress("DEPRECATION")
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        // A changed package version proves this is not the build's example version.
        info.versionName = "9.8.7 qa"
        info.longVersionCode = 7654321098L
        shadowOf(context.packageManager).installPackage(info)
        org.robolectric.shadows.ShadowBuild.setManufacturer("Runtime manufacturer")
        org.robolectric.shadows.ShadowBuild.setModel("Runtime model")
        launchProblemReport(context)
        val intent = shadowOf(context as android.app.Application).nextStartedActivity
        assertEquals(Intent.ACTION_VIEW, intent.action)
        assertTrue(intent.categories.contains(Intent.CATEGORY_BROWSABLE))
        assertNull(intent.extras)
        assertEquals("9.8.7 qa (7654321098)", intent.data!!.getQueryParameter("entry.258607485"))
        assertEquals("Runtime manufacturer Runtime model / Android ${android.os.Build.VERSION.RELEASE}",
            intent.data!!.getQueryParameter("entry.604351798"))
    }

    @Test fun browserAcceptanceRecordsOnceAndRapidTapsDoNotLaunchAgain() {
        val telemetry = FakeTelemetry()
        var now = 10_000L
        val vm = ProblemReportViewModel(telemetry = telemetry, clock = { now })
        var launches = 0
        assertEquals(ReportLaunchResult.OPENED, vm.open { launches++ })
        repeat(10) { assertEquals(ReportLaunchResult.IGNORED, vm.open { launches++ }) }
        assertEquals(1, launches)
        assertEquals(listOf(TelemetryEvent.ReportProblemOpened), telemetry.events)
        now += 1_000
        assertEquals(ReportLaunchResult.OPENED, vm.open { launches++ })
        assertEquals(2, launches)
    }

    @Test fun missingOrFailingBrowserAllowsImmediateRetryWithoutFalseOpenEvents() {
        for (error in listOf(ActivityNotFoundException(), SecurityException(), IllegalStateException())) {
            val telemetry = FakeTelemetry()
            val vm = ProblemReportViewModel(telemetry = telemetry, clock = { 1L })
            assertEquals(ReportLaunchResult.FAILED, vm.open { throw error })
            assertTrue(telemetry.events.isEmpty())
            assertEquals(ReportLaunchResult.OPENED, vm.open {})
            assertEquals(listOf(TelemetryEvent.ReportProblemOpened), telemetry.events)
        }
    }

    @Test fun savedGuardSurvivesRecreationWithoutReplayingBrowserOrTelemetry() {
        val telemetry = FakeTelemetry()
        val handle = SavedStateHandle()
        val vm = ProblemReportViewModel(handle, telemetry) { 10L }
        vm.open {}
        val recreated = ProblemReportViewModel(SavedStateHandle(handle.keys().associateWith {
            handle.get<Any>(it)
        }), telemetry) { 11L }
        assertEquals(ReportLaunchResult.IGNORED, recreated.open { fail("duplicate browser") })
        assertEquals(1, telemetry.events.size)
    }

    @Test fun reportingWorksIndependentlyOfTelemetryConsentAndBuildGate() {
        for (allowed in listOf(false, true)) {
            val sink = FakeTelemetry()
            val gate = ConsentTelemetry(sink, allowed)
            var now = 0L
            var launches = 0
            val vm = ProblemReportViewModel(telemetry = gate, clock = { now })
            vm.open { launches++ }
            assertTrue(sink.events.isEmpty())
            gate.setEnabled(true)
            now += 1_000
            vm.open { launches++ }
            assertEquals(if (allowed) 1 else 0, sink.events.size)
            gate.setEnabled(false)
            now += 1_000
            vm.open { launches++ }
            assertEquals(if (allowed) 1 else 0, sink.events.size)
            assertEquals(3, launches)
        }
    }
}
