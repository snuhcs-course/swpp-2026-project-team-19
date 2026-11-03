package com.zerotoone.bottlemap.data.owner

import android.content.Context
import com.zerotoone.bottlemap.network.ApiClient

/**
 * LOCAL MOCK ONLY, NOT A SERVER CACHE. Stores non-production Owner demo state in
 * app-private preferences across Activity and process recreation.
 *
 * Never enter real business numbers, credentials, or real business certificate images
 * in fixture data. Photo URIs are references, not copied image bytes. Actual picker
 * permissions must be persisted separately by the future screen implementation.
 */
// The full-backup and data-extraction rules must exclude this preference filename + ".xml".
internal const val OWNER_MOCK_PREFERENCES_NAME = "owner_mock_state_v1"

class AndroidOwnerMockStateStore(context: Context) : MockOwnerStateStore {
    private val preferences = context.applicationContext.getSharedPreferences(
        OWNER_MOCK_PREFERENCES_NAME, Context.MODE_PRIVATE,
    )
    private val adapter = ApiClient.moshi.adapter(MockOwnerSnapshot::class.java)

    override fun read(): MockOwnerSnapshot? =
        preferences.getString("snapshot", null)?.let(adapter::fromJson)

    override fun write(snapshot: MockOwnerSnapshot) {
        check(preferences.edit().putString("snapshot", adapter.toJson(snapshot)).commit()) {
            "Mock state could not be persisted"
        }
    }
}

/** Manual DI seam; one shared Repository instance for Owner and mock Customer Preview. */
object OwnerMockRuntime {
    @Volatile private var instance: OwnerMockRepository? = null

    fun repository(context: Context): OwnerMockRepository = instance ?: synchronized(this) {
        instance ?: LocalOwnerMockRepository(AndroidOwnerMockStateStore(context)).also {
            instance = it
        }
    }
}
