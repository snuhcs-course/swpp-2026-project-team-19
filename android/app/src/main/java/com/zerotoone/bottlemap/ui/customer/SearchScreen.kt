// AI-assisted implementation draft (2026-10-13, I2-P13). Human build/review pending.
package com.zerotoone.bottlemap.ui.customer

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import android.content.pm.PackageManager
import android.Manifest
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.zerotoone.bottlemap.data.NearbyBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp

private const val MAX_QUERY_LENGTH = 100

@Composable
fun SearchScreen(
    onOpenResults: (String) -> Unit,
    onOpenAccount: () -> Unit = {},
    onOpenNearby: () -> Unit = {},
    nearbyViewModel: NearbyBarsViewModel? = null,
    serverValidationErrorCode: String? = null,
    onClearServerValidation: () -> Unit = {},
) {
    var query by rememberSaveable { mutableStateOf("") }
    var navigating by rememberSaveable { mutableStateOf(false) }
    // Reset the one-shot navigation guard when returning from Search Results.
    LaunchedEffect(Unit) { navigating = false }
    LaunchedEffect(serverValidationErrorCode) {
        if (serverValidationErrorCode != null) navigating = false
    }
    val normalizedInput = query.trim()
    val tooLong = normalizedInput.length > MAX_QUERY_LENGTH
    val canSearch = normalizedInput.isNotEmpty() && !tooLong &&
        !navigating && serverValidationErrorCode == null
    val keyboard = LocalSoftwareKeyboardController.current
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val nearbyState = nearbyViewModel?.state?.collectAsStateWithLifecycle()?.value
    val selectedNearbyId = nearbyViewModel?.selectedBarId?.collectAsStateWithLifecycle()?.value
    val nearbyBars = (nearbyState as? NearbyUiState.Success)?.bars.orEmpty()

    // Home preview never starts location acquisition without user action.
    // When coming back from Android Settings, revoke a stale preview if precise
    // permission has been removed; the Nearby route remains opt-in.
    DisposableEffect(lifecycleOwner, nearbyViewModel) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME &&
                nearbyViewModel != null &&
                ContextCompat.checkSelfPermission(
                    context, Manifest.permission.ACCESS_FINE_LOCATION,
                ) != PackageManager.PERMISSION_GRANTED
            ) {
                nearbyViewModel.updatePermission(NearbyPermission.NONE)
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    val submit = {
        if (canSearch) {
            navigating = true
            keyboard?.hide()
            onOpenResults(normalizedInput)
        }
    }

    I2CustomerSearchTheme {
        SearchContent(
            query = query,
            tooLong = tooLong,
            canSearch = canSearch,
            isNavigating = navigating,
            serverValidationErrorCode = serverValidationErrorCode,
            onQueryChange = {
                query = it
                onClearServerValidation()
            },
            onClear = {
                query = ""
                onClearServerValidation()
            },
            onSearch = submit,
            onOpenAccount = onOpenAccount,
            onOpenNearby = onOpenNearby,
            nearbyBars = nearbyBars,
            selectedNearbyBarId = selectedNearbyId,
            onSelectNearbyBar = { id ->
                if (nearbyViewModel?.selectBar(id) == true) onOpenNearby()
            },
        )
    }
}

