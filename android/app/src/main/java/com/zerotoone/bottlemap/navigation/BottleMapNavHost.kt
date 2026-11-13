package com.zerotoone.bottlemap.navigation

import android.net.Uri
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.isImeVisible
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.navigation.compose.currentBackStackEntryAsState
import com.zerotoone.bottlemap.BuildConfig
import com.zerotoone.bottlemap.data.owner.review.MockPhotoReviewRepository
import com.zerotoone.bottlemap.data.owner.review.MockPhotoReviewScenario
import com.zerotoone.bottlemap.ui.auth.LoginErrorScreen
import com.zerotoone.bottlemap.ui.auth.SharedPrefsFirstLaunchStore
import com.zerotoone.bottlemap.ui.auth.SignInOutcome
import com.zerotoone.bottlemap.ui.auth.WelcomeScreen
import com.zerotoone.bottlemap.ui.auth.rememberGoogleSignInFlow
import com.zerotoone.bottlemap.ui.common.UxToast
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewScreen
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navigation
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.zerotoone.bottlemap.ui.auth.AccountScreen
import com.zerotoone.bottlemap.ui.auth.AuthUiState
import com.zerotoone.bottlemap.ui.auth.AuthViewModel
import com.zerotoone.bottlemap.ui.auth.GoogleLoginScreen
import com.zerotoone.bottlemap.ui.customer.BarDetailScreen
import com.zerotoone.bottlemap.ui.customer.BarDetailViewModel
import com.zerotoone.bottlemap.ui.customer.BarLocationMapScreen
import com.zerotoone.bottlemap.ui.customer.CustomerP18Home
import com.zerotoone.bottlemap.ui.customer.CustomerP18Results
import com.zerotoone.bottlemap.ui.customer.NearbyBarsScreen
import com.zerotoone.bottlemap.ui.customer.nearbyBarsViewModel
import com.zerotoone.bottlemap.ui.common.DelayedLoading

private const val SEARCH_VALIDATION_ERROR_KEY = "searchValidationErrorCode"
private const val REFRESH_AFTER_MISSING_BAR_KEY = "refreshAfterMissingBar"
private const val REFRESH_AFTER_MISSING_PRODUCT_KEY = "refreshAfterMissingProduct"

private object Routes {
    const val CUSTOMER_GRAPH = TabRoutes.SEARCH_GRAPH
    const val CUSTOMER_SEARCH = TabRoutes.SEARCH_HOME
    const val CUSTOMER_NEARBY = "customer/nearby"
    const val CUSTOMER_ACCOUNT = "customer/account"
    const val CUSTOMER_LOGIN = "customer/login"
    const val CUSTOMER_SEARCH_RESULTS = "customer/search-results"
    const val CUSTOMER_QUERY_ARGUMENT = "query"
    const val CUSTOMER_PRODUCT_ARGUMENT = "productId"
    const val CUSTOMER_SOURCE_ARGUMENT = "source"
    const val BAR_ID_ARGUMENT = "barId"
    const val CUSTOMER_BAR_DETAIL_ROUTE =
        "customer/bar-detail/{" + BAR_ID_ARGUMENT + "}?productId={" + CUSTOMER_PRODUCT_ARGUMENT + "}"
    const val CUSTOMER_BAR_MAP = "customer/bar-map"
    const val CUSTOMER_BAR_MAP_ROUTE = CUSTOMER_BAR_MAP + "/{" + BAR_ID_ARGUMENT + "}"
    const val CUSTOMER_SEARCH_RESULTS_ROUTE =
        CUSTOMER_SEARCH_RESULTS + "?query={query}&productId={productId}&source={source}"


}

