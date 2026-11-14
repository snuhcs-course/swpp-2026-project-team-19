package com.zerotoone.bottlemap.ui.auth

import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.zerotoone.bottlemap.BuildConfig
import java.security.MessageDigest
import java.security.SecureRandom
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/**
 * Starts Google account selection with Credential Manager. Returns a function that opens
 * the system account picker at once (one tap, no extra login screen) and returns false when
 * the ViewModel refuses to start (already signing in, signed in or logging out).
 *
 * Google Credential Manager only obtains an ID token. The backend NEVER validates that
 * Google token directly; AuthViewModel sends it to Supabase.
 */
@Composable
internal fun rememberGoogleSignInLauncher(viewModel: AuthViewModel): () -> Boolean {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    // ViewModel survives Activity recreation; the selection coroutine does not.
    // Clear only the pending Credential Manager stage on Back/recreation.
    // Once the ID token reaches the ViewModel, its Supabase exchange continues
    // independently in viewModelScope.
    DisposableEffect(viewModel) {
        onDispose { viewModel.cancelCredentialSelectionIfPending() }
    }

    return launch@{
        if (!viewModel.beginGoogleSignIn()) return@launch false
        if (BuildConfig.GOOGLE_WEB_CLIENT_ID.isBlank()) {
            viewModel.googleFailed()
            return@launch true
        }

        scope.launch {
            val rawNonce = SecureRandom().let { random ->
                ByteArray(32).also(random::nextBytes)
                    .joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }
            }
            val hashedNonce = MessageDigest.getInstance("SHA-256")
                .digest(rawNonce.toByteArray(Charsets.UTF_8))
                .joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }

            val googleOption = GetGoogleIdOption.Builder()
                .setServerClientId(BuildConfig.GOOGLE_WEB_CLIENT_ID)
                .setNonce(hashedNonce)
                .setFilterByAuthorizedAccounts(false)
                .setAutoSelectEnabled(false)
                .build()

            try {
                val request = GetCredentialRequest.Builder()
                    .addCredentialOption(googleOption)
                    .build()
                val credential = CredentialManager.create(context)
                    .getCredential(context = context, request = request).credential
                if (credential is CustomCredential &&
                    credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL
                ) {
                    val googleToken = GoogleIdTokenCredential
                        .createFrom(credential.data).idToken
                    viewModel.acceptGoogleCredential(googleToken, rawNonce)
                } else {
                    viewModel.googleFailed()
                }
            } catch (cancelled: GetCredentialCancellationException) {
                viewModel.googleCancelled()
            } catch (cancelled: CancellationException) {
                viewModel.googleCancelled()
                throw cancelled
            } catch (_: GetCredentialException) {
                viewModel.googleFailed()
            } catch (_: Exception) {
                viewModel.googleFailed()
            }
        }
        true
    }
}

/** How one Google sign-in attempt ended, read from [AuthUiState]. */
enum class SignInOutcome { SUCCESS, CANCELLED, FAILED }

/** Null while the attempt is still running (selecting an account or loading the profile). */
internal fun signInOutcome(state: AuthUiState): SignInOutcome? = when (state) {
    is AuthUiState.SignedIn -> SignInOutcome.SUCCESS
    AuthUiState.Guest -> SignInOutcome.CANCELLED
    is AuthUiState.SignInError -> SignInOutcome.FAILED
    AuthUiState.Initializing, AuthUiState.SigningIn, AuthUiState.SigningOut -> null
}

/**
 * One-tap Google sign-in with its result: the returned function opens the account picker and
 * [onOutcome] runs once when that attempt ends. Tapping while already signed in reports
 * success without opening the picker.
 */
@Composable
internal fun rememberGoogleSignInFlow(viewModel: AuthViewModel, onOutcome: (SignInOutcome) -> Unit): () -> Unit {
    val launch = rememberGoogleSignInLauncher(viewModel)
    val state by viewModel.state.collectAsStateWithLifecycle()
    val latestOutcome by rememberUpdatedState(onOutcome)
    var awaiting by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(state, awaiting) {
        if (!awaiting) return@LaunchedEffect
        signInOutcome(state)?.let {
            awaiting = false
            latestOutcome(it)
        }
    }
    return {
        when {
            launch() -> awaiting = true
            viewModel.state.value is AuthUiState.SignedIn -> latestOutcome(SignInOutcome.SUCCESS)
        }
    }
}

@Composable
internal fun GoogleSignInButton(
    viewModel: AuthViewModel,
    enabled: Boolean,
) {
    val launch = rememberGoogleSignInLauncher(viewModel)
    Button(
        enabled = enabled,
        modifier = Modifier.fillMaxWidth().heightIn(min=56.dp)
            .testTag("customer-google-button"),
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = Color(0xFFC99D6B),
            contentColor = Color(0xFF211A14),
        ),
        onClick = { launch() },
    ) {
        Row(horizontalArrangement=Arrangement.spacedBy(10.dp),
            verticalAlignment=Alignment.CenterVertically) {
            Text("G",fontSize=23.sp,fontWeight=FontWeight.Bold,
                color=Color(0xFF4285F4))
            Text("Google 계정으로 계속",fontSize=16.sp,
                fontWeight=FontWeight.SemiBold,color=Color(0xFF211E1B))
        }
    }
}
