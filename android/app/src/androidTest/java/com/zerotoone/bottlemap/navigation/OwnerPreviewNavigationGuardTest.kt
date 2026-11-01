package com.zerotoone.bottlemap.navigation

import androidx.activity.ComponentActivity
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Regression for rapid "미리보기 -> 관리 -> 미리보기" switching.
 * After the first return, a stale callback from the departing preview
 * must not pop the manager and expose the My Page destination beneath it.
 */
@RunWith(AndroidJUnit4::class)
class OwnerPreviewNavigationGuardTest {
    @get:Rule val compose = createAndroidComposeRule<ComponentActivity>()

    @Test fun staleManageClickCannotPopManagerOrSendUserBackToMyPage() {
        lateinit var nav: NavHostController
        compose.setContent {
            nav = rememberNavController()
            NavHost(navController = nav, startDestination = "mypage") {
                composable("mypage") { Text("MY_PAGE") }
                composable(OwnerPage.MGR_HOME.route) {
                    Column {
                        Text("MANAGEMENT_HOME")
                        Button(onClick = { nav.openOwnerManagerPreviewSafely() },
                            modifier = Modifier.testTag("go-preview")) {
                            Text("미리보기")
                        }
                    }
                }
                composable(OwnerPage.MGR_PREVIEW.route) {
                    Column {
                        Text("CUSTOMER_PREVIEW")
                        Button(onClick = { nav.returnToOwnerManagerSafely() },
                            modifier = Modifier.testTag("go-manage")) {
                            Text("관리")
                        }
                    }
                }
            }
        }
        compose.runOnIdle {
            nav.navigate(OwnerPage.MGR_HOME.route)
        }
        compose.onNodeWithTag("go-preview").performClick()
        compose.onNodeWithText("CUSTOMER_PREVIEW").assertIsDisplayed()
        compose.onNodeWithTag("go-manage").performClick()
        compose.runOnIdle {
            // This models a late second callback from the outgoing preview.
            assertFalse(nav.returnToOwnerManagerSafely())
            assertEquals(OwnerPage.MGR_HOME.route, nav.currentDestination?.route)
        }
        compose.onNodeWithTag("go-preview").performClick()
        compose.onNodeWithText("CUSTOMER_PREVIEW").assertIsDisplayed()
        compose.runOnIdle {
            assertFalse(nav.openOwnerManagerPreviewSafely())
            assertEquals(OwnerPage.MGR_PREVIEW.route, nav.currentDestination?.route)
        }
    }
}