/**
 * App navigation. UX v18: a first-launch welcome, then two bottom tabs (검색, 내 정보) that
 * keep separate back stacks. The owner area lives in the 내 정보 tab.
 *
 * [devReviewScenario] and [resetWelcome] are honoured in debug builds only, so the mock
 * review scenarios and the welcome can be opened for UX review (see MainActivity).
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun BottleMapNavHost(devReviewScenario: String? = null, resetWelcome: Boolean = false) {
    val navController = rememberNavController()
    // Single Activity-scoped state shared by My Page, Login and restored sessions.
    val authViewModel: AuthViewModel = viewModel()
    val context = LocalContext.current
    val firstLaunch = remember { SharedPrefsFirstLaunchStore(context) }
    val startDestination = remember {
        if (BuildConfig.DEBUG && resetWelcome) firstLaunch.reset()
        if (BuildConfig.DEBUG && devReviewScenario != null) firstLaunch.markDone()
        if (firstLaunch.isDone()) variantStartDestination else TabRoutes.WELCOME
    }
    var toast by remember { mutableStateOf<Pair<Long, String>?>(null) }
    val showToast: (String) -> Unit = { toast = System.nanoTime() to it }
    LaunchedEffect(toast) {
        if (toast != null) {
            kotlinx.coroutines.delay(2500)
            toast = null
        }
    }
    LaunchedEffect(devReviewScenario) {
        if (BuildConfig.DEBUG && devReviewScenario != null) {
            navController.selectTab(MainTab.ACCOUNT)
            navController.navigate(TabRoutes.devPhotoReview(devReviewScenario))
        }
    }
    val backStackEntry by navController.currentBackStackEntryAsState()
    val destination = backStackEntry?.destination
    val imeVisible = WindowInsets.isImeVisible

    fun enterTabs(tab: MainTab) {
        firstLaunch.markDone()
        navController.navigate(TabRoutes.SEARCH_GRAPH) {
            popUpTo(navController.graph.id) { inclusive = true }
            launchSingleTop = true
        }
        if (tab == MainTab.ACCOUNT) navController.selectTab(MainTab.ACCOUNT)
    }
    fun continueAfterSignIn(origin: LoginOrigin) {
        when (origin) {
            LoginOrigin.WELCOME -> enterTabs(MainTab.SEARCH)
            LoginOrigin.OWNER -> {
                enterTabs(MainTab.ACCOUNT)
                navController.navigate(OwnerRoutes.GRAPH)
            }
            LoginOrigin.ACCOUNT -> navController.popBackStack(Routes.CUSTOMER_ACCOUNT, inclusive = false)
        }
    }

    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            Box(Modifier.weight(1f)) {
                NavHost(
                    navController = navController,
                    startDestination = startDestination,
                ) {
                    composable(TabRoutes.WELCOME) {
                        var ownerIntent by remember { mutableStateOf(false) }
                        val signIn = rememberGoogleSignInFlow(authViewModel) { outcome ->
                            val origin = if (ownerIntent) LoginOrigin.OWNER else LoginOrigin.WELCOME
                            when (outcome) {
                                SignInOutcome.SUCCESS -> {
                                    showToast("로그인했어요.")
                                    continueAfterSignIn(origin)
                                }
                                SignInOutcome.CANCELLED -> showToast("로그인을 취소했어요.")
                                SignInOutcome.FAILED -> navController.navigate(TabRoutes.loginError(origin))
                            }
                        }
                        val state = authViewModel.state.collectAsStateWithLifecycle().value
                        WelcomeScreen(
                            onBrowseAsGuest = { enterTabs(MainTab.SEARCH) },
                            onGoogle = {
                                ownerIntent = false
                                signIn()
                            },
                            onOwner = {
                                if (state is AuthUiState.SignedIn) continueAfterSignIn(LoginOrigin.OWNER)
                                else {
                                    ownerIntent = true
                                    signIn()
                                }
                            },
                            busy = state is AuthUiState.SigningIn,
                        )
                    }
                    composable(
                        TabRoutes.LOGIN_ERROR,
                        arguments = listOf(navArgument("origin") { type = NavType.StringType }),
                    ) { entry ->
                        val origin = LoginOrigin.entries.firstOrNull {
                            it.name.lowercase() == entry.arguments?.getString("origin")
                        } ?: LoginOrigin.ACCOUNT
                        val signIn = rememberGoogleSignInFlow(authViewModel) { outcome ->
                            when (outcome) {
                                SignInOutcome.SUCCESS -> {
                                    showToast("로그인했어요.")
                                    continueAfterSignIn(origin)
                                }
                                SignInOutcome.CANCELLED -> {
                                    showToast("로그인을 취소했어요.")
                                    navController.popBackStack()
                                }
                                SignInOutcome.FAILED -> Unit
                            }
                        }
                        val state = authViewModel.state.collectAsStateWithLifecycle().value
                        LoginErrorScreen(
                            title = "Google 로그인에 실패했어요.",
                            onBack = { if (navController.currentDestination?.route == TabRoutes.LOGIN_ERROR) navController.popBackStack() },
                            onRetry = signIn,
                            onBrowseAsGuest = {
                                authViewModel.continueAsGuest()
                                if (origin == LoginOrigin.ACCOUNT) {
                                    navController.popBackStack()
                                    navController.selectTab(MainTab.SEARCH)
                                } else enterTabs(MainTab.SEARCH)
                            },
                            busy = state is AuthUiState.SigningIn,
                        )
                    }
                    customerGraph(
                        navController = navController,
                        onOpenNearby = {
                            if (navController.currentDestination?.route == Routes.CUSTOMER_SEARCH)
                                navController.navigate(Routes.CUSTOMER_NEARBY) { launchSingleTop = true }
                        },
                        onOpenResults = { query, source ->
                            if (navController.currentDestination?.route == Routes.CUSTOMER_SEARCH)
                                navController.navigate(
                                    Routes.CUSTOMER_SEARCH_RESULTS + "?query=" + Uri.encode(query) +
                                        "&productId=&source=" + Uri.encode(source)
                                ) { launchSingleTop = true }
                        },
                        onOpenProduct = { productId ->
                            if (navController.currentDestination?.route == Routes.CUSTOMER_SEARCH)
                                navController.navigate(
                                    Routes.CUSTOMER_SEARCH_RESULTS + "?query=&productId=" +
                                        Uri.encode(productId) + "&source=popular"
                                ) { launchSingleTop = true }
                        },
                        onBack = { navController.popBackStack() },
                        onInvalidQuery = { fieldCode ->
                            navController.getBackStackEntry(Routes.CUSTOMER_SEARCH)
                                .savedStateHandle[SEARCH_VALIDATION_ERROR_KEY] = fieldCode
                            navController.popBackStack()
                        },
                        onOpenBarDetail = { barId, productId ->
                            // Ignore stale events from a destination already leaving the back stack.
                            if (navController.currentDestination?.route in setOf(
                                    Routes.CUSTOMER_SEARCH_RESULTS_ROUTE, Routes.CUSTOMER_NEARBY
                                )) {
                                navController.navigate("customer/bar-detail/" + Uri.encode(barId) +
                                    "?productId=" + Uri.encode(productId.orEmpty())) {
                                    launchSingleTop = true
                                }
                            }
                        },
                        onOpenBarMap = { barId ->
                            navController.navigate(Routes.CUSTOMER_BAR_MAP + "/" + Uri.encode(barId))
                        },
                        onMissingBarReturn = {
                            navController.previousBackStackEntry?.savedStateHandle
                                ?.set(REFRESH_AFTER_MISSING_BAR_KEY, true)
                            navController.popBackStack()
                        },
                    )
                    accountGraph(navController, authViewModel, showToast)
                }
            }
            if (showsBottomTabs(destination?.route) && !imeVisible) {
                BottomTabs(selectedTab(destination)) { tab -> navController.selectTab(tab) }
            }
        }
        toast?.let { (_, message) -> UxToast(message, Modifier.align(Alignment.TopCenter)) }
    }
}

/** 내 정보 tab: the existing My Page, the existing login route and the whole owner area. */
private fun NavGraphBuilder.accountGraph(
    navController: NavHostController,
    authViewModel: AuthViewModel,
    showToast: (String) -> Unit,
) {
    navigation(route = TabRoutes.ACCOUNT_GRAPH, startDestination = Routes.CUSTOMER_ACCOUNT) {
        composable(Routes.CUSTOMER_ACCOUNT) {
            val state = authViewModel.state.collectAsStateWithLifecycle().value
            val signIn = rememberGoogleSignInFlow(authViewModel) { outcome ->
                when (outcome) {
                    SignInOutcome.SUCCESS -> showToast("로그인했어요.")
                    SignInOutcome.CANCELLED -> showToast("로그인을 취소했어요.")
                    SignInOutcome.FAILED -> navController.navigate(TabRoutes.loginError(LoginOrigin.ACCOUNT))
                }
            }
            AccountScreen(
                state = state,
                onBack = { navController.selectTab(MainTab.SEARCH) },
                // One tap opens Google account selection; no separate login screen (UX v18).
                onOpenLogin = { if (navController.currentDestination?.route == Routes.CUSTOMER_ACCOUNT) signIn() },
                onLogout = {
                    authViewModel.logout()
                    showToast("로그아웃했어요.")
                },
                onRetryAccount = authViewModel::retryAccountSync,
                onOpenOwner = { navController.navigate(OwnerRoutes.GRAPH) },
            )
        }
        composable(Routes.CUSTOMER_LOGIN) {
            val state = authViewModel.state.collectAsStateWithLifecycle().value
            LaunchedEffect(state) {
                if (state is AuthUiState.SignedIn) navController.popBackStack()
            }
            GoogleLoginScreen(
                state = state,
                authViewModel = authViewModel,
                onBack = { if (navController.currentDestination?.route==Routes.CUSTOMER_LOGIN) navController.popBackStack() },
                onContinueGuest = {
                    authViewModel.continueAsGuest()
                    navController.popBackStack()
                },
            )
        }
        registerVariantRoutes(navController)
        if (BuildConfig.DEBUG) {
            // MOCK ONLY: v18 photo-review scenarios, opened from MainActivity's debug extra.
            composable(
                TabRoutes.DEV_PHOTO_REVIEW,
                arguments = listOf(navArgument("scenario") { type = NavType.StringType }),
            ) { entry ->
                val scenario = MockPhotoReviewScenario.fromId(entry.arguments?.getString("scenario"))
                    ?: MockPhotoReviewScenario.BASIC
                val vm: PhotoReviewViewModel = viewModel(
                    factory = PhotoReviewViewModel.Factory(MockPhotoReviewRepository(scenario)))
                PhotoReviewScreen(
                    vm = vm,
                    initialFocusItemId = scenario.focusItemId,
                    onLeave = {
                        // In-app preview returns to the *same* menu-management entry.
                        // An adb-launched mock route has no menu parent, so route there.
                        if (navController.previousBackStackEntry?.destination?.route ==
                            OwnerPage.MGR_MENU.route) {
                            navController.popBackStack()
                        } else {
                            navController.navigate(OwnerPage.MGR_MENU.route) {
                                popUpTo(TabRoutes.DEV_PHOTO_REVIEW) { inclusive = true }
                                launchSingleTop = true
                            }
                        }
                    },
                )
            }
        }
    }
}

