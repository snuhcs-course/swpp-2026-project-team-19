package com.zerotoone.bottlemap.ui.owner

import android.content.Intent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.zerotoone.bottlemap.data.owner.MockOwnerLoadState
import com.zerotoone.bottlemap.data.owner.MockPhoto
import com.zerotoone.bottlemap.data.owner.MockPhotoKind
import com.zerotoone.bottlemap.ui.common.OwnerActionButton
import com.zerotoone.bottlemap.ui.common.OwnerHeader
import com.zerotoone.bottlemap.ui.common.OwnerLoading
import com.zerotoone.bottlemap.ui.theme.BottleMapSpacing
import java.util.UUID

/**
 * ACTION_FIRST_v4 photoEdit: two-column tiles, arrows among non-cover photos,
 * tap-to-open contextual actions, no drag, separate gallery-add header.
 *
 * Photo actions commit immediately to the same persistent Mock repository.
 * The information form remains a separate uncommitted draft, matching HTML.
 */
@Composable
fun OwnerPhotoHtmlV4Screen(
    state: MockOwnerLoadState,
    viewModel: OwnerMockViewModel,
    onBack: () -> Unit,
) {
    val bar = ownerInfoBar(state)?.second
    var menuPhotoId by rememberSaveable { mutableStateOf<String?>(null) }
    var deletePhotoId by rememberSaveable { mutableStateOf<String?>(null) }
    var error by rememberSaveable { mutableStateOf<String?>(null) }
    val context = LocalContext.current
    fun commit(photos: List<MockPhoto>) {
        val current = bar ?: return
        try {
            viewModel.saveBar(current.copy(gallery = photos))
            error = null
            menuPhotoId = null
        } catch (e: Exception) {
            error = e.message ?: "사진을 저장하지 못했어요. 다시 시도해 주세요."
        }
    }
    val picker = rememberLauncherForActivityResult(
        ActivityResultContracts.PickVisualMedia()
    ) { uri ->
        if (uri != null && bar != null) {
            try {
                context.contentResolver.takePersistableUriPermission(
                    uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            } catch (_: SecurityException) {
                // Some providers grant only transient access; do not claim durable access.
            }
            if (bar.gallery.none { it.uri == uri.toString() }) {
                commit(bar.gallery + MockPhoto(
                    UUID.randomUUID().toString(), uri.toString(), MockPhotoKind.BAR_GALLERY))
            }
        }
    }
    if (bar != null && deletePhotoId != null) {
        AlertDialog(
            onDismissRequest = { deletePhotoId = null },
            title = { Text("사진을 삭제할까요?") },
            text = { Text("삭제한 사진은 고객 화면에서도 바로 사라집니다.") },
            confirmButton = {
                TextButton(onClick = {
                    if (bar.gallery.size <= 1) {
                        error = "마지막 사진은 삭제할 수 없어요."
                    } else {
                        commit(bar.gallery.filterNot { it.photoId == deletePhotoId })
                    }
                    deletePhotoId = null
                }) { Text("삭제하기") }
            },
            dismissButton = {
                TextButton(onClick = { deletePhotoId = null }) { Text("취소") }
            },
        )
    }
    Column(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        OwnerHeader("사진 편집", onBack)
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(horizontal = BottleMapSpacing.screenHorizontal),
            verticalArrangement = Arrangement.spacedBy(13.dp),
        ) {
            if (bar == null) {
                when (state) {
                    is MockOwnerLoadState.Error -> {
                        Text(state.message, color = MaterialTheme.colorScheme.error)
                        OwnerActionButton("다시 시도", viewModel::retry)
                    }
                    MockOwnerLoadState.Loading -> OwnerLoading("매장 사진 불러오는 중")
                    else -> Text("관리할 매장이 없어요.")
                }
            } else {
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("매장 사진 편집", style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold)
                    OutlinedButton(onClick = {
                        picker.launch(PickVisualMediaRequest(
                            ActivityResultContracts.PickVisualMedia.ImageOnly))
                    }, modifier = Modifier.testTag("owner-photo-add")) {
                        Text("＋ 갤러리에서 추가", style = MaterialTheme.typography.labelSmall)
                    }
                }
                if (bar.gallery.isEmpty()) {
                    Text("등록된 사진이 없습니다. 갤러리에서 사진을 추가해 주세요.",
                        style = MaterialTheme.typography.bodySmall)
                }
                bar.gallery.chunked(2).forEachIndexed { rowIndex, rowPhotos ->
                    Row(Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        rowPhotos.forEachIndexed { column, photo ->
                            val index = rowIndex * 2 + column
                            Surface(
                                modifier = Modifier.weight(1f),
                                color = MaterialTheme.colorScheme.surface,
                                shape = RoundedCornerShape(12.dp),
                            ) {
                                Column(Modifier.padding(8.dp),
                                    verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                    Box(Modifier.fillMaxWidth().height(111.dp)) {
                                        // The image itself is clipped; the popup isn't clipped
                                        // by the image card, matching v17 HTML overflow safeguards.
                                        Box(
                                            Modifier.fillMaxSize()
                                                .clip(RoundedCornerShape(8.dp))
                                                .clickable { menuPhotoId = photo.photoId }
                                                .testTag("owner-photo-tile-" + index)
                                        ) {
                                            OwnerStoredPhoto(photo.uri, Modifier.fillMaxSize(),
                                                androidx.compose.ui.layout.ContentScale.Fit)
                                        }
                                        if (index == 0) {
                                            Text("대표", modifier = Modifier
                                                .align(Alignment.BottomStart)
                                                .background(MaterialTheme.colorScheme.surface)
                                                .padding(4.dp),
                                                style = MaterialTheme.typography.labelSmall)
                                        }
                                        DropdownMenu(
                                            expanded = menuPhotoId == photo.photoId,
                                            onDismissRequest = { menuPhotoId = null },
                                        ) {
                                            DropdownMenuItem(
                                                text = { Text("대표 사진 등록") },
                                                onClick = {
                                                    commit(makeCoverPhoto(bar.gallery, index))
                                                },
                                            )
                                            DropdownMenuItem(
                                                text = { Text("삭제하기") },
                                                onClick = {
                                                    menuPhotoId = null
                                                    deletePhotoId = photo.photoId
                                                },
                                            )
                                        }
                                    }
                                    Row(
                                        Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                                    ) {
                                        OutlinedButton(
                                            onClick = {
                                                commit(moveSecondaryBarPhoto(bar.gallery, index, -1))
                                            }, enabled = index > 1,
                                            modifier = Modifier.weight(1f).height(36.dp),
                                            contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp),
                                        ) { Text("←") }
                                        OutlinedButton(
                                            onClick = {
                                                commit(moveSecondaryBarPhoto(bar.gallery, index, 1))
                                            }, enabled = index > 0 && index < bar.gallery.lastIndex,
                                            modifier = Modifier.weight(1f).height(36.dp),
                                            contentPadding = androidx.compose.foundation.layout.PaddingValues(0.dp),
                                        ) { Text("→") }
                                    }
                                }
                            }
                        }
                        if (rowPhotos.size == 1) Spacer(Modifier.weight(1f))
                    }
                }
                error?.let {
                    Text(it, color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall)
                }
                OwnerActionButton("완료", onBack,
                    Modifier.fillMaxWidth().testTag("owner-photo-done"))
                Spacer(Modifier.height(20.dp))
            }
        }
    }
}
