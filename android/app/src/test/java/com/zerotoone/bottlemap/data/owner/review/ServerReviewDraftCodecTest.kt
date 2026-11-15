package com.zerotoone.bottlemap.data.owner.review

import com.zerotoone.bottlemap.network.ReviewDraftDto
import com.zerotoone.bottlemap.ui.owner.review.ClassificationSnapshot
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewState
import com.zerotoone.bottlemap.ui.owner.review.PhotoReviewRules
import com.zerotoone.bottlemap.ui.owner.review.PriceChoice
import com.zerotoone.bottlemap.ui.owner.review.ReviewItem
import com.zerotoone.bottlemap.ui.owner.review.ReviewItemType
import com.zerotoone.bottlemap.ui.owner.review.ReviewIssue
import com.zerotoone.bottlemap.ui.owner.review.ReviewMatch
import com.zerotoone.bottlemap.ui.owner.review.ReviewOption
import com.zerotoone.bottlemap.ui.owner.review.ReviewPriceCandidate
import com.zerotoone.bottlemap.ui.owner.review.VolumeSource
import org.junit.Assert.*
import org.junit.Test

class ServerReviewDraftCodecTest {
    @Test fun roundTripPreservesUnfinishedEditsWithoutSignedMediaOrNaN() {
        val item = ReviewItem(
            id = "ocr-1", name = "수정한 위스키", price = 15000.0,
            volume = Double.NaN, draftPriceText = "145",
            priceChoice = PriceChoice.MANUAL,
            reviewNameDraft = "수정 중", nameEditMode = true,
            sourcePhotoUrl = "https://signed.example/secret?token=abc",
            sourceBox = listOf(1,2,3,4),
            raw = "OCR raw line",
            options = listOf(ReviewOption(volume = Double.NaN, price = 20000.0)),
            classificationSnapshot = ClassificationSnapshot(
                type = ReviewItemType.OTHER,
                volume = Double.NaN, volumeSource = VolumeSource.PHOTO,
                bottle = false, primaryHasOption = true,
                options = listOf(ReviewOption(volume = Double.NaN)),
                match = ReviewMatch.NEW, matchConfirmed = false,
                nameSaved = false, newConfirmed = false,
                linkedProductId = null, linkedProductName = null,
                newProductName = null, candidates = emptyList(),
                rawOptionEdits = emptyMap(), primaryPrice = Double.NaN,
            ),
        )
        val data = ServerReviewDraftCodec.encode(PhotoReviewState(items = listOf(item)))
        val saved = ReviewDraftDto(4, 3, "2026-11-15T00:00:00Z", data)
        val restored = requireNotNull(ServerReviewDraftCodec.decode(saved))
        assertEquals("수정 중", restored.items.single().reviewNameDraft)
        assertEquals("145", restored.items.single().draftPriceText)
        assertEquals(PriceChoice.MANUAL, restored.items.single().priceChoice)
        assertEquals(0.0, restored.items.single().volume, 0.0)
        assertEquals(0.0, restored.items.single().options.single().volume, 0.0)
        assertEquals(0.0, restored.items.single().classificationSnapshot!!.volume, 0.0)
        assertNull(restored.items.single().classificationSnapshot!!.primaryPrice)
        val encoded = data.toString()
        assertFalse(encoded.contains("token=abc"))
        assertFalse(encoded.contains("OCR raw line"))
        assertFalse(encoded.contains("NaN"))
        assertEquals("ocr-1",
            (data["itemDecisions"] as List<*>).first().let {
                (it as Map<*, *>)["extractedItemId"]
            })
    }

    @Test fun anotherDevicesAndroidDraftRestoresReviewItemEdits() {
        val line = ReviewItem(
            id = "line-1", name = "글렌피딕 12",
            linkedProductId = "catalog-1",
            chosenServingPrices = mapOf("ml:30" to 12000),
            manuallySplitGroup = true, draftVolumeText = "6",
            expanded = true,
        )
        val content = ServerReviewDraftCodec.encode(PhotoReviewState(items = listOf(line)))
        val fromServer = ReviewDraftDto(7, 3, "2026-11-15T00:00:00Z", content)
        val copy = requireNotNull(ServerReviewDraftCodec.decode(fromServer)).items.single()
        assertEquals(mapOf("ml:30" to 12000), copy.chosenServingPrices)
        assertTrue(copy.manuallySplitGroup)
        assertTrue(copy.expanded)
        assertEquals("6", copy.draftVolumeText)
    }

