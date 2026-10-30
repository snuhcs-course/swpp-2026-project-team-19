package com.zerotoone.bottlemap.ui.common

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.material3.rememberDatePickerState
import com.zerotoone.bottlemap.ui.theme.BottleMapShapes
import com.zerotoone.bottlemap.ui.theme.BottleMapSizes
import com.zerotoone.bottlemap.ui.theme.BottleMapSpacing

/**
 * Shared Owner UI primitives from the final HTML. These do not own networking or business
 * decisions. All selection and save callbacks must be supplied by the calling screen.
 */
@Composable
fun OwnerHeader(title: String, onBack: () -> Unit, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier.fillMaxWidth().defaultMinSize(minHeight = BottleMapSizes.minTouchTarget)
            .padding(horizontal = BottleMapSpacing.sm, vertical = BottleMapSpacing.xs),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = onBack) {
            BmIcon(BmIconId.BACK, contentDescription = "뒤로가기")
        }
        Text(
            text = title,
            style = MaterialTheme.typography.headlineSmall,
            color = MaterialTheme.colorScheme.onBackground,
            modifier = Modifier.weight(1f).padding(end = BottleMapSpacing.md),
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
fun OwnerActionButton(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    secondary: Boolean = false,
) {
    val shape = BottleMapShapes.button
    if (secondary) {
        OutlinedButton(
            onClick = onClick, enabled = enabled, shape = shape,
            modifier = modifier.defaultMinSize(minHeight = BottleMapSizes.secondaryButtonMinHeight),
        ) { Text(label) }
    } else {
        Button(
            onClick = onClick, enabled = enabled, shape = shape,
            modifier = modifier.defaultMinSize(minHeight = BottleMapSizes.primaryButtonMinHeight),
        ) { Text(label) }
    }
}

@Composable
fun OwnerTextInput(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    placeholder: String = "",
    error: String? = null,
    singleLine: Boolean = true,
) {
    OutlinedTextField(
        modifier = modifier.fillMaxWidth().defaultMinSize(minHeight = BottleMapSizes.searchFieldMinHeight),
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        placeholder = if (placeholder.isNotBlank()) ({ Text(placeholder) }) else null,
        singleLine = singleLine,
        isError = error != null,
        supportingText = error?.let { message -> { Text(message) } },
        shape = BottleMapShapes.textField,
    )
}

@Composable
fun OwnerMenuRow(
    title: String,
    subtitle: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    trailing: String? = null,
) {
    Row(
        modifier = modifier.fillMaxWidth().clickable(onClick = onClick)
            .defaultMinSize(minHeight = BottleMapSizes.minTouchTarget)
            .padding(vertical = BottleMapSpacing.md, horizontal = BottleMapSpacing.sm),
        horizontalArrangement = Arrangement.spacedBy(BottleMapSpacing.sm),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(BottleMapSpacing.xxs)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (trailing != null) {
            Text(trailing, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
        }
    }
}

enum class OwnerStatusTone { NEUTRAL, SUCCESS, ERROR, ATTENTION }

@Composable
fun OwnerStatusLabel(text: String, tone: OwnerStatusTone = OwnerStatusTone.NEUTRAL) {
    val scheme = MaterialTheme.colorScheme
    val foreground = when (tone) {
        OwnerStatusTone.NEUTRAL -> scheme.onSurfaceVariant
        OwnerStatusTone.SUCCESS -> scheme.tertiary
        OwnerStatusTone.ERROR -> scheme.error
        OwnerStatusTone.ATTENTION -> scheme.primary
    }
    Surface(shape = BottleMapShapes.chip, color = scheme.surfaceVariant) {
        Text(
            text, color = foreground, style = MaterialTheme.typography.labelMedium,
            modifier = Modifier.padding(horizontal = BottleMapSpacing.md, vertical = BottleMapSpacing.xs),
        )
    }
}

@Composable
fun OwnerConfirmationDialog(
    visible: Boolean,
    title: String,
    message: String,
    confirmLabel: String,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
) {
    if (!visible) return
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { Text(message) },
        confirmButton = { TextButton(onClick = onConfirm) { Text(confirmLabel) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("취소") } },
    )
}

internal fun validOwnerTime(hour: Int, minute: Int): Boolean =
    hour in 0..23 && minute in 0..55 && minute % 5 == 0

/**
 * Scrollable hour/minute wheels (5-minute increments). Selection is UI-only until the parent
 * persists a confirmed schedule. No automated save when a wheel is scrolled.
 */
@Composable
fun OwnerTimeWheel(
    hour: Int,
    minute: Int,
    onTimeChange: (Int, Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    val hourState = rememberLazyListState(initialFirstVisibleItemIndex = hour.coerceIn(0, 23))
    val minuteState = rememberLazyListState(initialFirstVisibleItemIndex = (minute / 5).coerceIn(0, 11))
    LaunchedEffect(hourState) {
        snapshotFlow { hourState.firstVisibleItemIndex }.collect { selected ->
            if (selected != hour && validOwnerTime(selected, minute)) onTimeChange(selected, minute)
        }
    }
    LaunchedEffect(minuteState) {
        snapshotFlow { minuteState.firstVisibleItemIndex * 5 }.collect { selected ->
            if (selected != minute && validOwnerTime(hour, selected)) onTimeChange(hour, selected)
        }
    }
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(BottleMapSpacing.sm),
    ) {
        listOf("시" to 24, "분" to 12).forEachIndexed { part, spec ->
            val state = if (part == 0) hourState else minuteState
            LazyColumn(
                state = state,
                modifier = Modifier.weight(1f).height(168.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                items(spec.second) { index ->
                    val value = if (part == 0) index else index * 5
                    val selected = if (part == 0) hour == value else minute == value
                    Text(
                        text = "%02d %s".format(value, spec.first),
                        style = if (selected) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyLarge,
                        color = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.fillMaxWidth()
                            .clickable { if (part == 0) onTimeChange(value, minute) else onTimeChange(hour, value) }
                            .padding(BottleMapSpacing.xs),
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun OwnerCalendarDialog(
    visible: Boolean,
    onDismiss: () -> Unit,
    onSelectDateUtcMillis: (Long) -> Unit,
) {
    if (!visible) return
    val state = rememberDatePickerState()
    DatePickerDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(onClick = {
                state.selectedDateMillis?.let(onSelectDateUtcMillis)
                onDismiss()
            }, enabled = state.selectedDateMillis != null) { Text("선택") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("취소") } },
    ) { DatePicker(state = state) }
}

@Composable
fun OwnerPhotoThumbnail(
    contentDescription: String,
    painter: Painter?,
    onRemove: (() -> Unit)?,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier.size(96.dp).background(MaterialTheme.colorScheme.surfaceVariant, BottleMapShapes.card),
        contentAlignment = Alignment.Center,
    ) {
        if (painter != null) {
            Image(painter, contentDescription, modifier = Modifier.matchParentSize(), contentScale = ContentScale.Crop)
        } else {
            BmIcon(BmIconId.CAMERA, contentDescription = contentDescription)
        }
        if (onRemove != null) {
            TextButton(onClick = onRemove, modifier = Modifier.align(Alignment.TopEnd)) { Text("삭제") }
        }
    }
}

@Composable
fun OwnerLoading(message: String, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier.fillMaxWidth().padding(BottleMapSpacing.xl),
        verticalArrangement = Arrangement.spacedBy(BottleMapSpacing.md),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        GlassFillLoading()
        Text(message, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
