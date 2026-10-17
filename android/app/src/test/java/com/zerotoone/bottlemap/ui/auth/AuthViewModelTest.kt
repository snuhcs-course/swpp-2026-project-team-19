// AI-assisted tests (2026-10-17, I2-P19/P20/A5). Run :app:testDebugUnitTest.
package com.zerotoone.bottlemap.ui.auth

import com.zerotoone.bottlemap.data.AuthGateway
import com.zerotoone.bottlemap.data.AuthSessionEvent
import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.network.CurrentUserDto
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AuthViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    @Before fun setup() {
        Dispatchers.setMain(dispatcher)
    }

    @After fun cleanup() {
        Dispatchers.resetMain()
    }

    @Test
    fun noSessionRestoresGuestInsteadOfShowingLoginGate() = runTest(dispatcher) {
        val fake = FakeAuthGateway()
        val vm = AuthViewModel(fake)
        assertEquals(AuthUiState.Initializing, vm.state.value)
        fake.events.value = AuthSessionEvent.Guest
        advanceUntilIdle()
        assertEquals(AuthUiState.Guest, vm.state.value)
    }

    @Test
    fun restoredSessionSyncsBackendUserAndBecomesSignedIn() = runTest(dispatcher) {
        val fake = FakeAuthGateway()
        fake.events.value = AuthSessionEvent.Authenticated
        val vm = AuthViewModel(fake)
        advanceUntilIdle()
        val signedIn = vm.state.value as AuthUiState.SignedIn
        assertEquals("user-1", signedIn.user.userId)
        assertEquals("customer", signedIn.user.userType)
        assertEquals(1, fake.meRequests)
    }

    @Test
    fun googleSuccessAndRepeatedClickGuard() = runTest(dispatcher) {
        val fake = FakeAuthGateway()
        val vm = AuthViewModel(fake)
        fake.events.value = AuthSessionEvent.Guest
        advanceUntilIdle()

        assertTrue(vm.beginGoogleSignIn())
        assertFalse(vm.beginGoogleSignIn())
        assertEquals(AuthUiState.SigningIn, vm.state.value)
        vm.acceptGoogleCredential("id-token-for-test-only", "raw-nonce")
        advanceUntilIdle()

        assertEquals(listOf("id-token-for-test-only" to "raw-nonce"), fake.signIns)
        assertTrue(vm.state.value is AuthUiState.SignedIn)
    }

    @Test
    fun googleCancelKeepsGuestAndAllowsRetry() = runTest(dispatcher) {
        val fake = FakeAuthGateway()
        val vm = AuthViewModel(fake)
        fake.events.value = AuthSessionEvent.Guest
        advanceUntilIdle()

        assertTrue(vm.beginGoogleSignIn())
        vm.googleCancelled()
        assertEquals(AuthUiState.Guest, vm.state.value)
        assertTrue(vm.beginGoogleSignIn())
    }

    @Test
    fun googleErrorThenContinueGuestDoesNotBlockSearch() = runTest(dispatcher) {
        val fake = FakeAuthGateway()
        val vm = AuthViewModel(fake)
        fake.events.value = AuthSessionEvent.Guest
        advanceUntilIdle()

        assertTrue(vm.beginGoogleSignIn())
        vm.googleFailed()
        assertTrue(vm.state.value is AuthUiState.SignInError)
        vm.continueAsGuest()
        advanceUntilIdle()
        assertEquals(AuthUiState.Guest, vm.state.value)
        assertEquals(1, fake.logouts)
    }

    @Test
    fun backendUnavailableShowsRetryWithoutDestroyingSession() = runTest(dispatcher) {
        val fake = FakeAuthGateway()
        fake.meError = BottleMapApiException(code = "SERVICE_UNAVAILABLE", message = "down")
        fake.events.value = AuthSessionEvent.Authenticated
        val vm = AuthViewModel(fake)
        advanceUntilIdle()
        val state = vm.state.value as AuthUiState.SignInError
        assertTrue(state.message.contains("서버"))
        assertEquals(0, fake.logouts)
        fake.meError = null
        vm.retryAccountSync()
        advanceUntilIdle()
        assertTrue(vm.state.value is AuthUiState.SignedIn)
    }

    @Test
    fun logoutTransitionsToGuestAndClearsGatewaySession() = runTest(dispatcher) {
        val fake = FakeAuthGateway()
        fake.events.value = AuthSessionEvent.Authenticated
        val vm = AuthViewModel(fake)
        advanceUntilIdle()
        assertTrue(vm.state.value is AuthUiState.SignedIn)

        vm.logout()
        advanceUntilIdle()
        assertEquals(AuthUiState.Guest, vm.state.value)
        assertEquals(1, fake.logouts)
    }

    @Test
    fun refreshPendingDoesNotClearExistingSignedInIdentity() = runTest(dispatcher) {
        val fake = FakeAuthGateway()
        fake.events.value = AuthSessionEvent.Authenticated
        val vm = AuthViewModel(fake)
        advanceUntilIdle()
        fake.events.value = AuthSessionEvent.Refreshing
        advanceUntilIdle()
        assertTrue(vm.state.value is AuthUiState.SignedIn)
    }

    @Test
    fun logoutImmediatelyHidesIdentityAndIgnoresLateUncancellableProfileResponse() = runTest(dispatcher) {
        val fake = FakeAuthGateway()
        val heldProfile = CompletableDeferred<CurrentUserDto>()
        fake.pendingProfile = heldProfile
        fake.events.value = AuthSessionEvent.Authenticated
        val vm = AuthViewModel(fake)
        advanceUntilIdle()
        assertEquals(AuthUiState.Initializing, vm.state.value)
        assertEquals(1, fake.meRequests)

        vm.logout()
        // Must not wait for the suspended GET /api/me to finish.
        assertEquals(AuthUiState.Guest, vm.state.value)
        heldProfile.complete(fake.user)
        advanceUntilIdle()
        assertEquals(AuthUiState.Guest, vm.state.value)
        assertEquals(1, fake.logouts)
    }

    @Test
    fun sdkGuestAfterProfileErrorExitsErrorInsteadOfRetryingWithoutSession() = runTest(dispatcher) {
        val fake = FakeAuthGateway()
        fake.meError = BottleMapApiException(code = "SERVICE_UNAVAILABLE", message = "temporary")
        fake.events.value = AuthSessionEvent.Authenticated
        val vm = AuthViewModel(fake)
        advanceUntilIdle()
        assertTrue((vm.state.value as AuthUiState.SignInError).canRetryProfile)

        // Supabase expired/revoked session later -> normal Guest, not stuck Error.
        fake.events.value = AuthSessionEvent.Guest
        advanceUntilIdle()
        assertEquals(AuthUiState.Guest, vm.state.value)
        vm.retryAccountSync()
        advanceUntilIdle()
        assertEquals(1, fake.meRequests)
    }

    @Test
    fun confirmedUnauthenticatedProfileClearsSessionAndReturnsGuest() = runTest(dispatcher) {
        val fake = FakeAuthGateway()
        fake.meError = BottleMapApiException(code = "UNAUTHENTICATED", message = "expired")
        fake.events.value = AuthSessionEvent.Authenticated
        val vm = AuthViewModel(fake)
        advanceUntilIdle()
        assertEquals(AuthUiState.Guest, vm.state.value)
        assertEquals(1, fake.logouts)
        vm.retryAccountSync() // No session; do not issue GET /api/me again.
        advanceUntilIdle()
        assertEquals(1, fake.meRequests)
    }

    @Test
    fun transientNetworkErrorKeepsSessionAndAllowsProfileRetry() = runTest(dispatcher) {
        val fake = FakeAuthGateway()
        fake.meError = BottleMapApiException(code = "NETWORK_ERROR", message = "offline")
        fake.events.value = AuthSessionEvent.Authenticated
        val vm = AuthViewModel(fake)
        advanceUntilIdle()
        assertTrue((vm.state.value as AuthUiState.SignInError).canRetryProfile)
        assertEquals(0, fake.logouts)

        fake.meError = null
        vm.retryAccountSync()
        advanceUntilIdle()
        assertTrue(vm.state.value is AuthUiState.SignedIn)
    }

    @Test
    fun leavingLoginWhileGoogleAccountChooserIsOpenResetsPendingAttempt() = runTest(dispatcher) {
        val fake = FakeAuthGateway()
        val vm = AuthViewModel(fake)
        fake.events.value = AuthSessionEvent.Guest
        advanceUntilIdle()
        assertTrue(vm.beginGoogleSignIn())

        vm.cancelCredentialSelectionIfPending() // Compose screen disposed.
        assertEquals(AuthUiState.Guest, vm.state.value)
        // A late Credential Manager callback must not exchange its token.
        vm.acceptGoogleCredential("late-token", "late-nonce")
        advanceUntilIdle()
        assertTrue(fake.signIns.isEmpty())
        assertTrue(vm.beginGoogleSignIn())
    }

    @Test
    fun leavingLoginAfterCredentialDeliveryDoesNotAbortSupabaseExchange() = runTest(dispatcher) {
        val fake = FakeAuthGateway()
        val vm = AuthViewModel(fake)
        fake.events.value = AuthSessionEvent.Guest
        advanceUntilIdle()
        assertTrue(vm.beginGoogleSignIn())
        vm.acceptGoogleCredential("google-id-token", "nonce")

        // Credential UI is gone, but token exchange now belongs to ViewModel.
        vm.cancelCredentialSelectionIfPending()
        assertEquals(AuthUiState.SigningIn, vm.state.value)
        advanceUntilIdle()
        assertEquals(listOf("google-id-token" to "nonce"), fake.signIns)
        assertTrue(vm.state.value is AuthUiState.SignedIn)
    }

    private class FakeAuthGateway : AuthGateway {
        override val events = MutableStateFlow<AuthSessionEvent>(AuthSessionEvent.Initializing)
        val signIns = mutableListOf<Pair<String, String>>()
        var logouts = 0
        var meRequests = 0
        var meError: BottleMapApiException? = null
        var pendingProfile: CompletableDeferred<CurrentUserDto>? = null
        val user = CurrentUserDto(
            userId = "user-1",
            email = "user@example.com",
            displayName = "Guest turned member",
            userType = "customer",
            updatedAt = "2026-10-17T09:00:00Z",
        )

        override suspend fun signInWithGoogleIdToken(idToken: String, rawNonce: String) {
            signIns += idToken to rawNonce
            events.value = AuthSessionEvent.Authenticated
        }

        override suspend fun fetchCurrentUser(): CurrentUserDto {
            meRequests++
            meError?.let { throw it }
            // Deliberately simulate an uncancellable network callback to
            // verify stale UI responses cannot revive the logged-out identity.
            return pendingProfile?.let { pending ->
                withContext(NonCancellable) { pending.await() }
            } ?: user
        }

        override suspend fun logout() {
            logouts++
            events.value = AuthSessionEvent.Guest
        }
    }
}
