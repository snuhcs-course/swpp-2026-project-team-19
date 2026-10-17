# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #9); Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-18). Reviewed by Haeul Yang.
from datetime import datetime, timezone
from typing import Annotated

from pydantic import Field, PlainSerializer, WithJsonSchema


def _to_utc_string(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# The database session may return local time; the API always sends UTC RFC 3339 strings.
# Fractional seconds may be present, e.g. 2026-10-04T09:15:00.123456Z.
UtcDateTime = Annotated[
    datetime,
    PlainSerializer(_to_utc_string, return_type=str),
    WithJsonSchema({"type": "string", "format": "date-time"}),
]

# Bar coordinates (spec 2.1, 3.9.4): WGS84 decimal degrees, stored with up to 6 decimal places.
# Every bar has them; the bars table checks the same ranges.
Latitude = Annotated[float, Field(ge=-90, le=90, description="WGS84 latitude in decimal degrees; never null")]
Longitude = Annotated[float, Field(ge=-180, le=180, description="WGS84 longitude in decimal degrees; never null")]
