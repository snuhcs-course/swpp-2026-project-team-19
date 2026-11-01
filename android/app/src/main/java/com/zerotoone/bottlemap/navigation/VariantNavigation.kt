package com.zerotoone.bottlemap.navigation

import android.net.Uri
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.foundation.LocalIndication
import androidx.compose.material3.LocalRippleConfiguration
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.runtime.LaunchedEffect
import com.zerotoone.bottlemap.data.owner.MockOwnerLoadState
import com.zerotoone.bottlemap.data.owner.openSingleBarManager
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.zerotoone.bottlemap.data.owner.OwnerMockRuntime
import com.zerotoone.bottlemap.ui.owner.OwnerMockViewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navigation
import androidx.navigation.navArgument
import com.zerotoone.bottlemap.BuildConfig
import com.zerotoone.bottlemap.ui.owner.ExtractionReviewScreen
import com.zerotoone.bottlemap.ui.owner.MenuUploadScreen
import com.zerotoone.bottlemap.ui.owner.OwnerComponentGallery
import com.zerotoone.bottlemap.ui.owner.OwnerOnboardingScreen
import com.zerotoone.bottlemap.ui.owner.OwnerManagementHomeScreen
import com.zerotoone.bottlemap.ui.owner.OwnerOperatingQuickScreen
import com.zerotoone.bottlemap.ui.owner.OwnerMenuQuickEntryScreen
import com.zerotoone.bottlemap.data.owner.MockImportStatus
import com.zerotoone.bottlemap.ui.owner.OwnerInfoHtmlV4Screen
import com.zerotoone.bottlemap.ui.owner.OwnerPhotoHtmlV4Screen
import com.zerotoone.bottlemap.ui.owner.OwnerBarTagsEditorScreen
import com.zerotoone.bottlemap.ui.owner.OwnerBarHoursEditorScreen
import com.zerotoone.bottlemap.ui.owner.OwnerPreviewHtmlV4Screen
import com.zerotoone.bottlemap.ui.owner.OwnerSkeletonScreen

/** One Android artifact: everyone starts in Customer, with Owner accessible from My Page. */
internal const val variantStartDestination = "customer"

