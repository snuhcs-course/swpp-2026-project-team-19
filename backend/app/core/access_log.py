# AI-generated with Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-19). Reviewed by Haeul Yang.
"""Keep the customer's location out of uvicorn's access log.

The search APIs take the location as `lat`/`lng` query parameters (spec 3.10, 3.12). The server
does not store it, and the access log in journald should not keep it either. Each access line drops
those two parameters and keeps the rest of the query, such as the search text, for later analysis.
"""

import logging
from urllib.parse import unquote_plus

ACCESS_LOGGER = "uvicorn.access"
LOCATION_PARAMS = frozenset({"lat", "lng"})


def without_location(path: str) -> str:
    """The path with every `lat` and `lng` parameter removed; the other parameters stay as sent."""
    base, sep, query = path.partition("?")
    if not sep:
        return path
    # Compare decoded names, as the API does, so that `l%61t=` is removed too.
    kept = [p for p in query.split("&") if unquote_plus(p.partition("=")[0]) not in LOCATION_PARAMS]
    return f"{base}?{'&'.join(kept)}" if kept else base


class StripLocation(logging.Filter):
    """Rewrites uvicorn's access record: `'%s - "%s %s HTTP/%s" %d'` with the path third."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            record.args = (*args[:2], without_location(args[2]), *args[3:])
        return True


def strip_location_from_access_log() -> None:
    """Install the filter once; uvicorn has configured its loggers before it imports the app."""
    logger = logging.getLogger(ACCESS_LOGGER)
    if not any(isinstance(f, StripLocation) for f in logger.filters):
        logger.addFilter(StripLocation())