    @Test fun restoredConfirmedPricesSurviveStrippedPreviousServerPriceMap() {
        val saved30 = ReviewPriceCandidate(
            servingKey = "ml:30", volumeMl = 30, priceKrw = 11000, existing = true,
        )
        val saved60 = ReviewPriceCandidate(
            servingKey = "ml:60", volumeMl = 60, priceKrw = 20000, existing = true,
        )
        val original = PhotoReviewState(items = listOf(
            ReviewItem(
                id = "ocr-1", name = "검수한 위스키",
                linkedProductId = "product-1",
                volume = 30.0, price = 12000.0,
                options = listOf(ReviewOption(volume = 60.0, price = 22000.0)),
                chosenServingPrices = mapOf("ml:30" to 12000, "ml:60" to 22000),
                priceCandidates = listOf(saved30, saved60),
                existingServingPricesByProductId =
                    mapOf("product-1" to listOf(saved30, saved60)),
            ),
        ))
        val encoded = ServerReviewDraftCodec.encode(original)
        val recovered = requireNotNull(ServerReviewDraftCodec.decode(
            ReviewDraftDto(4, 3, "2026-11-16T00:00:00Z", encoded),
        )).items.single()
        // The decoder omits the old server-derived map by design.
        assertTrue(recovered.existingServingPricesByProductId.isEmpty())
        // Rebinding must preserve BOTH previously reviewed serving choices.
        assertEquals(mapOf("ml:30" to 12000, "ml:60" to 22000),
            retainedOwnerServingPriceDecisions(recovered, listOf(saved30, saved60)))
        // If the server changes one existing serving, require review only
        // for that serving, not for an unrelated correctly reviewed option.
        val changed30 = saved30.copy(priceKrw = 13000)
        assertEquals(mapOf("ml:60" to 22000),
            retainedOwnerServingPriceDecisions(recovered, listOf(changed30, saved60)))
        // A stale confirmation not matching the owner-edited final option
        // must never be restored as if the price was reviewed.
        assertEquals(emptyMap<String, Int>(), retainedOwnerServingPriceDecisions(
            recovered.copy(chosenServingPrices = mapOf("ml:30" to 9999)),
            listOf(saved30, saved60),
        ))
    }

    @Test fun serverDraftRoundTripPreservesSeveralDifferentReviewedItemDecisions() {
        val state = PhotoReviewState(items = listOf(
            ReviewItem(id = "linked", name = "수정한 상품", linkedProductId = "p1",
                price = 13000.0, volume = 30.0, matchConfirmed = true),
            ReviewItem(id = "excluded", name = "잡음", excluded = true),
            ReviewItem(id = "manual", name = "직접 입력", priceChoice = PriceChoice.MANUAL,
                price = 14000.0, volume = 60.0, draftPriceText = "15000"),
        ))
        val restored = requireNotNull(ServerReviewDraftCodec.decode(ReviewDraftDto(
            3, 7, "2026-11-16T00:00:00Z", ServerReviewDraftCodec.encode(state),
        )))
        assertEquals(listOf("linked", "excluded", "manual"),
            restored.items.map { it.id })
        assertEquals("수정한 상품", restored.items[0].name)
        assertTrue(restored.items[1].excluded)
        assertEquals(PriceChoice.MANUAL, restored.items[2].priceChoice)
        assertEquals("15000", restored.items[2].draftPriceText)
    }

    @Test fun foreignClientDraftCannotBeMistakenForEmptyAndroidDraft() {
        val foreign = ReviewDraftDto(5, 3, "2026-11-15T00:00:00Z",
            mapOf("itemDecisions" to listOf(mapOf("extractedItemId" to "ocr-1"))))
        assertNull(ServerReviewDraftCodec.decode(foreign))
    }

