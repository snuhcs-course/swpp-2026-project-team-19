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
        var nowMs = 0L
        val cooldown = OwnerPreviewSwitchCooldown { nowMs }
        compose.setContent {
            nav = rememberNavController()
            NavHost(navController = nav, startDestination = "mypage") {
                composable("mypage") { Text("MY_PAGE") }
                composable(OwnerPage.MGR_HOME.route) {
                    Column {
                        Text("MANAGEMENT_HOME")
                        Button(onClick = { nav.openOwnerManagerPreviewSafely(cooldown) },
                            modifier = Modifier.testTag("go-preview")) {
                            Text("미리보기")
                        }
                    }
                }
                composable(OwnerPage.MGR_PREVIEW.route) {
                    Column {
                        Text("CUSTOMER_PREVIEW")
                        Button(onClick = { nav.returnToOwnerManagerSafely(cooldown) },
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
        // Returning too soon after entering preview is ignored.
        compose.onNodeWithTag("go-manage").performClick()
        compose.runOnIdle {
            assertEquals(OwnerPage.MGR_PREVIEW.route, nav.currentDestination?.route)
            nowMs = 499L
        }
        compose.onNodeWithTag("go-manage").performClick()
        compose.runOnIdle {
            assertEquals(OwnerPage.MGR_PREVIEW.route, nav.currentDestination?.route)
            nowMs = 500L
        }
        compose.onNodeWithTag("go-manage").performClick()
        compose.onNodeWithText("MANAGEMENT_HOME").assertIsDisplayed()
        compose.runOnIdle {
            // A stale callback from the preview must not pop the manager.
            assertFalse(nav.returnToOwnerManagerSafely(cooldown))
            assertEquals(OwnerPage.MGR_HOME.route, nav.currentDestination?.route)
        }

        // The reverse direction also shares the 500-ms window.
        compose.onNodeWithTag("go-preview").performClick()
        compose.runOnIdle {
            assertEquals(OwnerPage.MGR_HOME.route, nav.currentDestination?.route)
            nowMs = 999L
        }
        compose.onNodeWithTag("go-preview").performClick()
        compose.runOnIdle {
            assertEquals(OwnerPage.MGR_HOME.route, nav.currentDestination?.route)
            nowMs = 1000L
        }
        compose.onNodeWithTag("go-preview").performClick()
        compose.onNodeWithText("CUSTOMER_PREVIEW").assertIsDisplayed()
        compose.runOnIdle {
            assertFalse(nav.openOwnerManagerPreviewSafely(cooldown))
            assertEquals(OwnerPage.MGR_PREVIEW.route, nav.currentDestination?.route)
        }
    }
}
