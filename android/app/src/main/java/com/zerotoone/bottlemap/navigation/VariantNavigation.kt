package com.zerotoone.bottlemap.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.material3.LocalRippleConfiguration
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import com.zerotoone.bottlemap.data.owner.MockOwnerLoadState
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.zerotoone.bottlemap.data.owner.OwnerRuntime
import com.zerotoone.bottlemap.ui.auth.AuthViewModel
import com.zerotoone.bottlemap.ui.auth.AuthUiState
import com.zerotoone.bottlemap.ui.owner.OwnerMockViewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.compose.composable
import androidx.navigation.navigation
import com.zerotoone.bottlemap.data.owner.review.LivePhotoReviewRepository
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewScreen
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewViewModel
import com.zerotoone.bottlemap.ui.owner.OwnerOnboardingScreen
import com.zerotoone.bottlemap.ui.owner.OwnerManagementHomeScreen
import com.zerotoone.bottlemap.ui.owner.OwnerMenuPhotoSelectionScreen
import com.zerotoone.bottlemap.ui.owner.OwnerMenuPhotoJobScreen
import com.zerotoone.bottlemap.ui.owner.OwnerPhotoStage8Screen
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
internal enum class OwnerAuthRecoveryAction { WAIT, LOGIN, ACCOUNT_RETRY }

internal fun ownerAuthRecoveryAction(state: AuthUiState): OwnerAuthRecoveryAction = when (state) {
    AuthUiState.Guest -> OwnerAuthRecoveryAction.LOGIN
    is AuthUiState.SignInError -> OwnerAuthRecoveryAction.ACCOUNT_RETRY
    else -> OwnerAuthRecoveryAction.WAIT
}

/** Never leave an expired Owner destination showing an endless spinner. */
@androidx.compose.runtime.Composable
private fun OwnerAuthGuard(
    state: AuthUiState,
    onSignOut: () -> Unit,
    onRecoverableAccountError: () -> Unit,
) {
    LaunchedEffect(state) {
        when (ownerAuthRecoveryAction(state)) {
            OwnerAuthRecoveryAction.LOGIN -> onSignOut()
            OwnerAuthRecoveryAction.ACCOUNT_RETRY -> onRecoverableAccountError()
            OwnerAuthRecoveryAction.WAIT -> Unit
        }
    }
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        CircularProgressIndicator()
    }
}

