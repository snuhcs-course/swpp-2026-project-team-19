// A13: existing P10 developer entry and Owner flows preserved in developer only.
package com.zerotoone.bottlemap.navigation

import android.net.Uri
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navigation
import androidx.navigation.navArgument
import com.zerotoone.bottlemap.ui.mode.ModeSelectionScreen
import com.zerotoone.bottlemap.ui.owner.ExtractionReviewScreen
import com.zerotoone.bottlemap.ui.owner.MenuUploadScreen

internal const val variantStartDestination = "mode-selection"

internal fun NavGraphBuilder.registerVariantRoutes(navController: NavHostController) {
    composable("mode-selection") {
        ModeSelectionScreen(
            onCustomerSelected = { navController.navigate("customer") },
            onOwnerSelected = { navController.navigate("owner") },
        )
    }
    navigation(route = "owner", startDestination = "owner/menu-upload") {
        composable("owner/menu-upload") {
            MenuUploadScreen(
                onOpenReview = { importId ->
                    navController.navigate("owner/extraction-review/" + Uri.encode(importId))
                },
            )
        }
        composable(
            route = "owner/extraction-review/{menuImportId}",
            arguments = listOf(navArgument("menuImportId") { type = NavType.StringType }),
        ) { backStackEntry ->
            ExtractionReviewScreen(
                menuImportId = backStackEntry.arguments?.getString("menuImportId").orEmpty(),
                onBack = { navController.popBackStack() },
            )
        }
    }
}
