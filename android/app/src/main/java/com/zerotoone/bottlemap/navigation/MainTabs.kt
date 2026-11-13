package com.zerotoone.bottlemap.navigation

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.navigation.NavDestination
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavHostController
import com.zerotoone.bottlemap.ui.common.BmLineIcon
import com.zerotoone.bottlemap.ui.common.BmLineIconId
import com.zerotoone.bottlemap.ui.common.UxColor
import com.zerotoone.bottlemap.ui.common.quietClick
import com.zerotoone.bottlemap.ui.common.uxText

/** The two bottom tabs of UX v18. Each tab is a nested graph with its own back stack. */
enum class MainTab(val graphRoute: String, val label: String, val icon: BmLineIconId) {
    SEARCH(TabRoutes.SEARCH_GRAPH, "검색", BmLineIconId.SEARCH),
    ACCOUNT(TabRoutes.ACCOUNT_GRAPH, "내 정보", BmLineIconId.USER),
}

object TabRoutes {
    const val SEARCH_GRAPH = "customer"
    const val ACCOUNT_GRAPH = "account-tab"
    /** The search tab's root screen; the one destination never popped by a tab switch. */
    const val SEARCH_HOME = "customer/search"
    const val WELCOME = "welcome"
    const val LOGIN_ERROR = "auth/login-error/{origin}"
    const val DEV_PHOTO_REVIEW = "dev/photo-review/{scenario}"
    fun loginError(origin: LoginOrigin) = "auth/login-error/" + origin.name.lowercase()
    fun devPhotoReview(scenario: String) = "dev/photo-review/$scenario"
}

/** Where a Google sign-in was started, so a retry continues to the same place. */
enum class LoginOrigin { WELCOME, OWNER, ACCOUNT }

/**
 * Routes that hide the bottom tabs: first launch, full-screen sign-in, and the whole
 * add-menu-by-photo flow (photo selection, AI processing, review).
 */
internal val routesWithoutTabs: Set<String> = setOf(
    TabRoutes.WELCOME,
    TabRoutes.LOGIN_ERROR,
    TabRoutes.DEV_PHOTO_REVIEW,
    "customer/login",
    OwnerPage.MGR_PHOTO.route,
    OwnerPage.MGR_JOB.route,
    OwnerPage.MGR_REVIEW.route,
    OwnerRoutes.LEGACY_UPLOAD,
    OwnerRoutes.LEGACY_REVIEW,
)

internal fun showsBottomTabs(route: String?): Boolean = route != null && route !in routesWithoutTabs

internal fun selectedTab(destination: NavDestination?): MainTab =
    if (destination?.hierarchy?.any { it.route == TabRoutes.ACCOUNT_GRAPH } == true) MainTab.ACCOUNT else MainTab.SEARCH

/**
 * Switches tabs keeping each tab's back stack: the stack being left is saved and the other
 * tab's saved stack is restored (e.g. 메뉴 관리 stays open under 내 정보).
 */
internal fun NavHostController.selectTab(tab: MainTab) {
    navigate(tab.graphRoute) {
        popUpTo(TabRoutes.SEARCH_HOME) { saveState = true }
        launchSingleTop = true
        restoreState = true
    }
}

/** `.bottom-nav`: 66dp, top divider, two equal tabs, gold when active. */
@Composable
internal fun BottomTabs(selected: MainTab, onSelect: (MainTab) -> Unit) {
    Row(
        Modifier.fillMaxWidth().height(66.dp).background(UxColor.bg)
            .drawBehind { drawLine(UxColor.line, Offset(0f, 0f), Offset(size.width, 0f), 1.dp.toPx()) }
            .testTag("bottom-tabs"),
    ) {
        MainTab.entries.forEach { tab ->
            val active = tab == selected
            val color = if (active) UxColor.gold else UxColor.muted
            Column(
                Modifier.weight(1f).fillMaxHeight()
                    .quietClick(role = Role.Tab) { onSelect(tab) }
                    .semantics { this.selected = active }
                    .testTag("bottom-tab-${tab.name.lowercase()}"),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(2.dp, Alignment.CenterVertically),
            ) {
                BmLineIcon(tab.icon, 21.dp, color)
                Text(tab.label, style = uxText(11f, 400, color))
            }
        }
    }
}
