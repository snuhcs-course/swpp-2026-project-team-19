// AI-generated with ChatGPT (Hojin Nam, 2026-10-06, PR #7, #15). Reviewed by Hojin Nam.
// AI-assisted with ChatGPT/GPT-6 (Hojin Nam, 2026-10-18, PR #38). Human review pending.
package com.zerotoone.bottlemap.navigation

import android.net.Uri
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
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
import com.zerotoone.bottlemap.ui.customer.SearchResultsScreen
import com.zerotoone.bottlemap.ui.customer.SearchScreen
import com.zerotoone.bottlemap.ui.customer.NearbyBarsScreen
import com.zerotoone.bottlemap.ui.customer.nearbyBarsViewModel
import com.zerotoone.bottlemap.ui.common.DelayedLoading

private const val SEARCH_VALIDATION_ERROR_KEY = "searchValidationErrorCode"
private const val REFRESH_AFTER_MISSING_BAR_KEY = "refreshAfterMissingBar"

private object Routes {
    const val CUSTOMER_GRAPH = "customer"
    const val CUSTOMER_SEARCH = "customer/search"
    const val CUSTOMER_NEARBY = "customer/nearby"
    const val CUSTOMER_ACCOUNT = "customer/account"
    const val CUSTOMER_LOGIN = "customer/login"
    const val CUSTOMER_SEARCH_RESULTS = "customer/search-results"
    const val CUSTOMER_QUERY_ARGUMENT = "query"
    const val BAR_ID_ARGUMENT = "barId"
    const val CUSTOMER_BAR_DETAIL_ROUTE = "customer/bar-detail/{" + BAR_ID_ARGUMENT + "}"
    const val CUSTOMER_BAR_MAP = "customer/bar-map"
    const val CUSTOMER_BAR_MAP_ROUTE = CUSTOMER_BAR_MAP + "/{" + BAR_ID_ARGUMENT + "}"
    const val CUSTOMER_SEARCH_RESULTS_ROUTE =
        CUSTOMER_SEARCH_RESULTS + "?" + CUSTOMER_QUERY_ARGUMENT + "={" + CUSTOMER_QUERY_ARGUMENT + "}"


}

@Composable
fun BottleMapNavHost() {
    val navController = rememberNavController()
    // Single Activity-scoped state shared by My Page, Login and restored sessions.
    val authViewModel: AuthViewModel = viewModel()

    NavHost(
        navController = navController,
        startDestination = variantStartDestination,
    ) {
        customerGraph(
            navController = navController,
            authViewModel = authViewModel,
            onOpenAccount = { navController.navigate(Routes.CUSTOMER_ACCOUNT) },
            onOpenNearby = { navController.navigate(Routes.CUSTOMER_NEARBY) },
            onOpenResults = { query ->
                val encodedQuery = Uri.encode(query)
                navController.navigate(
                    Routes.CUSTOMER_SEARCH_RESULTS + "?" +
                        Routes.CUSTOMER_QUERY_ARGUMENT + "=" + encodedQuery,
                )
            },
            onBack = { navController.popBackStack() },
            onInvalidQuery = { fieldCode ->
                navController.getBackStackEntry(Routes.CUSTOMER_SEARCH)
                    .savedStateHandle[SEARCH_VALIDATION_ERROR_KEY] = fieldCode
                navController.popBackStack()
            },
            onOpenBarDetail = { barId ->
                navController.navigate("customer/bar-detail/" + Uri.encode(barId))
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

        registerVariantRoutes(navController)
    }
}

private fun NavGraphBuilder.customerGraph(
    navController: NavHostController,
    authViewModel: AuthViewModel,
    onOpenAccount: () -> Unit,
    onOpenNearby: () -> Unit,
    onOpenResults: (String) -> Unit,
    onBack: () -> Unit,
    onInvalidQuery: (String) -> Unit,
    onOpenBarDetail: (String) -> Unit,
    onOpenBarMap: (String) -> Unit,
    onMissingBarReturn: () -> Unit,
) {
    navigation(
        route = Routes.CUSTOMER_GRAPH,
        startDestination = Routes.CUSTOMER_SEARCH,
    ) {
        composable(Routes.CUSTOMER_SEARCH) { backStackEntry ->
            val nearbyOwner = remember(backStackEntry, navController) {
                navController.getBackStackEntry(Routes.CUSTOMER_GRAPH)
            }
            val nearbyViewModel = nearbyBarsViewModel(nearbyOwner)
            val validationErrorCode = backStackEntry.savedStateHandle
                .getStateFlow<String?>(SEARCH_VALIDATION_ERROR_KEY, null)
                .collectAsStateWithLifecycle().value
            SearchScreen(
                onOpenResults = onOpenResults,
                onOpenAccount = onOpenAccount,
                onOpenNearby = onOpenNearby,
                nearbyViewModel = nearbyViewModel,
                serverValidationErrorCode = validationErrorCode,
                onClearServerValidation = {
                    backStackEntry.savedStateHandle[SEARCH_VALIDATION_ERROR_KEY] = null
                },
            )
        }
        composable(Routes.CUSTOMER_NEARBY) { backStackEntry ->
            val nearbyOwner = remember(backStackEntry, navController) {
                navController.getBackStackEntry(Routes.CUSTOMER_GRAPH)
            }
            NearbyBarsScreen(
                onBack = onBack,
                onOpenBarDetail = onOpenBarDetail,
                viewModel = nearbyBarsViewModel(nearbyOwner),
            )
        }
        composable(Routes.CUSTOMER_ACCOUNT) {
            val state = authViewModel.state.collectAsStateWithLifecycle().value
            AccountScreen(
                state = state,
                onBack = onBack,
                onOpenLogin = { navController.navigate(Routes.CUSTOMER_LOGIN) },
                onLogout = authViewModel::logout,
                onRetryAccount = authViewModel::retryAccountSync,
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
                onBack = onBack,
                onContinueGuest = {
                    authViewModel.continueAsGuest()
                    navController.popBackStack()
                },
            )
        }
        composable(
            route = Routes.CUSTOMER_SEARCH_RESULTS_ROUTE,
            arguments = listOf(
                navArgument(Routes.CUSTOMER_QUERY_ARGUMENT) {
                    type = NavType.StringType
                    defaultValue = ""
                },
            ),
        ) { backStackEntry ->
            val refreshAfterMissingBar = backStackEntry.savedStateHandle
                .getStateFlow(REFRESH_AFTER_MISSING_BAR_KEY, false)
                .collectAsStateWithLifecycle().value
            SearchResultsScreen(
                refreshAfterMissingBar = refreshAfterMissingBar,
                onRefreshHandled = {
                    backStackEntry.savedStateHandle[REFRESH_AFTER_MISSING_BAR_KEY] = false
                },
                query = backStackEntry.arguments
                    ?.getString(Routes.CUSTOMER_QUERY_ARGUMENT)
                    .orEmpty(),
                onBack = onBack,
                onInvalidQuery = onInvalidQuery,
                onOpenBarDetail = onOpenBarDetail,
            )
        }
        composable(
            route = Routes.CUSTOMER_BAR_DETAIL_ROUTE,
            arguments = listOf(navArgument(Routes.BAR_ID_ARGUMENT) {
                type = NavType.StringType
            }),
        ) { backStackEntry ->
            BarDetailScreen(
                barId = backStackEntry.arguments?.getString(Routes.BAR_ID_ARGUMENT).orEmpty(),
                onBack = onBack,
                onBackAndRefreshResults = onMissingBarReturn,
                onOpenMap = onOpenBarMap,
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
                    onBack = onBack,
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
