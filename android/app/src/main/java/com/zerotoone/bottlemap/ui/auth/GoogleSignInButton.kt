// AI-assisted implementation (2026-10-17, I2-P19/A5). Device verification pending.
package com.zerotoone.bottlemap.ui.auth

import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.platform.LocalContext
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import androidx.credentials.exceptions.GetCredentialException
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.zerotoone.bottlemap.BuildConfig
import java.security.MessageDigest
import java.security.SecureRandom
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/**
 * Google Credential Manager only obtains an ID token. The backend NEVER
 * validates that Google token directly; AuthViewModel sends it to Supabase.
 */
@Composable
internal fun GoogleSignInButton(
    viewModel: AuthViewModel,
    enabled: Boolean,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    // ViewModel survives Activity recreation; the selection coroutine does not.
    // Clear only the pending Credential Manager stage on Back/recreation.
    // Once the ID token reaches the ViewModel, its Supabase exchange continues
    // independently in viewModelScope.
    DisposableEffect(viewModel) {
        onDispose { viewModel.cancelCredentialSelectionIfPending() }
    }

    Button(
        enabled = enabled,
        onClick = {
            if (!viewModel.beginGoogleSignIn()) return@Button
            if (BuildConfig.GOOGLE_WEB_CLIENT_ID.isBlank()) {
                viewModel.googleFailed()
                return@Button
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
        },
    ) {
        Text("Google 계정으로 계속")
    }
}
