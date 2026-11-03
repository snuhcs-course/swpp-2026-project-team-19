package com.zerotoone.bottlemap.ui.owner

import android.content.Context
import android.net.Uri

/** Delete a discarded camera output via the registered FileProvider, not by
 * treating its content URI path as a filesystem path. Never delete picker URIs.
 *
 * Only files created by first-registration's registration-menu- camera capture
 * in the owner_menu_capture mapping are eligible. Other menu-import captures,
 * certificate photos, and gallery content are deliberately excluded.
 */
internal fun deleteOwnedRegistrationMenuCapture(context: Context, uri: Uri): Boolean {
    val app = context.applicationContext
    val filename = uri.pathSegments.singleOrNull { it.startsWith("registration-menu-") }
    val nameMatches = filename?.matches(Regex("registration-menu-[A-Za-z0-9-]+\\.jpg")) == true
    if (uri.scheme != "content" ||
        uri.authority != "${app.packageName}.owner.camera.provider" ||
        uri.pathSegments.size != 2 ||
        uri.pathSegments[0] != "owner_menu_capture" ||
        uri.pathSegments[1] != filename || !nameMatches) return false
    // AndroidX FileProvider resolves its own configured root securely.
    return runCatching { app.contentResolver.delete(uri, null, null) > 0 }
        .getOrDefault(false)
}
