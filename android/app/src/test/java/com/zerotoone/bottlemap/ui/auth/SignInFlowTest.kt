package com.zerotoone.bottlemap.ui.auth

import com.zerotoone.bottlemap.network.CurrentUserDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** How the welcome and 내 정보 read the end of one Google sign-in attempt. */
class SignInFlowTest {
    @Test fun runningStatesHaveNoOutcomeYet() {
        assertNull(signInOutcome(AuthUiState.SigningIn))
        assertNull(signInOutcome(AuthUiState.Initializing))
    }

    @Test fun endStatesMapToSuccessCancelAndFailure() {
        val user = CurrentUserDto("u1", "owner@example.com", "Owner", "customer", "2026-11-13T00:00:00Z")
        assertEquals(SignInOutcome.SUCCESS, signInOutcome(AuthUiState.SignedIn(user)))
        assertEquals(SignInOutcome.CANCELLED, signInOutcome(AuthUiState.Guest))
        assertEquals(SignInOutcome.FAILED, signInOutcome(AuthUiState.SignInError("x")))
        assertEquals(SignInOutcome.FAILED, signInOutcome(AuthUiState.SignInError("x", canRetryProfile = true)))
    }
}
