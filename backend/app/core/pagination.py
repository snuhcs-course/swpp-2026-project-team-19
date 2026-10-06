"""Opaque cursors for keyset pagination.

A cursor holds the sort key of the last item of a page (e.g. [name, id]); the next page
starts after it, so rows added or removed meanwhile do not shift or repeat items. Clients
pass `nextCursor` back unchanged and must not read it.
"""

import base64
import binascii
import json
from collections.abc import Callable
from typing import Any, TypeVar

from app.core.errors import validation_failed

T = TypeVar("T")


def encode_cursor(values: list[Any]) -> str:
    raw = json.dumps(values, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, parse: Callable[[list[Any]], T]) -> T:
    """`parse` turns the stored values back into the sort key and raises ValueError,
    TypeError or IndexError when they do not fit; any failure is 422 INVALID_CURSOR."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        values = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if not isinstance(values, list):
            raise TypeError("not a list")
        return parse(values)
    except (ValueError, TypeError, IndexError, UnicodeError, binascii.Error):
        raise validation_failed(
            "cursor", "INVALID_CURSOR", "다음 페이지 정보가 올바르지 않습니다. 처음부터 다시 조회해 주세요."
        ) from None
