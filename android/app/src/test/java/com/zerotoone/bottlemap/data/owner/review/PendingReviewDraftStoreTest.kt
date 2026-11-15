package com.zerotoone.bottlemap.data.owner.review

import android.content.Context
import android.util.Base64
import com.zerotoone.bottlemap.network.ReviewDraftDto
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import com.zerotoone.bottlemap.ui.owner.review.ReviewItem
import java.io.File
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class PendingReviewDraftStoreTest {
    private val context: Context = RuntimeEnvironment.getApplication()
    private val folder = File(context.noBackupFilesDir, "pending-owner-review-drafts")

    private fun jwt(subject: String) = "header." + Base64.encodeToString(
        """{"sub":"$subject"}""".toByteArray(),
        Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP,
    ) + ".signature"

    @After fun clean() { folder.deleteRecursively() }

    @Test fun failedNetworkDraftSurvivesRecreationButCannotLeakToOtherAccountOrImport() = runBlocking {
        val original = PhotoReviewState(items = listOf(ReviewItem(
            id = "ocr-1", name = "업주 수정 이름", draftPriceText = "15000",
            volume = Double.NaN,
        )))
        val pending = PendingReviewDraftStore.Envelope(
            reviewVersion = 7, expectedDraftVersion = 3,
            itemIds = listOf("ocr-1"), content = ServerReviewDraftCodec.encode(original),
        )
        val ownerA = PendingReviewDraftStore(context) { jwt("owner-a") }
        ownerA.write("import-1", pending)
        val recreated = PendingReviewDraftStore(context) { jwt("owner-a") }
        val ownerB = PendingReviewDraftStore(context) { jwt("owner-b") }
        assertNull(ownerB.read("import-1"))
        assertNull(recreated.read("import-2"))
        val restored = requireNotNull(recreated.read("import-1"))
        assertTrue(restored.canReplay(ReviewDraftDto(
            3, 7, "2026-11-15T00:00:00Z", emptyMap()), 7))
        assertFalse(restored.canReplay(ReviewDraftDto(
            4, 7, "2026-11-15T00:00:00Z", emptyMap()), 7))
        assertFalse(restored.canReplay(ReviewDraftDto(
            3, 8, "2026-11-15T00:00:00Z", emptyMap()), 8))
        // Even when the CAS number happens to match, never replay across
        // a server draft created for another OCR review version.
        assertFalse(restored.canReplay(ReviewDraftDto(
            3, 8, "2026-11-15T00:00:00Z", emptyMap()), 7))
        val decoded = requireNotNull(ServerReviewDraftCodec.decode(ReviewDraftDto(
            3, 7, "2026-11-15T00:00:00Z", restored.content,
        )))
        assertEquals("업주 수정 이름", decoded.items.single().name)
        assertEquals("15000", decoded.items.single().draftPriceText)
        ownerB.clear("import-1")
        assertNotNull(recreated.read("import-1"))
        recreated.clear("import-1")
        assertNull(recreated.read("import-1"))
    }

    @Test fun oversizedServerDraftSurvivesInPrivateDeviceFileAfterRecreation() = runBlocking {
        val content = ServerReviewDraftCodec.encode(PhotoReviewState(items = listOf(
            ReviewItem(id = "ocr-large", name = "큰 메뉴", draftPriceText = "9".repeat(400_000)),
        )))
        assertTrue(ServerReviewDraftCodec.exceedsServerLimit(content))
        val owner = PendingReviewDraftStore(context) { jwt("owner-large") }
        owner.write("import-large", PendingReviewDraftStore.Envelope(
            reviewVersion = 3, expectedDraftVersion = 4,
            itemIds = listOf("ocr-large"), content = content,
        ))
        val recreated = PendingReviewDraftStore(context) { jwt("owner-large") }
        val saved = requireNotNull(recreated.read("import-large"))
        assertEquals(4, saved.expectedDraftVersion)
        assertTrue(ServerReviewDraftCodec.exceedsServerLimit(saved.content))
        val restored = requireNotNull(ServerReviewDraftCodec.decode(ReviewDraftDto(
            4, 3, "2026-11-15T00:00:00Z", saved.content,
        )))
        assertEquals("9".repeat(400_000), restored.items.single().draftPriceText)
        assertNull(PendingReviewDraftStore(context) { jwt("other-account") }.read("import-large"))
    }

    @Test fun conflictWorkingCopyCanShrinkWhileOriginalOversizedBackupStaysImmutable() = runBlocking {
        val original = PendingReviewDraftStore(context) { jwt("owner-working") }
        val working = PendingReviewDraftStore(context, { jwt("owner-working") }, slot = "working")
        val oversized = ServerReviewDraftCodec.encode(PhotoReviewState(items = listOf(
            ReviewItem(id = "ocr-1", name = "편집할 내용",
                draftPriceText = "8".repeat(400_000)),
        )))
        val initial = PendingReviewDraftStore.Envelope(3, 2, listOf("ocr-1"), oversized)
        original.write("import-working", initial)
        assertTrue(ServerReviewDraftCodec.exceedsServerLimit(
            requireNotNull(original.read("import-working")).content))
        val reduced = ServerReviewDraftCodec.encode(PhotoReviewState(items = listOf(
            ReviewItem(id = "ocr-1", name = "편집할 내용", draftPriceText = "8000"),
        )))
        working.write("import-working", initial.copy(content = reduced))
        // Reopening the app preserves both: the immutable original and the
        // separately trimmed version available for an explicit CAS choice.
        val origAgain = PendingReviewDraftStore(context) { jwt("owner-working") }
        val workAgain = PendingReviewDraftStore(context, { jwt("owner-working") }, "working")
        assertEquals(oversized, requireNotNull(origAgain.read("import-working")).content)
        assertEquals(reduced, requireNotNull(workAgain.read("import-working")).content)
        assertFalse(ServerReviewDraftCodec.exceedsServerLimit(
            requireNotNull(workAgain.read("import-working")).content))
        assertNull(PendingReviewDraftStore(context, { jwt("another-owner") }, "working")
            .read("import-working"))
        workAgain.clear("import-working")
        assertNotNull(origAgain.read("import-working"))
    }

    @Test fun manuallySplitChildIsCompatibleForBothRestoreAndExplicitOverwrite() {
        val fresh = PhotoReviewState(items = listOf(
            ReviewItem(id = "master", name = "위스키"),
            ReviewItem(id = "child", name = "위스키", mergedInto = "master",
                primarySourceOptionId = "ocr-option", excluded = true),
        ))
        val split = fresh.copy(items = listOf(
            fresh.items.first(),
            fresh.items.last().copy(manuallySplitGroup = true, mergedInto = null,
                excluded = false),
        ))
        assertTrue(compatibleOwnerReviewDraft(split, fresh))
        assertFalse(compatibleOwnerReviewDraft(
            split.copy(items = split.items.reversed()), fresh))
        assertFalse(compatibleOwnerReviewDraft(
            split.copy(items = listOf(split.items.first(),
                split.items.last().copy(manuallySplitGroup = false))), fresh))
        assertFalse(compatibleOwnerReviewDraft(
            split.copy(items = listOf(split.items.first(),
                split.items.last().copy(primarySourceOptionId = "unknown-id"))), fresh))
    }

    @Test fun interruptedAtomicRewriteKeepsLastCompletedLocalDraft() = runBlocking {
        val store = PendingReviewDraftStore(context) { jwt("owner-recovery") }
        val draft = PendingReviewDraftStore.Envelope(
            2, 1, listOf("ocr-1"), ServerReviewDraftCodec.encode(
                PhotoReviewState(items = listOf(ReviewItem(id = "ocr-1", name = "보관한 수정"))),
            ),
        )
        store.write("import-recovery", draft)
        val file = requireNotNull(folder.listFiles()?.singleOrNull { it.name.endsWith(".json") })
        // Simulate a process dying after the next atomic write begins but
        // before finishWrite can commit it.
        android.util.AtomicFile(file).startWrite().use {
            it.write("{corrupt partial".toByteArray())
        }
        val recovered = requireNotNull(store.read("import-recovery"))
        assertEquals("보관한 수정", requireNotNull(ServerReviewDraftCodec.decode(
            ReviewDraftDto(1, 2, "2026-11-15T00:00:00Z", recovered.content)
        )).items.single().name)
    }


    @Test fun conflictedOfflineSnapshotStaysImmutableUntilExplicitDecision() = runBlocking {
        val store = PendingReviewDraftStore(context) { jwt("owner-conflicted") }
        fun snapshot(name: String) = PendingReviewDraftStore.Envelope(
            reviewVersion = 2, expectedDraftVersion = 3, itemIds = listOf("ocr-1"),
            content = ServerReviewDraftCodec.encode(PhotoReviewState(
                items = listOf(ReviewItem(id = "ocr-1", name = name)),
            )),
        )
        val protected = snapshot("오프라인에서 고친 원본")
        store.write("import-conflicted", protected)
        try {
            // The actual Live repository uses this gate before AtomicFile.write.
            DraftSaveSafety.assertWritable(true)
            store.write("import-conflicted", snapshot("새 서버 화면의 편집"))
            fail("Conflict must not enter the local backup writer")
        } catch (_: ReviewDraftConflictException) {
            val stillSaved = requireNotNull(store.read("import-conflicted"))
            val restored = requireNotNull(ServerReviewDraftCodec.decode(ReviewDraftDto(
                3, 2, "2026-11-15T00:00:00Z", stillSaved.content,
            )))
            assertEquals("오프라인에서 고친 원본", restored.items.single().name)
            assertEquals(3, stillSaved.expectedDraftVersion)
        }
    }

    @Test fun pendingEqualSnapshotMustNotSkipRequiredServerCas() {
        val content = ServerReviewDraftCodec.encode(PhotoReviewState(
            items = listOf(ReviewItem(id = "ocr-1", name = "동일한 초안")),
        ))
        assertTrue(DraftSaveSafety.canSkip(
            forced = false, pendingLocally = false, attempted = content,
            acknowledged = content,
        ))
        assertFalse(DraftSaveSafety.canSkip(
            forced = false, pendingLocally = true, attempted = content,
            acknowledged = content,
        ))
        assertFalse(DraftSaveSafety.canSkip(
            forced = true, pendingLocally = false, attempted = content,
            acknowledged = content,
        ))
        assertFalse(DraftSaveSafety.canSkip(
            forced = false, pendingLocally = false, attempted = content,
            acknowledged = null,
        ))
    }

    @Test fun cannotWriteUnscopedDraftWithoutCurrentAuthSubject() = runBlocking {
        val unauthenticated = PendingReviewDraftStore(context) { null }
        try {
            unauthenticated.write("import-1", PendingReviewDraftStore.Envelope(
                1, 0, emptyList(), emptyMap(),
            ))
            fail("Draft must not be written without an authenticated account scope")
        } catch (_: IllegalStateException) {
            assertTrue(folder.listFiles()?.isEmpty() != false)
        }
    }
}