    @Test fun oversizedDraftIsEncodedForDeviceButMarkedUnsafeForServerPut() {
        val huge = PhotoReviewState(items = listOf(ReviewItem(
            id = "line-1", name = "A",
            draftPriceText = "9".repeat(270_000),
        )))
        // Do not throw before PendingReviewDraftStore.write(), even when
        // the server's JSON content limit is exceeded.
        val content = ServerReviewDraftCodec.encode(huge)
        assertTrue(ServerReviewDraftCodec.exceedsServerLimit(content))
        val restored = requireNotNull(ServerReviewDraftCodec.decode(ReviewDraftDto(
            0, 3, "2026-11-15T00:00:00Z", content,
        )))
        assertEquals("9".repeat(270_000), restored.items.single().draftPriceText)
        val normal = ServerReviewDraftCodec.encode(PhotoReviewState(items = listOf(
            ReviewItem(id = "line-1", name = "A", draftPriceText = "9000"),
        )))
        assertFalse(ServerReviewDraftCodec.exceedsServerLimit(normal))
    }
    @Test fun operatorStandardDraftRestoresSimpleNamePriceAndLinkedProduct() {
        val state = PhotoReviewState(items = listOf(
            ReviewItem(id = "ocr-1", name = "인식된 이름",
                price = 12000.0, volume = 30.0,
                primarySourceOptionId = "opt-1"),
        ))
        val server = ReviewDraftDto(2, 3, "2026-11-15T00:00:00Z", mapOf(
            "itemDecisions" to listOf(mapOf(
                "extractedItemId" to "ocr-1",
                "action" to "select_existing_product",
                "productId" to "catalog-a",
                "correctedProductName" to "수정된 상품",
                "options" to listOf(mapOf(
                    "extractedOptionId" to "opt-1",
                    "optionLabel" to "잔",
                    "pourMl" to 30,
                    "priceKrw" to 15000,
                )),
            )),
            "changeDecisions" to emptyList<Any>(),
        ))
        val restored = requireNotNull(ServerReviewDraftCodec.restoreStandard(server,state))
            .items.single()
        assertEquals("catalog-a", restored.linkedProductId)
        assertEquals("수정된 상품", restored.name)
        assertEquals(15000.0, restored.price, 0.0)
        assertEquals("opt-1",restored.primarySourceOptionId)
        assertTrue(restored.matchConfirmed)
    }

    @Test fun operatorChangeDecisionOrUnknownOptionCannotBeSilentlyDiscarded() {
        val state=PhotoReviewState(items=listOf(ReviewItem(
            id="ocr-1",name="위스키",primarySourceOptionId="opt-1",
        )))
        val decisions=listOf(mapOf(
            "extractedItemId" to "ocr-1",
            "options" to listOf(mapOf(
                "extractedOptionId" to "wrong-id", "pourMl" to 30,
                "priceKrw" to 12000,
            )),
        ))
        val saved=ReviewDraftDto(2,3,"2026-11-15T00:00:00Z",mapOf(
            "itemDecisions" to decisions, "changeDecisions" to emptyList<Any>(),
        ))
        assertNull(ServerReviewDraftCodec.restoreStandard(saved,state))
        val withIgnore=saved.copy(content=saved.content + mapOf(
            "changeDecisions" to listOf(mapOf("changeId" to "change-a", "decision" to "ignore")),
        ))
        assertNull(ServerReviewDraftCodec.restoreStandard(withIgnore,state))
    }

    @Test fun lostSaveResponseCanBeIdentifiedAfterServerJsonRoundTrip() {
        val state=PhotoReviewState(items=listOf(ReviewItem(id="ocr-1",name="위스키")))
        val attempted=ServerReviewDraftCodec.encode(state)
        val client=attempted["clientState"] as Map<*, *>
        // Real Moshi object/number roundtrip converts JSON integer 1 to 1.0.
        val serverCopy=attempted + mapOf("clientState" to
            client + mapOf("androidSchemaVersion" to 1.0))
        assertTrue(ServerReviewDraftCodec.sameAndroidSnapshot(attempted,serverCopy))
        assertFalse(ServerReviewDraftCodec.sameAndroidSnapshot(attempted,null))
        val changed=ServerReviewDraftCodec.encode(state.copy(
            items=state.items.map { it.copy(draftPriceText="changed") },
        ))
        assertFalse(ServerReviewDraftCodec.sameAndroidSnapshot(attempted,changed))
        // Do not confuse a different operator's choices with our lost 200,
        // even when they kept the original Android UI snapshot verbatim.
        val foreign=serverCopy + mapOf("itemDecisions" to emptyList<Any>())
        assertFalse(ServerReviewDraftCodec.sameAndroidSnapshot(attempted,foreign))
    }


