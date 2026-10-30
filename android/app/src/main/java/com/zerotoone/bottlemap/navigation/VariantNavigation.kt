package com.zerotoone.bottlemap.navigation

import android.net.Uri
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
import com.zerotoone.bottlemap.ui.owner.OwnerEntryScreen
import com.zerotoone.bottlemap.ui.owner.OwnerSkeletonScreen

/** One Android artifact: everyone starts in Customer, with Owner accessible from My Page. */
internal const val variantStartDestination = "customer"

internal fun NavGraphBuilder.registerVariantRoutes(navController: NavHostController) {
    navigation(route = OwnerRoutes.GRAPH, startDestination = OwnerRoutes.ENTRY) {
        composable(OwnerRoutes.ENTRY) {
            val data: OwnerMockViewModel = viewModel(factory = OwnerMockViewModel.Factory(
                OwnerMockRuntime.repository(LocalContext.current)))
            val mockState = data.state.collectAsStateWithLifecycle().value
            OwnerEntryScreen(
                mockState = mockState,
                onRetry = data::retry,
                onBack = { navController.popBackStack() },
                onOpenGroup = { group -> navController.navigate(OwnerRoutes.groupStart(group)) },
                onComponents = { navController.navigate(OwnerRoutes.COMPONENTS) },
            )
        }
        composable(OwnerRoutes.COMPONENTS) {
            OwnerComponentGallery(onBack = { navController.popBackStack() })
        }
        OwnerPage.entries.forEach { page ->
            composable(page.route) {
                val data: OwnerMockViewModel = viewModel(factory = OwnerMockViewModel.Factory(
                    OwnerMockRuntime.repository(LocalContext.current)))
                val mockState = data.state.collectAsStateWithLifecycle().value
                OwnerSkeletonScreen(
                    page = page,
                    mockState = mockState,
                    onBack = { navController.popBackStack() },
                    onNavigate = { next -> navController.navigate(next.route) },
                    onHome = {
                        navController.popBackStack(OwnerRoutes.ENTRY, inclusive = false)
                    },
                )
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
