from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer


def _to_utc_string(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# The database session may return local time; the API always sends UTC RFC 3339 strings.
UtcDateTime = Annotated[datetime, PlainSerializer(_to_utc_string, return_type=str)]
