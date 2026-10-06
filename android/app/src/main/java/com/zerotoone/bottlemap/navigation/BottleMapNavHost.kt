package com.zerotoone.bottlemap.navigation

import android.net.Uri
import androidx.compose.runtime.Composable
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navigation
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.zerotoone.bottlemap.ui.customer.SearchResultsScreen
import com.zerotoone.bottlemap.ui.customer.SearchScreen
import com.zerotoone.bottlemap.ui.mode.ModeSelectionScreen
import com.zerotoone.bottlemap.ui.owner.ExtractionReviewScreen
import com.zerotoone.bottlemap.ui.owner.MenuUploadScreen

private object Routes {
    const val MODE_SELECTION = "mode-selection"

    const val CUSTOMER_GRAPH = "customer"
    const val CUSTOMER_SEARCH = "customer/search"
    const val CUSTOMER_SEARCH_RESULTS = "customer/search-results"
    const val CUSTOMER_QUERY_ARGUMENT = "query"
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
) {
    navigation(
        route = Routes.CUSTOMER_GRAPH,
        startDestination = Routes.CUSTOMER_SEARCH,
    ) {
        composable(Routes.CUSTOMER_SEARCH) {
            SearchScreen(onOpenResults = onOpenResults)
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
            SearchResultsScreen(
                query = backStackEntry.arguments
                    ?.getString(Routes.CUSTOMER_QUERY_ARGUMENT)
                    .orEmpty(),
                onBack = onBack,
            )
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
