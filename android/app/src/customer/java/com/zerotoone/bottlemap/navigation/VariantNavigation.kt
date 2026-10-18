// A12: Customer APK compiles no Owner destination or Owner implementation.
package com.zerotoone.bottlemap.navigation

import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavHostController

internal const val variantStartDestination = "customer"

@Suppress("UNUSED_PARAMETER")
internal fun NavGraphBuilder.registerVariantRoutes(navController: NavHostController) {
    // No Owner / role-selection destinations in the Customer navigation graph.
}