    @Test fun operatorEmptyDraftAndDeletedOptionsAreNotRejectedOrResurrected() {
        val fresh = PhotoReviewState(items = listOf(ReviewItem(
            id = "ocr-1", name = "위스키", price = 10000.0, volume = 30.0,
            primarySourceOptionId = "opt-1",
        )))
        fun draft(content: Map<String, Any?>) =
            ReviewDraftDto(2, 3, "2026-11-15T00:00:00Z", content)
        assertEquals(fresh, ServerReviewDraftCodec.restoreStandard(draft(emptyMap()), fresh))
        assertEquals(fresh, ServerReviewDraftCodec.restoreStandard(
            draft(mapOf("changeDecisions" to emptyList<Any>())), fresh))
        val cleared = requireNotNull(ServerReviewDraftCodec.restoreStandard(
            draft(mapOf("itemDecisions" to listOf(mapOf(
                "extractedItemId" to "ocr-1", "options" to emptyList<Any>()
            )))), fresh,
        )).items.single()
        assertFalse(cleared.primaryHasOption)
        assertTrue(PhotoReviewRules.optionSummary(cleared).isEmpty())
    }

    @Test fun operatorFirstOptionIsRetainedAndExplicitNonProductCannotBecomeReject() {
        val fresh = PhotoReviewState(items = listOf(ReviewItem(
            id = "ocr-1", name = "위스키", price = 0.0, primaryHasOption = false,
        )))
        fun draft(decision: Map<String, Any?>) =
            ReviewDraftDto(2, 3, "2026-11-15T00:00:00Z",
                mapOf("itemDecisions" to listOf(decision)))
        val added = requireNotNull(ServerReviewDraftCodec.restoreStandard(draft(mapOf(
            "extractedItemId" to "ocr-1",
            "options" to listOf(mapOf("priceKrw" to 15000,
                "optionLabel" to "잔", "pourMl" to 45)),
        )), fresh)).items.single()
        assertTrue(added.primaryHasOption)
        assertEquals(15000.0, PhotoReviewRules.optionSummary(added).single().price, 0.0)
        assertNull(ServerReviewDraftCodec.restoreStandard(draft(mapOf(
            "extractedItemId" to "ocr-1", "action" to "confirm_non_product",
            "finalLineType" to "header",
        )), fresh))
        assertNull(ServerReviewDraftCodec.restoreStandard(draft(mapOf(
            "extractedItemId" to "ocr-1", "action" to "publish_without_product",
        )), fresh))
        val other = requireNotNull(ServerReviewDraftCodec.restoreStandard(draft(mapOf(
            "extractedItemId" to "ocr-1", "action" to "publish_without_product",
            "kind" to "other",
        )), fresh)).items.single()
        assertEquals(ReviewItemType.OTHER, other.type)
    }

    @Test fun operatorStandardDecisionsOverrideStaleClientState() {
        val fresh = PhotoReviewState(items = listOf(ReviewItem(
            id = "ocr-1", name = "원래 메뉴", price = 10000.0,
        )))
        val original = ServerReviewDraftCodec.encode(fresh)
        val updated = original + mapOf("itemDecisions" to listOf(mapOf(
            "extractedItemId" to "ocr-1",
            "correctedProductName" to "운영자가 수정한 이름",
        )))
        val dto = ReviewDraftDto(4, 3, "2026-11-15T00:00:00Z", updated)
        // The embedded Android snapshot is no longer authoritative.
        assertNull(ServerReviewDraftCodec.decode(dto))
        val restored = requireNotNull(ServerReviewDraftCodec.restoreStandard(dto, fresh))
        assertEquals("운영자가 수정한 이름", restored.items.single().name)
        val noOptions = ReviewItem(id = "empty", name = "미완료",
            primaryHasOption = false)
        val emptyWire = ServerReviewDraftCodec.encode(
            PhotoReviewState(items = listOf(noOptions)))
        val firstDecision = (emptyWire["itemDecisions"] as List<*>).first() as Map<*, *>
        assertEquals(emptyList<Any>(), firstDecision["options"])
    }