@OptIn(ExperimentalMaterial3Api::class)
internal fun NavGraphBuilder.registerVariantRoutes(navController: NavHostController) {
    // Shared by both ends of the Owner manage <-> preview round trip.
    val previewSwitchCooldown = OwnerPreviewSwitchCooldown()
    navigation(route = OwnerRoutes.GRAPH, startDestination = OwnerRoutes.ENTRY) {
        composable(OwnerRoutes.ENTRY) {
                CompositionLocalProvider(
                    LocalIndication provides null,
                    LocalRippleConfiguration provides null,
                ) {
            val ownerViewModel: OwnerMockViewModel = viewModel(factory = OwnerMockViewModel.Factory(
                OwnerMockRuntime.repository(LocalContext.current)))
            val mockState = ownerViewModel.state.collectAsStateWithLifecycle().value
            val snapshot = when (mockState) {
                is MockOwnerLoadState.Ready -> mockState.snapshot
                is MockOwnerLoadState.Empty -> mockState.snapshot
                else -> null
            }
            val directManager = snapshot?.openSingleBarManager() == true
            LaunchedEffect(directManager) {
                if (directManager) {
                    navController.navigate(OwnerPage.MGR_HOME.route) {
                        popUpTo(OwnerRoutes.ENTRY) { inclusive = true }
                        launchSingleTop = true
                    }
                }
            }
            if (!directManager) OwnerOnboardingScreen(
                viewModel = ownerViewModel,
                onBack = { navController.popBackStack() },
                onFirstReview = { navController.navigate(OwnerPage.PHOTO_START.route) },
                onManagerPreview = { navController.navigate(OwnerPage.MGR_HOME.route) },
                onComponents = { navController.navigate(OwnerRoutes.COMPONENTS) },
                onLegacyDebugUpload = OwnerRoutes.legacyDebugEntryRoute(BuildConfig.DEBUG)?.let { route ->
                    { navController.navigate(route) }
                },
            )
            }
        }
        composable(OwnerRoutes.ADD_BAR) {
                CompositionLocalProvider(
                    LocalIndication provides null,
                    LocalRippleConfiguration provides null,
                ) {
            OwnerOnboardingScreen(
                viewModel = viewModel(factory = OwnerMockViewModel.Factory(
                    OwnerMockRuntime.repository(LocalContext.current))),
                onBack = { navController.popBackStack() },
                onFirstReview = { navController.navigate(OwnerPage.PHOTO_START.route) },
                onManagerPreview = { navController.navigate(OwnerPage.MGR_HOME.route) },
                startRegistration = true,
            )
            }
        }
        composable(OwnerRoutes.COMPONENTS) {
                CompositionLocalProvider(
                    LocalIndication provides null,
                    LocalRippleConfiguration provides null,
                ) {
            OwnerComponentGallery(onBack = { navController.popBackStack() })
            }
        }
        OwnerPage.entries.forEach { page ->
            composable(page.route) {
                val data: OwnerMockViewModel = viewModel(factory = OwnerMockViewModel.Factory(
                    OwnerMockRuntime.repository(LocalContext.current)))
                val mockState = data.state.collectAsStateWithLifecycle().value
                // Owner-wide policy: no transient bright/ripple feedback on press.
                // Stateful selected/checked indicators are intentionally preserved.
                CompositionLocalProvider(
                    LocalIndication provides null,
                    LocalRippleConfiguration provides null,
                ) {
                when (page) {
                    OwnerPage.MGR_HOME -> OwnerManagementHomeScreen(
                        state = mockState,
                        viewModel = data,
                        onRetry = data::retry,
                        onBack = { navController.popBackStack() },
                        onPreview = { navController.openOwnerManagerPreviewSafely(previewSwitchCooldown) },
                        onInfo = { navController.navigate(OwnerPage.MGR_INFO.route) },
                        onStatus = { navController.navigate(OwnerPage.MGR_STATUS.route) },
                        onMenu = { navController.navigate(OwnerPage.MGR_MENU.route) },
                        onAddBar = { navController.navigate(OwnerRoutes.ADD_BAR) },
                        onJob = { status ->
                            navController.navigate(
                                if (status == MockImportStatus.READY_FOR_REVIEW)
                                    OwnerPage.MGR_REVIEW.route
                                else if (status == MockImportStatus.APPLIED)
                                    OwnerPage.MGR_MENU.route
                                else OwnerPage.MGR_JOB.route
                            )
                        },
                    )
                    OwnerPage.MGR_STATUS -> OwnerOperatingQuickScreen(
                        state = mockState,
                        viewModel = data,
                        onBack = { navController.popBackStack() },
                    )
                    OwnerPage.MGR_INFO -> OwnerInfoHtmlV4Screen(
                        state = mockState, viewModel = data,
                        onBack = { navController.popBackStack() },
                        onPhotos = { navController.navigate(OwnerPage.MGR_PHOTOS.route) },
                    )
                    OwnerPage.MGR_PHOTOS -> OwnerPhotoHtmlV4Screen(
                        state = mockState, viewModel = data,
                        onBack = { navController.popBackStack() },
                    )
                    // Legacy UX jump destinations share the one HTML-v4 info form.
                    OwnerPage.MGR_TAGS, OwnerPage.MGR_HOURS -> OwnerInfoHtmlV4Screen(
                        state = mockState, viewModel = data,
                        onBack = { navController.popBackStack() },
                        onPhotos = { navController.navigate(OwnerPage.MGR_PHOTOS.route) },
                    )
                    OwnerPage.MGR_PREVIEW -> OwnerPreviewHtmlV4Screen(
                        state = mockState, viewModel = data,
                        onBack = { navController.returnToOwnerManagerSafely(previewSwitchCooldown) },
                        onManage = { navController.returnToOwnerManagerSafely(previewSwitchCooldown) },
                    )
                    OwnerPage.MGR_MENU -> OwnerMenuQuickEntryScreen(
                        state = mockState, viewModel = data,
                        onRetry = data::retry,
                        onBack = { navController.popBackStack() },
                        onNewPhoto = { navController.navigate(OwnerPage.MGR_PHOTO.route) },
                        onExistingJob = { status ->
                            navController.navigate(
                                if (status == MockImportStatus.READY_FOR_REVIEW)
                                    OwnerPage.MGR_REVIEW.route else OwnerPage.MGR_JOB.route
                            )
                        },
                    )
                    else -> OwnerSkeletonScreen(
                        page = page,
                        mockState = mockState,
                        onRetry = data::retry,
                        onBack = { navController.popBackStack() },
                        onNavigate = { next -> navController.navigate(next.route) },
                        onHome = {
                            if (!navController.popBackStack(OwnerRoutes.ENTRY, inclusive = false)) {
                                navController.popBackStack(OwnerRoutes.GRAPH, inclusive = true)
                            }
                        },
                        onLegacyDebugUpload = null,
                    )
                }
                }
            }
        }

        // Keep the earlier developer integration test routes available in DEBUG builds
        // only. They use temp operator login and must not be exposed from production UX.
        if (BuildConfig.DEBUG) {
            composable(OwnerRoutes.LEGACY_UPLOAD) {
                MenuUploadScreen(
                    onOpenReview = { id ->
                        navController.navigate("owner/extraction-review/" + Uri.encode(id))
                    },
                )
            }
            composable(
                route = OwnerRoutes.LEGACY_REVIEW,
                arguments = listOf(navArgument("menuImportId") { type = NavType.StringType }),
            ) { entry ->
                ExtractionReviewScreen(
                    menuImportId = entry.arguments?.getString("menuImportId").orEmpty(),
                    onBack = { navController.popBackStack() },
                )
            }
        }
    }
}

/**
 * A fast click on "미리보기 -> 관리 -> 미리보기" can arrive while the outgoing
 * Compose destination is still being drawn. Never use an unqualified popBackStack
 * for that return action: a stale second click must not pop the manager itself.
 */
/**
 * One monotonic 500-ms window for both "미리보기" and "관리" actions.
 * The time source is injectable so the boundary can be regression tested.
 */
internal class OwnerPreviewSwitchCooldown(
    private val nowMs: () -> Long = { android.os.SystemClock.elapsedRealtime() },
) {
    private var lastAcceptedMs: Long? = null

    fun allow(): Boolean {
        val current = nowMs()
        val previous = lastAcceptedMs
        if (previous != null && current - previous < 500L) return false
        lastAcceptedMs = current
        return true
    }
}

internal fun NavHostController.returnToOwnerManagerSafely(
    cooldown: OwnerPreviewSwitchCooldown,
): Boolean {
    if (currentDestination?.route != OwnerPage.MGR_PREVIEW.route) return false
    if (!cooldown.allow()) return false
    return popBackStack(OwnerPage.MGR_HOME.route, inclusive = false)
}

/** Reject clicks on a stale destination and early repeats across both buttons. */
internal fun NavHostController.openOwnerManagerPreviewSafely(
    cooldown: OwnerPreviewSwitchCooldown,
): Boolean {
    if (currentDestination?.route != OwnerPage.MGR_HOME.route) return false
    if (!cooldown.allow()) return false
    navigate(OwnerPage.MGR_PREVIEW.route) { launchSingleTop = true }
    return true
}