@Composable
private fun SearchContent(
    query: String,
    tooLong: Boolean,
    canSearch: Boolean,
    isNavigating: Boolean,
    serverValidationErrorCode: String?,
    onQueryChange: (String) -> Unit,
    onClear: () -> Unit,
    onSearch: () -> Unit,
    onOpenAccount: () -> Unit,
    onOpenNearby: () -> Unit,
    nearbyBars: List<NearbyBar> = emptyList(),
    selectedNearbyBarId: String? = null,
    onSelectNearbyBar: (String) -> Unit = {},
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
    ) {
        Surface(
            color = MaterialTheme.colorScheme.background,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "◉ BottleMap",
                    color = MaterialTheme.colorScheme.onBackground,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                )
                TextButton(onClick = onOpenAccount) { Text("마이페이지") }
            }
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 22.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(
                text = "DISCOVER YOUR POUR",
                color = MaterialTheme.colorScheme.primary,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = "찾는 위스키, 어디에서 마실까요?",
                color = MaterialTheme.colorScheme.onBackground,
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = "위스키 이름으로 취급하는 바를 찾아보세요.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                text = "위스키 검색",
                color = MaterialTheme.colorScheme.onBackground,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(top = 12.dp),
            )

            OutlinedTextField(
                value = query,
                onValueChange = onQueryChange,
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                enabled = !isNavigating,
                placeholder = { Text("위스키 이름 입력") },
                leadingIcon = { Text("⌕") },
                trailingIcon = {
                    if (query.isNotEmpty()) {
                        TextButton(onClick = onClear) { Text("지우기") }
                    }
                },
                isError = tooLong || serverValidationErrorCode != null,
                supportingText = if (tooLong || serverValidationErrorCode != null) {
                    {
                        Text(if (tooLong) "검색어는 공백 제외 100자 이하여야 합니다."
                            else searchValidationMessage(requireNotNull(serverValidationErrorCode)))
                    }
                } else null,
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Text,
                    imeAction = ImeAction.Search,
                ),
                keyboardActions = KeyboardActions(onSearch = { if (canSearch) onSearch() }),
            )

            Button(
                onClick = onSearch,
                enabled = canSearch,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("판매하는 바 찾기")
            }
            // I2 Figma S0/S1: an actual nearby carousel alongside a map tile.
            // Populate only after a user deliberately granted precise location
            // and the A9 public backend returned complete results.
            Text(
                text = "내 주변 바",
                color = MaterialTheme.colorScheme.onBackground,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(top = 8.dp),
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                if (nearbyBars.isNotEmpty()) {
                    LazyRow(
                        modifier = Modifier.weight(2f).height(150.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        items(nearbyBars, key = { it.barId }) { bar ->
                            OutlinedCard(
                                onClick = { onSelectNearbyBar(bar.barId) },
                                modifier = Modifier.width(186.dp).height(150.dp),
                                border = BorderStroke(
                                    if (bar.barId == selectedNearbyBarId) 2.dp else 1.dp,
                                    if (bar.barId == selectedNearbyBarId)
                                        MaterialTheme.colorScheme.primary
                                    else MaterialTheme.colorScheme.outlineVariant,
                                ),
                            ) {
                                Column(
                                    modifier = Modifier.padding(12.dp),
                                    verticalArrangement = Arrangement.spacedBy(5.dp),
                                ) {
                                    Text("NEARBY · 1km", style = MaterialTheme.typography.labelSmall)
                                    Text(
                                        bar.name,
                                        maxLines = 1,
                                        style = MaterialTheme.typography.titleSmall,
                                    )
                                    Text(
                                        "${bar.distanceMeters.toInt()}m",
                                        color = MaterialTheme.colorScheme.primary,
                                    )
                                    Text(
                                        bar.address,
                                        maxLines = 1,
                                        style = MaterialTheme.typography.labelSmall,
                                    )
                                    Text(
                                        bar.menuUpdatedAt?.let(::formatMenuTimestamp)
                                            ?: "아직 등록된 메뉴 없음",
                                        style = MaterialTheme.typography.labelSmall,
                                    )
                                }
                            }
                        }
                    }
                } else {
                    OutlinedCard(
                        onClick = onOpenNearby,
                        modifier = Modifier.weight(2f).height(150.dp),
                    ) {
                        Column(
                            modifier = Modifier.padding(12.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            Text("NEARBY · 1km", style = MaterialTheme.typography.labelSmall)
                            Text(
                                "현재 위치로 내 주변 바를 확인해 보세요.",
                                style = MaterialTheme.typography.bodySmall,
                            )
                            Text(
                                "위치 사용하고 보기 →",
                                style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.primary,
                            )
                        }
                    }
                }
                OutlinedCard(
                    onClick = onOpenNearby,
                    modifier = Modifier.weight(1.1f).height(150.dp),
                ) {
                    Column(
                        modifier = Modifier.padding(10.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Text("⌖", style = MaterialTheme.typography.headlineMedium)
                        Text("주변 바", style = MaterialTheme.typography.titleSmall)
                        Text(
                            "지도에서 보기 →",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.primary,
                        )
                    }
                }
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun I2SearchInitialPreview() {
    I2CustomerSearchTheme {
        SearchContent("", false, false, false, null, {}, {}, {}, {}, {})
    }
}

@Preview(showBackground = true)
@Composable
private fun I2SearchEnteredPreview() {
    I2CustomerSearchTheme {
        SearchContent("Deanston 12", false, true, false, null, {}, {}, {}, {}, {})
    }
}

/** This mapping is display-only. The backend remains the validation authority. */
internal fun searchValidationMessage(fieldCode: String): String = when (fieldCode) {
    "MISSING", "BLANK" -> "검색어를 입력해 주세요."
    "STRING_TOO_LONG" -> "검색어는 100자 이하여야 합니다."
    "NOT_SEARCHABLE" -> "검색할 수 있는 문자가 없습니다. 제품명을 입력해 주세요."
    else -> "검색어를 확인해 주세요."
}