    @Test fun regeneratedReviewKeepsSurvivingEditsByIdAndRechecksChangedOptions() {
        val edited = ReviewItem(
            id = "retained", name = "사장님이 고친 이름",
            volume = 30.0, price = 16000.0,
            primarySourceOptionId = "removed-opt",
            options = listOf(ReviewOption(
                volume = 60.0, price = 24000.0, sourceOptionId = "still-opt",
            )),
        )
        val previous = PhotoReviewState(items = listOf(
            ReviewItem(id = "deleted", name = "과거 줄"),
            edited,
        ))
        val now = PhotoReviewState(items = listOf(
            ReviewItem(id = "new", name = "새 줄"),
            ReviewItem(id = "retained", name = "OCR 새 이름",
                primarySourceOptionId = "still-opt",
                volume = 60.0, price = 20000.0,
                options = listOf(ReviewOption(
                    volume = 90.0, price = 28000.0,
                    sourceOptionId = "new-opt",
                )),
            ),
        ))
        val fixed = requireNotNull(ServerReviewDraftCodec.reconcileRegenerated(previous,now))
        assertEquals(listOf("new","retained"), fixed.items.map { it.id })
        val line = fixed.items.last()
        assertEquals("사장님이 고친 이름", line.name)
        assertEquals("still-opt", line.primarySourceOptionId)
        assertEquals(24000.0,line.price,0.0)
        assertFalse(line.volumeChoicesConfirmed)
        assertEquals(setOf("still-opt","new-opt"),
            line.volumeChoices.mapNotNull { it.sourceOptionId }.toSet())
        assertFalse(PhotoReviewRules.stats(fixed).canPublish)
    }

    @Test fun regeneratedOperatorDraftIgnoresRemovedItemsAndStaleOptions() {
        val fresh = PhotoReviewState(items = listOf(ReviewItem(
            id = "live", name = "메뉴",
            primarySourceOptionId = "option-live",
        )))
        val dto = ReviewDraftDto(5, 2, "2026-11-15T00:00:00Z", mapOf(
            "itemDecisions" to listOf(
                mapOf("extractedItemId" to "removed", "action" to "reject"),
                mapOf("extractedItemId" to "live", "options" to listOf(
                    mapOf("extractedOptionId" to "option-deleted",
                        "priceKrw" to 11000),
                    mapOf("extractedOptionId" to "option-live",
                        "priceKrw" to 15000, "pourMl" to 30),
                )),
            ),
        ))
        val restored = requireNotNull(ServerReviewDraftCodec.restoreStandard(
            dto, fresh, allowStaleIds = true,
        ))
        assertEquals(listOf("live"),restored.items.map { it.id })
        assertEquals(15000.0,restored.items.single().price,0.0)
        assertEquals("option-live",restored.items.single().primarySourceOptionId)
    }

    @Test fun operatorAliasChangesCannotBeDiscardedByAndroidAutosave() {
        val fresh = PhotoReviewState(items = listOf(ReviewItem(
            id = "ocr-1", name = "위스키", primarySourceOptionId = "opt-1",
        )))
        fun draft(aliases: Any?) = ReviewDraftDto(5, 3, "2026-11-15T00:00:00Z",
            mapOf("itemDecisions" to listOf(mapOf(
                "extractedItemId" to "ocr-1",
                "action" to "select_existing_product",
                "productId" to "catalog-a",
                "aliasesToAdd" to aliases,
            ))))
        assertNull(ServerReviewDraftCodec.restoreStandard(
            draft(listOf("운영자 확정 별칭")), fresh))
        assertNotNull(ServerReviewDraftCodec.restoreStandard(
            draft(emptyList<String>()), fresh))
        assertNull(ServerReviewDraftCodec.restoreStandard(
            draft("잘못된 별칭 형식"), fresh))
    }

