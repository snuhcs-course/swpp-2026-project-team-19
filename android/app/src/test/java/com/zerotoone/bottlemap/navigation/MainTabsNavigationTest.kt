package com.zerotoone.bottlemap.navigation

import androidx.compose.material3.Text
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navigation
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * The two tabs keep separate back stacks (UX v18): the graph has the app's shape, with the
 * owner area nested in the 내 정보 tab, and switching uses the app's [selectTab].
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class MainTabsNavigationTest {
    @get:Rule val rule = createComposeRule()

    private lateinit var nav: NavHostController
    private val results = "customer/search-results"

    private fun setUp() {
        rule.setContent {
            nav = rememberNavController()
            NavHost(nav, startDestination = TabRoutes.SEARCH_GRAPH) {
                navigation(route = TabRoutes.SEARCH_GRAPH, startDestination = TabRoutes.SEARCH_HOME) {
                    composable(TabRoutes.SEARCH_HOME) { Text("home") }
                    composable(results) { Text("results") }
                }
                navigation(route = TabRoutes.ACCOUNT_GRAPH, startDestination = "customer/account") {
                    composable("customer/account") { Text("account") }
                    navigation(route = OwnerRoutes.GRAPH, startDestination = OwnerRoutes.ENTRY) {
                        composable(OwnerRoutes.ENTRY) { Text("owner") }
                        composable(OwnerPage.MGR_HOME.route) { Text("manager") }
                        composable(OwnerPage.MGR_MENU.route) { Text("menu") }
                        composable(OwnerPage.MGR_PHOTO.route) { Text("photo") }
                    }
                }
            }
        }
        rule.waitForIdle()
    }

    private fun route() = nav.currentDestination?.route

    private fun go(action: () -> Unit) {
        rule.runOnIdle(action)
        rule.waitForIdle()
    }

    @Test fun eachTabReturnsToWhereItWasLeft() {
        setUp()
        // 내 정보 -> 매장 관리 홈 -> 메뉴 관리
        go { nav.selectTab(MainTab.ACCOUNT) }
        go { nav.navigate(OwnerRoutes.GRAPH) }
        go { nav.navigate(OwnerPage.MGR_HOME.route) }
        go { nav.navigate(OwnerPage.MGR_MENU.route) }
        assertEquals(MainTab.ACCOUNT, selectedTab(nav.currentDestination))
        // 검색 -> 검색 결과
        go { nav.selectTab(MainTab.SEARCH) }
        assertEquals(TabRoutes.SEARCH_HOME, route())
        go { nav.navigate(results) }
        // 내 정보: back to 메뉴 관리
        go { nav.selectTab(MainTab.ACCOUNT) }
        assertEquals(OwnerPage.MGR_MENU.route, route())
        // 검색: back to 검색 결과
        go { nav.selectTab(MainTab.SEARCH) }
        assertEquals(results, route())
        assertEquals(MainTab.SEARCH, selectedTab(nav.currentDestination))
        // Back inside the restored account stack still walks its own history.
        go { nav.selectTab(MainTab.ACCOUNT) }
        go { nav.popBackStack() }
        assertEquals(OwnerPage.MGR_HOME.route, route())
    }

    @Test fun photoFlowAndSignInHideTheTabs() {
        assertFalse(showsBottomTabs(OwnerPage.MGR_PHOTO.route))
        assertFalse(showsBottomTabs(OwnerPage.MGR_JOB.route))
        assertFalse(showsBottomTabs(OwnerPage.MGR_REVIEW.route))
        assertFalse(showsBottomTabs(TabRoutes.WELCOME))
        assertFalse(showsBottomTabs(TabRoutes.LOGIN_ERROR))
        assertTrue(showsBottomTabs(TabRoutes.SEARCH_HOME))
        assertTrue(showsBottomTabs("customer/account"))
        assertTrue(showsBottomTabs(OwnerPage.MGR_MENU.route))
        assertTrue(showsBottomTabs(OwnerPage.MGR_HOME.route))
        assertTrue(showsBottomTabs(OwnerPage.MGR_STATUS.route))
        assertTrue(showsBottomTabs(OwnerRoutes.ENTRY))
    }
}
