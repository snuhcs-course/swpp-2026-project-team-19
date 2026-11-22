package com.zerotoone.bottlemap.ui.common

import kotlin.contracts.ExperimentalContracts
import kotlin.contracts.contract

/** Only local form validation supplies this app-owned copy. Never wrap server prose. */
internal class UserInputException(val notice: String) : IllegalArgumentException(notice)

@OptIn(ExperimentalContracts::class)
internal inline fun requireUserInput(value: Boolean, lazyMessage: () -> String) {
    contract { returns() implies value }
    if (!value) throw UserInputException(lazyMessage())
}