private fun NavGraphBuilder.customerGraph(
    navController: NavHostController,
    onOpenNearby: () -> Unit,
    onOpenResults: (String, String) -> Unit,
    onOpenProduct: (String) -> Unit,
    onBack: () -> Unit,
    onInvalidQuery: (String) -> Unit,
    onOpenBarDetail: (String, String?) -> Unit,
    onOpenBarMap: (String) -> Unit,
    onMissingBarReturn: () -> Unit,
) {
    navigation(
        route = Routes.CUSTOMER_GRAPH,
        startDestination = Routes.CUSTOMER_SEARCH,
    ) {
        composable(Routes.CUSTOMER_SEARCH) { backStackEntry ->
            val refreshPopular=backStackEntry.savedStateHandle
                .getStateFlow(REFRESH_AFTER_MISSING_PRODUCT_KEY,false)
                .collectAsStateWithLifecycle().value
            CustomerP18Home(
                refreshAfterMissingProduct=refreshPopular,
                onMissingProductRefreshConsumed={
                    backStackEntry.savedStateHandle[REFRESH_AFTER_MISSING_PRODUCT_KEY]=false
                },
                onSearch = onOpenResults,
                onPopular = onOpenProduct,
                // The 내 정보 bottom tab replaces the header account entry.
                onAccount = null,
                onMap = onOpenNearby,
            )
        }
        composable(Routes.CUSTOMER_NEARBY) {
            com.zerotoone.bottlemap.ui.customer.CustomerP18Explore(
                onBack={ if (navController.currentDestination?.route==Routes.CUSTOMER_NEARBY) onBack() },
                onOpenBar={id->onOpenBarDetail(id,null)},
            )
        }
        composable(
            route = Routes.CUSTOMER_SEARCH_RESULTS_ROUTE,
            arguments = listOf(
                navArgument(Routes.CUSTOMER_QUERY_ARGUMENT) {
                    type = NavType.StringType
                    defaultValue = ""
                },
                navArgument(Routes.CUSTOMER_PRODUCT_ARGUMENT) {
                    type = NavType.StringType
                    defaultValue = ""
                },
                navArgument(Routes.CUSTOMER_SOURCE_ARGUMENT) {
                    type = NavType.StringType
                    defaultValue = "input"
                },
            ),
        ) { entry ->
            val refreshMissingBar=entry.savedStateHandle
                .getStateFlow(REFRESH_AFTER_MISSING_BAR_KEY,false)
                .collectAsStateWithLifecycle().value
            CustomerP18Results(
                refreshAfterMissingBar=refreshMissingBar,
                onMissingBarRefreshConsumed={
                    entry.savedStateHandle[REFRESH_AFTER_MISSING_BAR_KEY]=false
                },
                onMissingProduct={
                    navController.getBackStackEntry(Routes.CUSTOMER_SEARCH)
                        .savedStateHandle[REFRESH_AFTER_MISSING_PRODUCT_KEY]=true
                },
                initialQuery = entry.arguments?.getString(Routes.CUSTOMER_QUERY_ARGUMENT)
                    ?.takeIf { it.isNotBlank() },
                initialProductId = entry.arguments?.getString(Routes.CUSTOMER_PRODUCT_ARGUMENT)
                    ?.takeIf { it.isNotBlank() },
                source = entry.arguments?.getString(Routes.CUSTOMER_SOURCE_ARGUMENT) ?: "input",
                onBack = { if (navController.currentDestination?.route==Routes.CUSTOMER_SEARCH_RESULTS_ROUTE) onBack() },
                onOpenBar = onOpenBarDetail,
                onSearchAgain = { updated ->
                    if (navController.currentDestination?.route==Routes.CUSTOMER_SEARCH_RESULTS_ROUTE) {
                        navController.navigate(Routes.CUSTOMER_SEARCH_RESULTS +
                            "?query=" + Uri.encode(updated) + "&productId=&source=input") {
                            popUpTo(Routes.CUSTOMER_SEARCH_RESULTS_ROUTE) { inclusive = true }
                            launchSingleTop = true
                        }
                    }
                },
            )
        }
        composable(
            route = Routes.CUSTOMER_BAR_DETAIL_ROUTE,
            arguments = listOf(
                navArgument(Routes.BAR_ID_ARGUMENT) { type = NavType.StringType },
                navArgument(Routes.CUSTOMER_PRODUCT_ARGUMENT) {
                    type = NavType.StringType
                    defaultValue = ""
                },
            ),
        ) { backStackEntry ->
            BarDetailScreen(
                barId = backStackEntry.arguments?.getString(Routes.BAR_ID_ARGUMENT).orEmpty(),
                onBack = { if(navController.currentDestination?.route==Routes.CUSTOMER_BAR_DETAIL_ROUTE) onBack() },
                onBackAndRefreshResults = { if(navController.currentDestination?.route==Routes.CUSTOMER_BAR_DETAIL_ROUTE)
                    onMissingBarReturn() },
                onOpenMap = onOpenBarMap,
                highlightProductId = backStackEntry.arguments
                    ?.getString(Routes.CUSTOMER_PRODUCT_ARGUMENT)?.takeIf {it.isNotBlank()},
            )
        }
        composable(
            route = Routes.CUSTOMER_BAR_MAP_ROUTE,
            arguments = listOf(navArgument(Routes.BAR_ID_ARGUMENT) {
                type = NavType.StringType
            }),
        ) { backStackEntry ->
            val barId = backStackEntry.arguments?.getString(Routes.BAR_ID_ARGUMENT).orEmpty()
            // previousBackStackEntry is NOT stable during animated pop:
            // when returning Map -> Detail it can briefly refer to Results.
            // Look up the actual detail destination by route, and verify its ID.
            val detailEntry = remember(backStackEntry, navController, barId) {
                runCatching {
                    navController.getBackStackEntry(Routes.CUSTOMER_BAR_DETAIL_ROUTE)
                }.getOrNull()?.takeIf { entry ->
                    entry.arguments?.getString(Routes.BAR_ID_ARGUMENT) == barId
                }
            }
            if (detailEntry != null) {
                val detailViewModel: BarDetailViewModel = viewModel(
                    viewModelStoreOwner = detailEntry,
                )
                // On process recreation the parent ViewModel can be new.
                // load() deduplicates the same barId, so a normal map visit
                // does not request bar detail again.
                androidx.compose.runtime.LaunchedEffect(barId) {
                    detailViewModel.load(barId)
                }
                val detailState = detailViewModel.state.collectAsStateWithLifecycle().value
                BarLocationMapScreen(
                    barId = barId,
                    detailState = detailState,
                    onBack = { if(navController.currentDestination?.route==Routes.CUSTOMER_BAR_MAP_ROUTE) onBack() },
                    onRetryDetail = detailViewModel::retry,
                )
            } else {
                // An orphan map destination is a real navigation error, not a
                // transient Loading state. Allow a brief transition to settle
                // before showing guidance; do not block Back navigation.
                DelayedLoading {
                    BarLocationMapScreen(
                        barId = barId,
                        detailState = com.zerotoone.bottlemap.ui.customer.BarDetailUiState.Error(
                            message = "바 상세에서 위치 보기를 다시 실행해 주세요.",
                            canRetry = false,
                        ),
                        onBack = onBack,
                        onRetryDetail = {},
                    )
                }
            }
        }
    }
}
