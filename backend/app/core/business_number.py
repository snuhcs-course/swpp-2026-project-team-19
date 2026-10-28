"""Korean business registration numbers (사업자등록번호): 10 digits, the last one a check digit.

The National Tax Service check digit: weight the first nine digits by 1, 3, 7, 1, 3, 7, 1, 3, 5,
add the tens digit of (ninth digit x 5), and the check digit is what brings the sum up to a
multiple of 10. Used by the certificate OCR (spec 3.11.12) and by owner applications (3.11.2).
"""

import re

WEIGHTS = (1, 3, 7, 1, 3, 7, 1, 3, 5)
_SEPARATORS = re.compile(r"[\s-]")


def check_digit(first_nine: str) -> int:
    digits = [int(c) for c in first_nine]
    total = sum(d * w for d, w in zip(digits, WEIGHTS)) + digits[8] * 5 // 10
    return (10 - total % 10) % 10


def is_valid_business_number(digits: str) -> bool:
    """True for exactly 10 ASCII digits whose last digit is the NTS check digit."""
    if len(digits) != 10 or not digits.isascii() or not digits.isdigit():
        return False
    return check_digit(digits[:9]) == int(digits[9])


def normalize_business_number(text: str) -> str | None:
    """The 10 digits with hyphens and spaces removed, or None if they are not a valid number."""
    digits = _SEPARATORS.sub("", text)
    return digits if is_valid_business_number(digits) else None
