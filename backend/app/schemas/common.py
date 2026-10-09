# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #9). Reviewed by Haeul Yang.
from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer, WithJsonSchema


def _to_utc_string(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# The database session may return local time; the API always sends UTC RFC 3339 strings.
# Fractional seconds may be present, e.g. 2026-10-04T09:15:00.123456Z.
UtcDateTime = Annotated[
    datetime,
    PlainSerializer(_to_utc_string, return_type=str),
    WithJsonSchema({"type": "string", "format": "date-time"}),
]
