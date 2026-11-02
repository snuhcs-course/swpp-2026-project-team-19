package com.zerotoone.bottlemap.ui.owner

import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.TextFieldValue
import org.junit.Assert.assertEquals
import org.junit.Test

/** Prevents the cursor jumping to a stale offset as auto-hyphens appear. */
class OwnerRegistrationPhoneInputTest {
    @Test fun insertingInMiddlePreservesDigitRelativeCaret() {
        val previous=TextFieldValue("010-1234",selection=TextRange(4))
        val incoming=TextFieldValue("010-91234",selection=TextRange(5))
        val result=ownerPhoneEdit(previous,incoming)
        assertEquals("010-912-34",result.text)
        assertEquals(5,result.selection.start)
    }

    @Test fun appendingDoesNotMoveCursorBeforeAutoInsertedHyphen() {
        val before=TextFieldValue("010",selection=TextRange(3))
        val typed=TextFieldValue("0101",selection=TextRange(4))
        val result=ownerPhoneEdit(before,typed)
        assertEquals("010-1",result.text)
        assertEquals(result.text.length,result.selection.start)
    }

    @Test fun backspacingAutoHyphenActuallyRemovesPrecedingDigit() {
        val before=TextFieldValue("010-1234",selection=TextRange(4))
        val after=TextFieldValue("0101234",selection=TextRange(3))
        val result=ownerPhoneEdit(before,after)
        assertEquals("011-234",result.text)
        assertEquals(2,result.selection.start)
    }

    @Test fun areaAndSafeNumberPrefixesKeepTheirOwnGroupLengths() {
        val area=ownerPhoneEdit(TextFieldValue("02-123",selection=TextRange(6)),
            TextFieldValue("02-1234",selection=TextRange(7)))
        assertEquals("02-1234",area.text)
        assertEquals(area.text.length,area.selection.start)
        val safe=ownerPhoneEdit(TextFieldValue("0507",selection=TextRange(4)),
            TextFieldValue("05071",selection=TextRange(5)))
        assertEquals("0507-1",safe.text)
        assertEquals(safe.text.length,safe.selection.start)
    }

    @Test fun pureCaretMappingDoesNotConfuseHyphensWithDigits() {
        assertEquals(0,ownerPhoneCaretOffset("010-1234",0))
        assertEquals(4,ownerPhoneCaretOffset("010-1234",3))
        assertEquals(7,ownerPhoneCaretOffset("010-1234",6))
    }
}