internal fun NavGraphBuilder.registerVariantRoutes(
    navController: NavHostController,
    onNotice: (String) -> Unit = {},
    authViewModel: AuthViewModel,
    onForceOwnerReauthentication: () -> Unit,
    onRecoverableOwnerAuthError: () -> Unit,
) {
    // Shared by both ends of the Owner manage <-> preview round trip.
    val previewSwitchCooldown = OwnerPreviewSwitchCooldown()
    navigation(route = OwnerRoutes.GRAPH, startDestination = OwnerRoutes.ENTRY) {
        composable(OwnerRoutes.ENTRY) {
            val authState = authViewModel.state.collectAsStateWithLifecycle().value
            val ownerId = (authState as? AuthUiState.SignedIn)?.user?.userId
            if (ownerId == null) {
                OwnerAuthGuard(authState, onForceOwnerReauthentication,
                    onRecoverableOwnerAuthError)
                return@composable
            }
                CompositionLocalProvider(
                    LocalRippleConfiguration provides null,
                ) {
            val ownerViewModel: OwnerMockViewModel = viewModel(
                key = "owner-entry-$ownerId",
                factory = OwnerMockViewModel.Factory(
                    OwnerRuntime.repository(LocalContext.current, ownerId)))
            if (abortUnavailableOwnerEntry(ownerViewModel, retryOnEntry = true) {
                    navController.popBackStack()
                }) return@CompositionLocalProvider
            // Always show the owned-bar list. One or many bars use the same flow;
            // the user explicitly selects which bar to manage.
            OwnerOnboardingScreen(
                viewModel = ownerViewModel,
                onBack = { navController.popBackStack() },
                onManagerPreview = { navController.navigate(OwnerPage.MGR_HOME.route) },
            )
            }
        }
        composable(OwnerRoutes.ADD_BAR) {
            val authState = authViewModel.state.collectAsStateWithLifecycle().value
            val ownerId = (authState as? AuthUiState.SignedIn)?.user?.userId
            if (ownerId == null) {
                OwnerAuthGuard(authState, onForceOwnerReauthentication,
                    onRecoverableOwnerAuthError)
                return@composable
            }
                CompositionLocalProvider(
                    LocalRippleConfiguration provides null,
                ) {
            val data: OwnerMockViewModel = viewModel(key = "owner-add-bar-$ownerId",
                factory = OwnerMockViewModel.Factory(OwnerRuntime.repository(LocalContext.current, ownerId)))
            if (abortUnavailableOwnerEntry(data, retryOnEntry = true) { navController.popBackStack() }) return@CompositionLocalProvider
            OwnerOnboardingScreen(
                viewModel = data,
                onBack = { navController.popBackStack() },
                onManagerPreview = { navController.navigate(OwnerPage.MGR_HOME.route) },
                startRegistration = true,
            )
            }
        }
        OwnerPage.entries.forEach { page ->
            composable(page.route) { reviewEntry ->
                val authState = authViewModel.state.collectAsStateWithLifecycle().value
                val ownerId = (authState as? AuthUiState.SignedIn)?.user?.userId
                if (ownerId == null) {
                    OwnerAuthGuard(authState, onForceOwnerReauthentication,
                        onRecoverableOwnerAuthError)
                    return@composable
                }
                val data: OwnerMockViewModel = viewModel(key = "owner-page-${page.route}-$ownerId",
                    factory = OwnerMockViewModel.Factory(
                        OwnerRuntime.repository(LocalContext.current, ownerId)))
                val mockState = data.state.collectAsStateWithLifecycle().value
                if (page !in setOf(OwnerPage.MGR_PHOTO, OwnerPage.MGR_JOB, OwnerPage.MGR_REVIEW) &&
                    abortUnavailableOwnerEntry(data) { navController.popBackStack() }) return@composable
                // Owner-wide policy: no transient bright/ripple feedback on press.
                // Stateful selected/checked indicators are intentionally preserved.
                CompositionLocalProvider(
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
                            navController.currentBackStackEntry?.savedStateHandle
                                ?.set("resumeOwnerImport",status==MockImportStatus.READY_FOR_REVIEW)
                            navController.navigate(when(status) {
                                MockImportStatus.APPLIED -> OwnerPage.MGR_MENU.route
                                MockImportStatus.READY_FOR_REVIEW -> OwnerPage.MGR_REVIEW.route
                                else -> OwnerPage.MGR_JOB.route
                            })
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
                        onNotice = onNotice,
                        onExistingJob = { status ->
                            navController.currentBackStackEntry?.savedStateHandle
                                ?.set("resumeOwnerImport",status==MockImportStatus.READY_FOR_REVIEW)
                            navController.navigate(if(status==MockImportStatus.READY_FOR_REVIEW)
                                OwnerPage.MGR_REVIEW.route else OwnerPage.MGR_JOB.route)
                        },
                    )
                    OwnerPage.MGR_PHOTO -> OwnerMenuPhotoSelectionScreen(
                        state = mockState, viewModel = data,
                        onBack = { navController.popBackStack() },
                        onJob = { navController.navigate(OwnerPage.MGR_JOB.route) }
                    )
                    OwnerPage.MGR_JOB -> OwnerMenuPhotoJobScreen(
                        state = mockState, viewModel = data,
                        onHome = {
                            navController.navigate(OwnerPage.MGR_MENU.route) {
                                popUpTo(OwnerPage.MGR_HOME.route) { inclusive = false }
                                launchSingleTop = true
                            }
                        },
                        onRetryPhotos = { navController.navigate(OwnerPage.MGR_PHOTO.route) },
                        onReview = {
                            navController.navigate(OwnerPage.MGR_REVIEW.route) {
                                popUpTo(OwnerPage.MGR_JOB.route) { inclusive = true }
                                launchSingleTop = true
                            }
                        }
                    )
                    OwnerPage.MGR_REVIEW -> {
                        val snapshot = when (mockState) {
                            is MockOwnerLoadState.Ready -> mockState.snapshot
                            is MockOwnerLoadState.Empty -> mockState.snapshot
                            else -> null
                        }
                        val activeBar = snapshot?.selectedBarId
                            ?: snapshot?.bars?.firstOrNull()?.barId
                        val latestJob = snapshot?.imports?.lastOrNull {
                            it.barId == activeBar && it.status == MockImportStatus.READY_FOR_REVIEW
                        }
                        // Keep the import ID tied to this navigation entry.
                        // After review-and-apply commits, the import leaves
                        // READY_FOR_REVIEW; recomposing must NOT create a new
                        // "owner-review-fixture" ViewModel that fails to load.
                        var capturedImportId by rememberSaveable(reviewEntry.id) {
                            mutableStateOf<String?>(null)
                        }
                        val selectedImportId = capturedImportId ?: latestJob?.menuImportId
                        if (capturedImportId == null && latestJob != null) {
                            SideEffect {
                                if (capturedImportId == null)
                                    capturedImportId = latestJob.menuImportId
                            }
                        }
                        when {
                            selectedImportId != null -> {
                                val repository = LivePhotoReviewRepository(
                                    owner = data, importId = selectedImportId,
                                    context = LocalContext.current.applicationContext,
                                )
                                val reviewVm: PhotoReviewViewModel = viewModel(
                                    key = "owner-review-$selectedImportId",
                                    factory = PhotoReviewViewModel.Factory(repository),
                                )
                                PhotoReviewScreen(
                                    vm = reviewVm,
                                    onLeave = {
                                // The v22 result page already confirms publication;
                                // do not show a second popup on menu management.
                                data.consumePhotoPublishWarning()
                                if (!navController.popBackStack(
                                        OwnerPage.MGR_MENU.route, inclusive = false
                                    )) {
                                    navController.navigate(OwnerPage.MGR_MENU.route) {
                                        popUpTo(OwnerPage.MGR_REVIEW.route) {
                                            inclusive = true
                                        }
                                        launchSingleTop = true
                                    }
                                }
                                    },
                                    onReauthenticate = onForceOwnerReauthentication,
                                )
                            }
                            mockState == MockOwnerLoadState.Loading -> {
                                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                                    CircularProgressIndicator()
                                }
                            }
                            else -> {
                                // No pending import: there is nothing to retry.
                                // Leave the dead-end instead of spinning forever.
                                LaunchedEffect(reviewEntry.id) {
                                    if (!navController.popBackStack(OwnerPage.MGR_MENU.route, false))
                                        navController.navigate(OwnerPage.MGR_MENU.route) {
                                            popUpTo(OwnerPage.MGR_REVIEW.route) { inclusive = true }
                                            launchSingleTop = true
                                        }
                                    onNotice("검수할 메뉴판 작업이 없어요. 메뉴 관리에서 새로 시작해 주세요.")
                                }
                                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                                    Text("메뉴 관리로 돌아가는 중이에요.")
                                }
                            }
                        }
                    }
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


/** Abort only an unavailable cold entry. Cached owner screens keep their current content. */
@Composable
private fun abortUnavailableOwnerEntry(
    viewModel: OwnerMockViewModel, retryOnEntry: Boolean = false, onBack: () -> Unit,
): Boolean {
    val state = viewModel.state.collectAsStateWithLifecycle().value
    var started by remember(viewModel) { mutableStateOf(!retryOnEntry) }
    LaunchedEffect(viewModel) {
        if (retryOnEntry && viewModel.state.value != MockOwnerLoadState.Loading) viewModel.retry()
        started = true
    }
    LaunchedEffect(started, state) {
        if (started && viewModel.state.value == MockOwnerLoadState.NetworkUnavailable) onBack()
    }
    return !started || state == MockOwnerLoadState.NetworkUnavailable
}
