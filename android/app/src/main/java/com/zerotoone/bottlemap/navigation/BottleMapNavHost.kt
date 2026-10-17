// AI-generated with ChatGPT (Hojin Nam, 2026-10-06, PR #7, #15). Reviewed by Hojin Nam.
package com.zerotoone.bottlemap.navigation

import android.net.Uri
import androidx.compose.runtime.Composable
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navigation
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.zerotoone.bottlemap.ui.customer.BarDetailScreen
import com.zerotoone.bottlemap.ui.customer.BarDetailViewModel
import com.zerotoone.bottlemap.ui.customer.BarLocationMapScreen
import com.zerotoone.bottlemap.ui.customer.SearchResultsScreen
import com.zerotoone.bottlemap.ui.customer.SearchScreen
import com.zerotoone.bottlemap.ui.mode.ModeSelectionScreen
import com.zerotoone.bottlemap.ui.owner.ExtractionReviewScreen
import com.zerotoone.bottlemap.ui.owner.MenuUploadScreen

private const val SEARCH_VALIDATION_ERROR_KEY = "searchValidationErrorCode"
private const val REFRESH_AFTER_MISSING_BAR_KEY = "refreshAfterMissingBar"

private object Routes {
    const val MODE_SELECTION = "mode-selection"

    const val CUSTOMER_GRAPH = "customer"
    const val CUSTOMER_SEARCH = "customer/search"
    const val CUSTOMER_SEARCH_RESULTS = "customer/search-results"
    const val CUSTOMER_QUERY_ARGUMENT = "query"
    const val BAR_ID_ARGUMENT = "barId"
    const val CUSTOMER_BAR_DETAIL_ROUTE = "customer/bar-detail/{" + BAR_ID_ARGUMENT + "}"
    const val CUSTOMER_BAR_MAP = "customer/bar-map"
    const val CUSTOMER_BAR_MAP_ROUTE = CUSTOMER_BAR_MAP + "/{" + BAR_ID_ARGUMENT + "}"
    const val CUSTOMER_SEARCH_RESULTS_ROUTE =
        CUSTOMER_SEARCH_RESULTS + "?" + CUSTOMER_QUERY_ARGUMENT + "={" + CUSTOMER_QUERY_ARGUMENT + "}"

    const val OWNER_GRAPH = "owner"
    const val OWNER_MENU_UPLOAD = "owner/menu-upload"
    const val OWNER_EXTRACTION_REVIEW = "owner/extraction-review"
    const val MENU_IMPORT_ID_ARGUMENT = "menuImportId"
    const val OWNER_EXTRACTION_REVIEW_ROUTE =
        OWNER_EXTRACTION_REVIEW + "/{" + MENU_IMPORT_ID_ARGUMENT + "}"
}

@Composable
fun BottleMapNavHost() {
    val navController = rememberNavController()

    NavHost(
        navController = navController,
        startDestination = Routes.MODE_SELECTION,
    ) {
        composable(Routes.MODE_SELECTION) {
            ModeSelectionScreen(
                onCustomerSelected = { navController.navigate(Routes.CUSTOMER_GRAPH) },
                onOwnerSelected = { navController.navigate(Routes.OWNER_GRAPH) },
            )
        }

        customerGraph(
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

        ownerGraph(
            onOpenReview = { importId ->
                navController.navigate(
                    Routes.OWNER_EXTRACTION_REVIEW + "/" + Uri.encode(importId)
                )
            },
            onBack = { navController.popBackStack() },
        )
    }
}

private fun NavGraphBuilder.customerGraph(
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
            val validationErrorCode = backStackEntry.savedStateHandle
                .getStateFlow<String?>(SEARCH_VALIDATION_ERROR_KEY, null)
                .collectAsStateWithLifecycle().value
            SearchScreen(
                onOpenResults = onOpenResults,
                serverValidationErrorCode = validationErrorCode,
                onClearServerValidation = {
                    backStackEntry.savedStateHandle[SEARCH_VALIDATION_ERROR_KEY] = null
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
            // Reuse the Bar Detail entry's ViewModel. The published bar/coordinate
            // response is already loaded, so opening the map makes no duplicate API call.
            val parentEntry = navController.previousBackStackEntry
            val parentIsDetail = parentEntry?.destination?.route ==
                Routes.CUSTOMER_BAR_DETAIL_ROUTE
            if (parentIsDetail && parentEntry != null) {
                val detailViewModel: BarDetailViewModel = viewModel(
                    viewModelStoreOwner = parentEntry,
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
                // No fabricated state or API request when this internal-only
                // destination is opened without the Bar Detail back stack.
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

private fun NavGraphBuilder.ownerGraph(
    onOpenReview: (String) -> Unit,
    onBack: () -> Unit,
) {
    navigation(
        route = Routes.OWNER_GRAPH,
        startDestination = Routes.OWNER_MENU_UPLOAD,
    ) {
        composable(Routes.OWNER_MENU_UPLOAD) {
            MenuUploadScreen(onOpenReview = onOpenReview)
        }
        composable(
            route = Routes.OWNER_EXTRACTION_REVIEW_ROUTE,
            arguments = listOf(
                navArgument(Routes.MENU_IMPORT_ID_ARGUMENT) {
                    type = NavType.StringType
                },
            ),
        ) { backStackEntry ->
            ExtractionReviewScreen(
                menuImportId = backStackEntry.arguments
                    ?.getString(Routes.MENU_IMPORT_ID_ARGUMENT)
                    .orEmpty(),
                onBack = onBack,
            )
        }
    }
}