    @Test fun regeneratedClassificationSnapshotNeverRestoresDeletedOcrId() {
        val hidden = ClassificationSnapshot(
            type = ReviewItemType.OTHER,
            volume = 30.0,
            volumeSource = VolumeSource.PHOTO,
            bottle = false,
            primaryHasOption = true,
            options = listOf(ReviewOption(
                volume = 60.0, price = 20000.0, sourceOptionId = "surviving",
            )),
            match = ReviewMatch.NEW,
            matchConfirmed = false,
            nameSaved = true,
            newConfirmed = true,
            linkedProductId = null,
            linkedProductName = null,
            newProductName = null,
            candidates = emptyList(),
            rawOptionEdits = emptyMap(),
            primarySourceOptionId = "removed",
            primaryPrice = 15000.0,
        )
        val previous = PhotoReviewState(items = listOf(ReviewItem(
            id = "line", name = "교정한 위스키", volume = 30.0, price = 12000.0,
            primarySourceOptionId = "visible",
            classificationSnapshot = hidden,
        )))
        val updated = PhotoReviewState(items = listOf(ReviewItem(
            id = "line", name = "OCR 결과", volume = 30.0, price = 12000.0,
            primarySourceOptionId = "visible",
            options = listOf(ReviewOption(
                volume = 60.0, price = 18000.0, sourceOptionId = "surviving",
            )),
        )))
        val recovered = requireNotNull(
            ServerReviewDraftCodec.reconcileRegenerated(previous, updated)
        ).items.single()
        val safeSnapshot = requireNotNull(recovered.classificationSnapshot)
        assertEquals("surviving", safeSnapshot.primarySourceOptionId)
        assertTrue(safeSnapshot.options.isEmpty())
        assertFalse(recovered.volumeChoicesConfirmed)
        val returnedToOther = PhotoReviewRules.reclassify(recovered, 30.0)
        assertEquals("surviving", returnedToOther.primarySourceOptionId)
        assertFalse(PhotoReviewRules.optionSummary(returnedToOther)
            .any { it.sourceOptionId == "removed" })
    }

    @Test fun regeneratedOperatorDraftRequiresExplicitNewOcrOptionSelection() {
        val fresh = PhotoReviewState(items = listOf(ReviewItem(
            id = "line", name = "위스키",
            price = 12000.0, volume = 30.0, primarySourceOptionId = "option-a",
            options = listOf(ReviewOption(
                price = 22000.0, volume = 60.0, sourceOptionId = "option-b",
            )),
        )))
        val content = mapOf("itemDecisions" to listOf(mapOf(
            "extractedItemId" to "line",
            "options" to listOf(mapOf(
                "extractedOptionId" to "option-a",
                "priceKrw" to 15000,
                "pourMl" to 30,
            )),
        )))
        val saved = ReviewDraftDto(4, 2, "2026-11-15T00:00:00Z", content)
        val restored = requireNotNull(ServerReviewDraftCodec.restoreStandard(
            saved, fresh, allowStaleIds = true))
        val line = restored.items.single()
        assertFalse(line.volumeChoicesConfirmed)
        assertEquals(setOf("option-a", "option-b"),
            line.volumeChoices.mapNotNull { it.sourceOptionId }.toSet())
        assertEquals(setOf("ml:30"), line.chosenVolumeKeys)
        assertFalse(PhotoReviewRules.stats(restored).canPublish)
        // The non-whisky screen cannot express the whisky-only volume picker.
        assertNull(ServerReviewDraftCodec.restoreStandard(saved,
            fresh.copy(items = fresh.items.map { it.copy(type = ReviewItemType.OTHER) }),
            allowStaleIds = true))
    }

    @Test fun operatorBottleCapacityLabelsRestoreWithBottleIdentity() {
        val original = PhotoReviewState(items = listOf(ReviewItem(
            id = "line", name = "위스키", primarySourceOptionId = "opt-1",
        )))
        for (label in listOf("병 700ml", "Bottle 700ml")) {
            val server = ReviewDraftDto(4, 3, "2026-11-15T00:00:00Z",
                mapOf("itemDecisions" to listOf(mapOf(
                    "extractedItemId" to "line",
                    "options" to listOf(mapOf(
                        "extractedOptionId" to "opt-1",
                        "optionLabel" to label,
                        "priceKrw" to 90000,
                    )),
                ))))
            val restored = requireNotNull(ServerReviewDraftCodec.restoreStandard(
                server, original)).items.single()
            val option = PhotoReviewRules.optionSummary(restored).single()
            assertTrue(label, option.bottle)
            assertEquals(0.0, option.volume, 0.0)
            assertEquals("bottle", PhotoReviewRules.servingKey(option))
        }
    }

