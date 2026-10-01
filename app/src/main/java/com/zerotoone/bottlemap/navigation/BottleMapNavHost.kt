package com.zerotoone.bottlemap.navigation

import androidx.compose.runtime.Composable
import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navigation
import androidx.navigation.compose.rememberNavController
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

    const val OWNER_GRAPH = "owner"
    const val OWNER_MENU_UPLOAD = "owner/menu-upload"
    const val OWNER_EXTRACTION_REVIEW = "owner/extraction-review"
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
            onOpenResults = { navController.navigate(Routes.CUSTOMER_SEARCH_RESULTS) },
            onBack = { navController.popBackStack() },
        )

        ownerGraph(
            onOpenReview = { navController.navigate(Routes.OWNER_EXTRACTION_REVIEW) },
            onBack = { navController.popBackStack() },
        )
    }
}

private fun NavGraphBuilder.customerGraph(
    onOpenResults: () -> Unit,
    onBack: () -> Unit,
) {
    navigation(
        route = Routes.CUSTOMER_GRAPH,
        startDestination = Routes.CUSTOMER_SEARCH,
    ) {
        composable(Routes.CUSTOMER_SEARCH) {
            SearchScreen(onOpenResults = onOpenResults)
        }
        composable(Routes.CUSTOMER_SEARCH_RESULTS) {
            SearchResultsScreen(onBack = onBack)
        }
    }
}

private fun NavGraphBuilder.ownerGraph(
    onOpenReview: () -> Unit,
    onBack: () -> Unit,
) {
    navigation(
        route = Routes.OWNER_GRAPH,
        startDestination = Routes.OWNER_MENU_UPLOAD,
    ) {
        composable(Routes.OWNER_MENU_UPLOAD) {
            MenuUploadScreen(onOpenReview = onOpenReview)
        }
        composable(Routes.OWNER_EXTRACTION_REVIEW) {
            ExtractionReviewScreen(onBack = onBack)
        }
    }
}
