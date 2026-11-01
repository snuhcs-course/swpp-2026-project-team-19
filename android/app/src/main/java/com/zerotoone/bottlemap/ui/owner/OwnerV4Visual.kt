package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
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
                .heightIn(min = if (singleLine) 45.dp else 75.dp)
                .background(V4Color.elevated, RoundedCornerShape(9.dp))
                .border(1.dp, V4Color.line, RoundedCornerShape(9.dp))
                .padding(horizontal = 12.dp, vertical = 11.dp),
            textStyle = TextStyle(fontSize = 14.sp, color = V4Color.text, lineHeight = 20.sp),
            decorationBox = { inner ->
                Box {
                    if (value.isEmpty() && placeholder.isNotEmpty()) {
                        Text(placeholder, color = Color(0xFFA69B91), fontSize = 13.sp)
                    }
                    inner()
                }
            }
        )
    }
}