    @Test fun partialOperatorProductIdWithoutActionCannotBeDiscarded() {
        val fresh = PhotoReviewState(items = listOf(ReviewItem(
            id = "ocr-1", name = "미확인 상품", match = ReviewMatch.NEW,
            linkedProductId = null,
        )))
        fun draft(decision: Map<String, Any?>) = ReviewDraftDto(
            4, 3, "2026-11-15T00:00:00Z",
            mapOf("itemDecisions" to listOf(decision)),
        )
        assertNull(ServerReviewDraftCodec.restoreStandard(
            draft(mapOf(
                "extractedItemId" to "ocr-1",
                "productId" to "operator-selected",
            )), fresh))
        val completed = requireNotNull(ServerReviewDraftCodec.restoreStandard(
            draft(mapOf(
                "extractedItemId" to "ocr-1",
                "action" to "select_existing_product",
                "productId" to "operator-selected",
            )), fresh)).items.single()
        assertEquals("operator-selected", completed.linkedProductId)
        assertEquals(ReviewItemType.WHISKY, completed.type)
    }

    @Test fun operatorCatalogSelectionConvertsOtherToWhiskyAndEnforcesThreeSizes() {
        val fresh = PhotoReviewState(items = listOf(ReviewItem(
            id = "other-line", name = "잘못 분류한 위스키",
            type = ReviewItemType.OTHER, primarySourceOptionId = "opt-1",
            options = listOf(
                ReviewOption(45.0, 14000.0, sourceOptionId = "opt-2"),
                ReviewOption(60.0, 19000.0, sourceOptionId = "opt-3"),
                ReviewOption(90.0, 25000.0, sourceOptionId = "opt-4"),
            ),
        )))
        val saved = ReviewDraftDto(4, 3, "2026-11-15T00:00:00Z", mapOf(
            "itemDecisions" to listOf(mapOf(
                "extractedItemId" to "other-line",
                "action" to "select_existing_product",
                "productId" to "catalog-whisky",
            )),
        ))
        val restored = requireNotNull(
            ServerReviewDraftCodec.restoreStandard(saved, fresh))
        assertEquals(ReviewItemType.WHISKY, restored.items.single().type)
        assertEquals("catalog-whisky", restored.items.single().linkedProductId)
        assertTrue(PhotoReviewRules.problems(restored.items.single()).isNotEmpty())
        assertFalse(PhotoReviewRules.stats(restored).canPublish)
    }

    @Test fun regeneratedOperatorDraftRechecksNewlyGroupedSourceNullServings() {
        // A second OCR child row was merged. Its 60ml serving is a manual
        // master option and intentionally has no extractedOptionId.
        val master = ReviewItem(
            id = "master", name = "위스키", price = 14000.0,
            volume = 30.0, primarySourceOptionId = "ocr-a",
            options = listOf(ReviewOption(
                volume = 60.0, price = 22000.0,
                sourceOptionId = null, label = "잔",
            )),
            required = true,
        )
        val child = ReviewItem(
            id = "child", name = "위스키", excluded = true,
            required = false, mergedInto = "master",
        )
        val fresh = PhotoReviewState(items = listOf(master, child))
        val saved = ReviewDraftDto(7, 2, "2026-11-15T00:00:00Z", mapOf(
            "itemDecisions" to listOf(mapOf(
                "extractedItemId" to "master",
                "options" to listOf(mapOf(
                    "extractedOptionId" to "ocr-a",
                    "optionLabel" to "잔", "pourMl" to 30,
                    "priceKrw" to 15000,
                )),
            )),
        ))
        val restored = requireNotNull(ServerReviewDraftCodec.restoreStandard(
            saved, fresh, allowStaleIds = true))
        val line = restored.items.first()
        assertFalse(line.volumeChoicesConfirmed)
        assertEquals(setOf("ml:30", "ml:60"),
            line.volumeChoices.map(PhotoReviewRules::servingKey).toSet())
        assertEquals(setOf("ml:30"), line.chosenVolumeKeys)
        assertFalse(PhotoReviewRules.stats(restored).canPublish)
        val confirmed = PhotoReviewRules.confirmVolumeChoices(
            line.copy(chosenVolumeKeys = setOf("ml:30", "ml:60")))
        assertEquals(2, PhotoReviewRules.optionSummary(confirmed).size)
        assertEquals(15000.0, confirmed.price, 0.0)
        assertEquals(22000.0, confirmed.options.single().price, 0.0)
    }

