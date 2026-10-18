# AI-generated with Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-19). Reviewed by Haeul Yang.
"""Keep query strings out of uvicorn's access log.

The search APIs take the customer's location as `lat`/`lng` query parameters (spec 3.10, 3.12).
The server does not store it, and the access log in journald should not keep it either, so each
access line keeps the method, path and status but drops everything after `?`.
"""

import logging

ACCESS_LOGGER = "uvicorn.access"


class StripQueryString(logging.Filter):
    """Rewrites uvicorn's access record: `'%s - "%s %s HTTP/%s" %d'` with the path third."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            record.args = (*args[:2], args[2].split("?", 1)[0], *args[3:])
        return True


def strip_query_strings_from_access_log() -> None:
    """Install the filter once; uvicorn has configured its loggers before it imports the app."""
    logger = logging.getLogger(ACCESS_LOGGER)
    if not any(isinstance(f, StripQueryString) for f in logger.filters):
        logger.addFilter(StripQueryString())
