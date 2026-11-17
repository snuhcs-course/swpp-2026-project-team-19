package com.zerotoone.bottlemap.navigation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OwnerNavigationContractTest {
    @Test fun expiredOwnerSessionUsesExistingLoginAndRecoverableErrorUsesAccountRetry() {
        assertEquals(OwnerAuthRecoveryAction.LOGIN,
            ownerAuthRecoveryAction(com.zerotoone.bottlemap.ui.auth.AuthUiState.Guest))
        assertEquals(OwnerAuthRecoveryAction.ACCOUNT_RETRY,
            ownerAuthRecoveryAction(com.zerotoone.bottlemap.ui.auth.AuthUiState.SignInError(
                "일시적인 연결 오류", canRetryProfile = true)))
        assertEquals(OwnerAuthRecoveryAction.WAIT,
            ownerAuthRecoveryAction(com.zerotoone.bottlemap.ui.auth.AuthUiState.Initializing))
        assertEquals(OwnerAuthRecoveryAction.WAIT,
            ownerAuthRecoveryAction(com.zerotoone.bottlemap.ui.auth.AuthUiState.SigningOut))
    }

    @Test fun unifiedBuildStillStartsWithCustomer() {
        assertEquals("customer", variantStartDestination)
        assertEquals("owner", OwnerRoutes.GRAPH)
    }

    @Test fun allOwnerPreviewRoutesAreUniqueAndNamed() {
        val pages = OwnerPage.entries
        assertEquals(pages.size, pages.map { it.route }.toSet().size)
        assertTrue(pages.all { it.route.startsWith("owner/ux/") && it.title.isNotBlank() })
    }

    @Test fun obsoleteMockUploadRoutesAreNotInTheActiveNavigationContract() {
        assertTrue(routesWithoutTabs.none {
            it.contains("menu-upload") || it.contains("extraction-review") ||
                it.contains("dev/photo-review")
        })
        assertEquals("customer", variantStartDestination)
    }

    @Test fun groupedRoutesIncludeHoursTagsPhotosAndReview() {
        OwnerFlowGroup.entries.forEach { group ->
            val first = OwnerPage.entries.first { it.group == group }
            assertEquals(first.route, OwnerRoutes.groupStart(group))
            assertTrue(OwnerPage.entries.any { it.group == group && it.next() == null })
        }
        assertTrue(OwnerPage.entries.any { it.htmlId == "photoEdit" })
        assertTrue(OwnerPage.entries.any { it.htmlId == "s13sum" })
        assertTrue(OwnerPage.entries.any { it.htmlId == "hours" })
        assertTrue(OwnerPage.entries.any { it.htmlId == "tags" })
    }
}
