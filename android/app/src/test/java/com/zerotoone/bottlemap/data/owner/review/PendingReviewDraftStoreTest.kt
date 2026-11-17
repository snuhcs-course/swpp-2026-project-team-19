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


    @Test fun oldPendingAttemptCannotBlockAcknowledgedNewerCheckpoint() {
        fun content(name: String) = ServerReviewDraftCodec.encode(
            PhotoReviewState(items = listOf(ReviewItem(id = "ocr-1", name = name))))
        val pending = PendingReviewDraftStore.Envelope(
            reviewVersion = 7, expectedDraftVersion = 3,
            itemIds = listOf("ocr-1"), content = content("earlier price"))
        val newest = pending.copy(expectedDraftVersion = 4,
            content = content("latest price and volume"))
        val remote = ReviewDraftDto(
            draftVersion = 5, reviewVersion = 7,
            savedAt = "2026-11-17T00:00:00Z", content = newest.content)
        assertTrue(supersededPendingReview(pending, newest, remote))
        assertFalse(supersededPendingReview(pending, newest,
            remote.copy(content = content("someone else's change"))))
        assertFalse(supersededPendingReview(
            pending.copy(expectedDraftVersion = 5), newest, remote))
        assertFalse(supersededPendingReview(pending, null, remote))
    }

    @Test fun workingCopyAckAfterPendingWasClearedDoesNotCreateFalseConflict() {
        fun content(name: String) = ServerReviewDraftCodec.encode(
            PhotoReviewState(items = listOf(ReviewItem(id = "ocr-1", name = name))))
        val value = content("latest owner edit")
        val remote = ReviewDraftDto(8, 3, "2026-11-17T00:00:00Z", value)
        val working = PendingReviewDraftStore.Envelope(
            reviewVersion = 3, expectedDraftVersion = 7,
            itemIds = listOf("ocr-1"), content = value)
        assertEquals(DraftRecoveryPolicy.Outcome.ACKNOWLEDGED,
            DraftRecoveryPolicy.decide(remote, working, null, 3))
        assertTrue(acknowledgedWorkingReview(remote, working, null))
        assertFalse(acknowledgedWorkingReview(
            remote, working, working.copy(content = content("newer unsent edit"))))
        assertFalse(acknowledgedWorkingReview(
            remote.copy(content = content("foreign edit")), working, null))
        assertFalse(acknowledgedWorkingReview(
            remote.copy(reviewVersion = 4), working, null))
    }

    @Test fun acknowledgedWorkingCopyRetainsOlderProtectedBackup() = runBlocking {
        fun content(name: String) = ServerReviewDraftCodec.encode(
            PhotoReviewState(items = listOf(ReviewItem(id = "ocr-1", name = name))),
        )
        val original = PendingReviewDraftStore.Envelope(
            reviewVersion = 7, expectedDraftVersion = 3,
            itemIds = listOf("ocr-1"), content = content("before conflict"),
        )
        val working = original.copy(content = content("explicitly edited copy"))
        val originalStore = PendingReviewDraftStore(context) { jwt("working-ack") }
        val workingStore = PendingReviewDraftStore(context, slot = "working") {
            jwt("working-ack")
        }
        originalStore.write("import-ack", original)
        workingStore.write("import-ack", working)
        val server = ReviewDraftDto(4, 7, "2026-11-17T00:00:00Z", working.content)
        val againOriginal = requireNotNull(originalStore.read("import-ack"))
        val againWorking = requireNotNull(workingStore.read("import-ack"))
        assertEquals(DraftRecoveryPolicy.Outcome.ACKNOWLEDGED,
            DraftRecoveryPolicy.decide(server, againWorking, againOriginal, 7))
        assertTrue(DraftSaveSafety.latestCopyAcknowledged(
            server, againOriginal, againWorking))
        assertFalse(DraftSaveSafety.latestCopyAcknowledged(
            server, againOriginal, againWorking,
            againWorking.copy(content = content("newer unsaved keystroke"))))
        assertTrue(ServerReviewDraftCodec.sameAndroidSnapshot(
            original.content, requireNotNull(originalStore.read("import-ack")).content))
        assertFalse(DraftSaveSafety.latestCopyAcknowledged(
            server.copy(content = content("third party")), againOriginal, againWorking))
    }

    @Test fun selfWrittenOutdatedCasIsAcknowledgedButForeignDraftStillConflicts() {
        fun content(name: String) = ServerReviewDraftCodec.encode(
            PhotoReviewState(items = listOf(ReviewItem(id = "ocr-1", name = name))))
        val written = content("our latest version")
        val server = ReviewDraftDto(
            draftVersion = 4, reviewVersion = 7,
            savedAt = "2026-11-17T00:00:00Z", content = written)
        assertTrue(DraftSaveSafety.ownCasAcknowledged(server, written, 3, 7))
        assertFalse(DraftSaveSafety.ownCasAcknowledged(
            server.copy(content = content("different device")), written, 3, 7))
        assertFalse(DraftSaveSafety.ownCasAcknowledged(
            server.copy(draftVersion = 5), written, 3, 7))
        assertFalse(DraftSaveSafety.ownCasAcknowledged(
            server.copy(reviewVersion = 8), written, 3, 7))
        assertFalse(DraftSaveSafety.ownCasAcknowledged(null, written, 3, 7))
    }

    @Test fun recoveryPolicyRestoresOnlyMatchingReviewAndServerCas() {
        fun content(name: String) = ServerReviewDraftCodec.encode(
            PhotoReviewState(items = listOf(ReviewItem(id = "ocr-1", name = name)))
        )
        fun envelope(name: String, expected: Int) =
            PendingReviewDraftStore.Envelope(
                reviewVersion = 7, expectedDraftVersion = expected,
                itemIds = listOf("ocr-1"), content = content(name),
            )
        fun remote(name: String, version: Int) =
            ReviewDraftDto(version, 7, "2026-11-16T00:00:00Z", content(name))

        val local = envelope("latest edit", 3)
        assertEquals(DraftRecoveryPolicy.Outcome.RESTORE,
            DraftRecoveryPolicy.decide(remote("older edit", 3), local, null, 7))
        assertEquals(DraftRecoveryPolicy.Outcome.ACKNOWLEDGED,
            DraftRecoveryPolicy.decide(remote("latest edit", 4), local, null, 7))
        assertEquals(DraftRecoveryPolicy.Outcome.REBASE,
            DraftRecoveryPolicy.decide(
                remote("in flight", 4), local, envelope("in flight", 3), 7))
        assertEquals(DraftRecoveryPolicy.Outcome.CONFLICT,
            DraftRecoveryPolicy.decide(remote("other device", 4), local, null, 7))
        assertEquals(DraftRecoveryPolicy.Outcome.CONFLICT,
            DraftRecoveryPolicy.decide(remote("other device", 5), local,
                envelope("in flight", 3), 7))
        assertEquals(DraftRecoveryPolicy.Outcome.CONFLICT,
            DraftRecoveryPolicy.decide(remote("older edit", 3),
                local.copy(reviewVersion = 6), null, 7))
        assertEquals(DraftRecoveryPolicy.Outcome.NONE,
            DraftRecoveryPolicy.decide(remote("older edit", 3), null, null, 7))
    }

    @Test fun checkpointStoreRetainsLatestEditSeparateFromPreviousInFlightAttempt() =
        runBlocking {
            fun envelope(name: String) = PendingReviewDraftStore.Envelope(
                reviewVersion = 7, expectedDraftVersion = 3,
                itemIds = listOf("ocr-1"),
                content = ServerReviewDraftCodec.encode(PhotoReviewState(
                    items = listOf(ReviewItem(id = "ocr-1", name = name)))),
            )
            val attempt = PendingReviewDraftStore(context) { jwt("same-owner") }
            val checkpoint = PendingReviewDraftStore(context, slot = "checkpoint") {
                jwt("same-owner")
            }
            attempt.write("import-1", envelope("first request"))
            checkpoint.write("import-1", envelope("newest local edit"))
            attempt.clear("import-1")
            assertNull(attempt.read("import-1"))
            val recovered = requireNotNull(checkpoint.read("import-1"))
            val decoded = ServerReviewDraftCodec.decode(ReviewDraftDto(
                3, 7, "2026-11-16T00:00:00Z", recovered.content))
            assertEquals("newest local edit", decoded?.items?.single()?.name)
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
        val working = PendingReviewDraftStore(context, slot = "working") { jwt("owner-working") }
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
        val workAgain = PendingReviewDraftStore(context, slot = "working") { jwt("owner-working") }
        assertTrue(ServerReviewDraftCodec.sameAndroidSnapshot(
            oversized, requireNotNull(origAgain.read("import-working")).content))
        assertTrue(ServerReviewDraftCodec.sameAndroidSnapshot(
            reduced, requireNotNull(workAgain.read("import-working")).content))
        assertFalse(ServerReviewDraftCodec.exceedsServerLimit(
            requireNotNull(workAgain.read("import-working")).content))
        assertNull(PendingReviewDraftStore(context, slot = "working") { jwt("another-owner") }
            .read("import-working"))
        workAgain.clear("import-working")
        assertNotNull(origAgain.read("import-working"))
    }

    @Test fun reorderingCardsDoesNotChangeOcrIdentityButMissingOrDuplicateDoes() {
        assertTrue(sameReviewSourceIds(
            listOf("line-a", "line-b"), listOf("line-b", "line-a")))
        assertFalse(sameReviewSourceIds(
            listOf("line-a", "line-a"), listOf("line-a", "line-b")))
        assertFalse(sameReviewSourceIds(
            listOf("line-a"), listOf("line-a", "line-b")))
        assertFalse(sameReviewSourceIds(
            listOf("line-a", "line-z"), listOf("line-a", "line-b")))
    }

    @Test fun uneditedReloadDoesNotReplaceProtectedConflictDraft() = runBlocking {
        fun snapshot(name: String) = ServerReviewDraftCodec.encode(
            PhotoReviewState(items = listOf(ReviewItem(id = "ocr-1", name = name))))
        val remoteDisplay = snapshot("current server version")
        val protectedLocal = snapshot("edited on this device")
        val store = PendingReviewDraftStore(context, slot = "working") {
            jwt("protected-conflict")
        }
        val envelope = PendingReviewDraftStore.Envelope(
            reviewVersion = 7, expectedDraftVersion = 5,
            itemIds = listOf("ocr-1"), content = protectedLocal,
        )
        store.write("import-conflict-preserve", envelope)
        assertFalse(isNewConflictReviewEdit(remoteDisplay, remoteDisplay))
        // The Back handler must not write the displayed remote state over the
        // protected local copy when the user made no edits after reloading.
        if (isNewConflictReviewEdit(remoteDisplay, remoteDisplay)) {
            store.write("import-conflict-preserve", envelope.copy(content = remoteDisplay))
        }
        assertTrue(ServerReviewDraftCodec.sameAndroidSnapshot(
            protectedLocal,
            requireNotNull(store.read("import-conflict-preserve")).content))
        assertTrue(isNewConflictReviewEdit(protectedLocal, remoteDisplay))
    }

    @Test fun manuallySplitChildIsCompatibleForBothRestoreAndExplicitOverwrite() {
        val fresh = PhotoReviewState(items = listOf(
            ReviewItem(id = "master", name = "위스키"),
            ReviewItem(id = "child", name = "위스키", mergedInto = "master",
                primaryHasOption = true, primarySourceOptionId = "ocr-option",
                price = 15000.0, volume = 30.0, excluded = true),
        ))
        val split = fresh.copy(items = listOf(
            fresh.items.first(),
            fresh.items.last().copy(manuallySplitGroup = true, mergedInto = null,
                excluded = false),
        ))
        assertTrue(compatibleOwnerReviewDraft(split, fresh))
        // Display/group ordering is not OCR identity. Restoring the same
        // extracted IDs must not discard the owner's latest edits.
        assertTrue(compatibleOwnerReviewDraft(
            split.copy(items = split.items.reversed()), fresh))
        val changedSelection = split.copy(items = listOf(
            split.items.first(),
            split.items.last().copy(volumeChoices = emptyList(),
                chosenVolumeKeys = setOf("ml:30")),
        ))
        assertTrue(compatibleOwnerReviewDraft(changedSelection, fresh))
        assertFalse(compatibleOwnerReviewDraft(
            split.copy(items = listOf(split.items.first(),
                split.items.last().copy(manuallySplitGroup = false))), fresh))
        assertFalse(compatibleOwnerReviewDraft(
            split.copy(items = listOf(split.items.first(),
                split.items.last().copy(primarySourceOptionId = "unknown-id"))), fresh))
    }

    @Test fun oldServerAckCannotDeleteMoreRecentUnsubmittedWorkingCopy() {
        fun snapshot(name: String) = ServerReviewDraftCodec.encode(
            PhotoReviewState(items = listOf(ReviewItem(id = "ocr-1", name = name))),
        )
        val original = PendingReviewDraftStore.Envelope(
            3, 4, listOf("ocr-1"), snapshot("옛 원본"),
        )
        val edited = original.copy(content = snapshot("작업 중 변경사항"))
        fun server(content: Map<String, Any?>, reviewVersion: Int = 3) =
            ReviewDraftDto(5, reviewVersion, "2026-11-15T00:00:00Z", content)
        assertFalse(DraftSaveSafety.latestCopyAcknowledged(
            server(original.content), original, edited))
        assertTrue(DraftSaveSafety.latestCopyAcknowledged(
            server(edited.content), original, edited))
        assertTrue(DraftSaveSafety.latestCopyAcknowledged(
            server(original.content), original, null))
        assertFalse(DraftSaveSafety.latestCopyAcknowledged(
            server(edited.content, 4), original, edited))
        assertFalse(DraftSaveSafety.latestCopyAcknowledged(
            ReviewDraftDto(4, 3, "2026-11-15T00:00:00Z", edited.content),
            original, edited))
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
