package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.height
import androidx.compose.ui.Alignment
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Exact manager HTML CSS palette (ACTION_FIRST_v4 MANAGER_DOCUMENT). */
internal object V4Color {
    val background = Color(0xFF211E1B)
    val surface = Color(0xFF302B27)
    val elevated = Color(0xFF3A332E)
    val primary = Color(0xFFC99D6B)
    val text = Color(0xFFF2EDE8)
    val sub = Color(0xFFC7BBB0)
    val line = Color(0xFF51473F)
    val positive = Color(0xFFB9DFC8)
}
@Composable
internal fun V4FormField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    placeholder: String = "",
    singleLine: Boolean = true,
    keyboardType: KeyboardType = KeyboardType.Text,
    testTag: String? = null
) {
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(5.dp)) {
        Text(label, color = V4Color.text, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
        BasicTextField(
            value = value, onValueChange = onValueChange,
            singleLine = singleLine,
            keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
            modifier = Modifier.fillMaxWidth()
                .then(if (testTag == null) Modifier else Modifier.testTag(testTag))
                .height(if (singleLine) 43.dp else 75.dp)
                .background(V4Color.elevated, RoundedCornerShape(9.dp))
                .border(1.dp, V4Color.line, RoundedCornerShape(9.dp))
                .padding(horizontal = 12.dp, vertical = if (singleLine) 0.dp else 11.dp),
            textStyle = TextStyle(fontSize = 14.sp, color = V4Color.text, lineHeight = 20.sp),
            decorationBox = { inner ->
                Box(Modifier.fillMaxWidth().then(if (singleLine) Modifier.height(43.dp)
                    else Modifier), contentAlignment = if (singleLine) Alignment.CenterStart else Alignment.TopStart) {
                    if (value.isEmpty() && placeholder.isNotEmpty()) {
                        Text(placeholder, color = Color(0xFFA69B91), fontSize = 13.sp)
                    }
                    inner()
                }
            }
        )
    }
}

@Composable
internal fun V4CompactCheck(label: String, checked: Boolean, onChange: (Boolean)->Unit) {
    val focus = LocalFocusManager.current
    val keyboard = LocalSoftwareKeyboardController.current
    val interaction = remember { MutableInteractionSource() }
    Row(verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.clickable(interactionSource = interaction, indication = null) {
            focus.clearFocus()
            keyboard?.hide()
            onChange(!checked)
        },
        horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Box(Modifier.size(15.dp).background(if (checked) V4Color.primary else
            V4Color.elevated, RoundedCornerShape(4.dp))
            .border(1.dp, V4Color.line, RoundedCornerShape(4.dp)),
            contentAlignment = Alignment.Center) {
            if (checked) Canvas(Modifier.size(11.dp)) {
                val check = Path().apply {
                    moveTo(size.width * 0.14f, size.height * 0.50f)
                    lineTo(size.width * 0.40f, size.height * 0.72f)
                    lineTo(size.width * 0.87f, size.height * 0.25f)
                }
                drawPath(check, V4Color.background, style = Stroke(
                    width = 2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
            }
        }
        Text(label, color = V4Color.sub, fontSize = 11.sp, maxLines = 1)
    }
}

@Composable
internal fun V4HourButton(text: String, onClick: ()->Unit, modifier: Modifier = Modifier) {
    Box(modifier.width(75.dp).height(35.dp)
        .background(V4Color.elevated, RoundedCornerShape(6.dp))
        .border(1.dp, V4Color.line, RoundedCornerShape(6.dp))
        .clickable(onClick = onClick), contentAlignment = Alignment.Center) {
        Text(text, color = V4Color.text, fontSize = 11.sp, maxLines = 1,
            textAlign = TextAlign.Center)
    }
}

/** HTML top bar: small section caption next to a standalone back arrow. */
@Composable
internal fun V4Toolbar(title: String?, onBack: () -> Unit) {
    Row(Modifier.fillMaxWidth().height(52.dp).background(V4Color.background)
        .padding(horizontal = 16.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        val focus = LocalFocusManager.current
        val keyboard = LocalSoftwareKeyboardController.current
        val backInteraction = remember { MutableInteractionSource() }
        Box(Modifier.size(40.dp).clickable(interactionSource = backInteraction,
            indication = null) {
                focus.clearFocus()
                keyboard?.hide()
                onBack()
            }.semantics { contentDescription = "뒤로가기" },
            contentAlignment = Alignment.Center) {
            Text("←", color = V4Color.text, fontSize = 26.sp, lineHeight = 28.sp)
        }
        if (title != null) Text(title, color = V4Color.sub,
            fontSize = 12.sp, fontWeight = FontWeight.Medium)
    }
}

@Composable
internal fun V4SearchField(value: String, onChange: (String) -> Unit, tag: String, hint: String) {
    Row(Modifier.fillMaxWidth().heightIn(min = 52.dp)
        .background(V4Color.elevated, RoundedCornerShape(9.dp))
        .border(1.dp, V4Color.line, RoundedCornerShape(9.dp))
        .padding(horizontal = 13.dp, vertical = 13.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("⌕", color = V4Color.sub, fontSize = 21.sp, lineHeight = 22.sp)
        BasicTextField(
            value = value, onValueChange = onChange, singleLine = true,
            modifier = Modifier.weight(1f).testTag(tag),
            textStyle = TextStyle(fontSize = 13.sp, color = V4Color.text),
            decorationBox = { inner ->
                Box {
                    if (value.isEmpty()) Text(hint, fontSize = 13.sp,
                        color = Color(0xFF938780))
                    inner()
                }
            }
        )
    }
}

@Composable
internal fun V4TagChip(label: String, selected: Boolean = false, onClick: ()->Unit) {
    Box(
        Modifier.background(if (selected) Color(0xFF4A382A) else V4Color.elevated,
            RoundedCornerShape(7.dp))
            .border(1.dp, if (selected) V4Color.primary else V4Color.line,
                RoundedCornerShape(7.dp))
            .clickable(onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 7.dp)
    ) {
        Text(label, fontSize = 12.sp, color = if (selected) Color(0xFFF7DFBF)
            else V4Color.text, lineHeight = 17.sp)
    }
}
