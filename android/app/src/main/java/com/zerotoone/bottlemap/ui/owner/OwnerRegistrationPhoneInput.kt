package com.zerotoone.bottlemap.ui.owner

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Keeps the caret at the same *digit*, rather than at a stale string offset
 * when a 02/010/0507 separator is inserted or removed. */
internal fun ownerPhoneCaretOffset(formatted:String, digitCount:Int):Int {
    if(digitCount<=0)return 0
    var seen=0
    for(index in formatted.indices) {
        if(formatted[index].isDigit())seen++
        if(seen==digitCount) {
            val right=index+1
            return if(right<formatted.length && formatted[right]=='-')right+1 else right
        }
    }
    return formatted.length
}
internal fun ownerPhoneEdit(
    previous:TextFieldValue,incoming:TextFieldValue
):TextFieldValue {
    val before=ownerPhoneDigits(previous.text)
    var digits=ownerPhoneDigits(incoming.text)
    var position=incoming.text.take(incoming.selection.end).count(Char::isDigit)
    // Android IMEs delete the hyphen without deleting a digit. Treat Backspace
    // on that separator as deleting the preceding digit, not as an inert edit.
    val backspaceAt = previous.selection.start - 1
    val deletedSeparator =
        previous.selection.collapsed && incoming.selection.collapsed &&
        backspaceAt >= 0 && previous.text[backspaceAt] == '-' &&
        incoming.text.length == previous.text.length - 1 &&
        incoming.selection.start == backspaceAt &&
        incoming.text == previous.text.removeRange(backspaceAt, backspaceAt + 1)
    if(digits==before && deletedSeparator) {
        val remove=(position-1).coerceAtLeast(0)
        if(remove<digits.length) {
            digits=digits.removeRange(remove,remove+1)
            position=remove
        }
    }
    val formatted=formatOwnerPhone(digits)
    val cursor=ownerPhoneCaretOffset(formatted,position.coerceAtMost(digits.length))
    return TextFieldValue(formatted,selection=TextRange(cursor))
}

/** Local phone field (public shop/private applicant). Only numeric digits
 * are saved into the Mock draft. Selection is kept as Compose TextFieldValue. */
@Composable
internal fun RegistrationPhoneInput(
    digits:String,onDigitsChange:(String)->Unit,placeholder:String,tag:String
) {
    val initial=formatOwnerPhone(digits)
    var field by rememberSaveable(stateSaver=TextFieldValue.Saver) {
        mutableStateOf(TextFieldValue(initial,selection=TextRange(initial.length)))
    }
    var focused by androidx.compose.runtime.remember {
        androidx.compose.runtime.mutableStateOf(false)
    }
    LaunchedEffect(digits) {
        if(ownerPhoneDigits(field.text)!=ownerPhoneDigits(digits)) {
            val newText=formatOwnerPhone(digits)
            field=TextFieldValue(newText,selection=TextRange(newText.length))
        }
    }
    BasicTextField(
        value=field,
        onValueChange={ incoming ->
            val next=ownerPhoneEdit(field,incoming)
            field=next
            val normalized=ownerPhoneDigits(next.text)
            if(normalized!=ownerPhoneDigits(digits)) onDigitsChange(normalized)
        },
        singleLine=true,
        keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Phone),
        modifier=Modifier.fillMaxWidth().height(56.dp).testTag(tag)
            .background(RegistrationV4.surface,RoundedCornerShape(12.dp))
            .border(1.dp,if(focused)RegistrationV4.primary else RegistrationV4.border,
                RoundedCornerShape(12.dp))
            .onFocusChanged { focused=it.isFocused }
            .padding(horizontal=16.dp),
        textStyle=TextStyle(color=RegistrationV4.text,fontSize=16.sp,lineHeight=24.sp),
        decorationBox={inner ->
            Box(Modifier.fillMaxWidth().height(56.dp),contentAlignment=Alignment.CenterStart) {
                if(field.text.isEmpty()) androidx.compose.material3.Text(
                    placeholder,color=RegistrationV4.muted,fontSize=16.sp,lineHeight=24.sp)
                inner()
            }
        }
    )
}