    @Test fun regeneratedGroupedChildWithFormerPublishDecisionIsNotSilentlyRepublished() {
        val master = ReviewItem(id = "master", name = "위스키",
            price = 14000.0, volume = 30.0, primarySourceOptionId = "master-opt")
        val freshChild = ReviewItem(id = "child", name = "위스키",
            mergedInto = "master", excluded = true, required = false,
            price = 22000.0, volume = 60.0, primarySourceOptionId = "child-opt")
        val current = PhotoReviewState(items = listOf(master, freshChild))
        fun draft(action: String) = ReviewDraftDto(6, 2, "2026-11-15T00:00:00Z",
            mapOf("itemDecisions" to listOf(mapOf(
                "extractedItemId" to "child", "action" to action,
                "kind" to "whisky",
            ))))
        // A previously independent child publish choice cannot become a
        // hidden second publish after new OCR grouping.
        assertNull(ServerReviewDraftCodec.restoreStandard(
            draft("publish_without_product"), current, allowStaleIds = true))
        val reject = ReviewDraftDto(6, 2, "2026-11-15T00:00:00Z",
            mapOf("itemDecisions" to listOf(mapOf(
                "extractedItemId" to "child", "action" to "reject",
            ))))
        val safelyRestored = requireNotNull(ServerReviewDraftCodec.restoreStandard(
            reject, current, allowStaleIds = true))
        assertEquals("master", safelyRestored.items.last().mergedInto)
        assertTrue(safelyRestored.items.last().excluded)
        assertEquals(1, safelyRestored.items.count { it.mergedInto == null })
        val visible = PhotoReviewRules.stats(safelyRestored)
        assertTrue((visible.pending + visible.ready + visible.other + visible.excluded)
            .none { it.id == "child" })
    }

    @Test fun partialOperatorKindDecisionIsNotOverwrittenByFreshOcrKind() {
        val fresh = PhotoReviewState(items = listOf(ReviewItem(
            id = "line", name = "위스키", type = ReviewItemType.WHISKY,
        )))
        fun dto(fields: Map<String, Any?>) = ReviewDraftDto(
            3, 2, "2026-11-15T00:00:00Z",
            mapOf("itemDecisions" to listOf(
                mapOf("extractedItemId" to "line") + fields,
            )),
        )
        assertNull(ServerReviewDraftCodec.restoreStandard(dto(
            mapOf("kind" to "other")), fresh))
        assertNull(ServerReviewDraftCodec.restoreStandard(dto(
            mapOf("kind" to null)), fresh))
        assertNull(ServerReviewDraftCodec.restoreStandard(dto(
            mapOf("action" to "select_existing_product", "productId" to "catalog-a",
                "kind" to "other")), fresh))
        val complete = requireNotNull(ServerReviewDraftCodec.restoreStandard(dto(
            mapOf("action" to "publish_without_product", "kind" to "other")),
            fresh,
        )).items.single()
        assertEquals(ReviewItemType.OTHER, complete.type)
    }

    @Test fun operatorDraftSupportsFullServingPourRangeNotBarDefaultRange() {
        val fresh = PhotoReviewState(items = listOf(ReviewItem(
            id = "line", name = "위스키", price = 15000.0,
            primarySourceOptionId = "opt-1",
        )))
        fun draft(pour: Int) = ReviewDraftDto(4, 3, "2026-11-15T00:00:00Z",
            mapOf("itemDecisions" to listOf(mapOf(
                "extractedItemId" to "line",
                "options" to listOf(mapOf(
                    "extractedOptionId" to "opt-1", "priceKrw" to 15000,
                    "optionLabel" to "잔", "pourMl" to pour,
                )),
            ))))
        val restored = requireNotNull(ServerReviewDraftCodec.restoreStandard(
            draft(32767), fresh)).items.single()
        assertEquals(32767.0, restored.volume, 0.0)
        assertFalse(ReviewIssue.VOLUME in PhotoReviewRules.problems(restored))
        assertNull(ServerReviewDraftCodec.restoreStandard(draft(32768), fresh))
    }
}
