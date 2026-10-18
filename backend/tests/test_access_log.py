# AI-generated with Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-19). Reviewed by Haeul Yang.
import logging

import pytest

import app.main  # noqa: F401  (importing the app installs the filter)
from app.core.access_log import ACCESS_LOGGER, StripQueryString, strip_query_strings_from_access_log

# The format uvicorn's HTTP protocols use for access lines.
UVICORN_FORMAT = '%s - "%s %s HTTP/%s" %d'


def access_record(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        ACCESS_LOGGER, logging.INFO, __file__, 1, UVICORN_FORMAT, ("1.2.3.4:5678", "GET", path, "1.1", 200), None
    )


@pytest.mark.parametrize(
    ("path", "logged"),
    [
        ("/api/search/nearby-bars?lat=37.4781&lng=126.959&radiusMeters=500", "/api/search/nearby-bars"),
        ("/api/search/bars?query=%EA%B8%80&lat=37.478&lng=126.951", "/api/search/bars"),
        ("/api/bars/abc/menu", "/api/bars/abc/menu"),
    ],
)
def test_the_access_line_keeps_the_path_but_not_the_query(path, logged):
    record = access_record(path)

    assert StripQueryString().filter(record) is True
    assert record.getMessage() == f'1.2.3.4:5678 - "GET {logged} HTTP/1.1" 200'


def test_other_records_are_left_alone():
    record = logging.LogRecord(ACCESS_LOGGER, logging.INFO, __file__, 1, "plain %s", ("a?b",), None)

    assert StripQueryString().filter(record) is True
    assert record.getMessage() == "plain a?b"


def test_the_app_installs_the_filter_once():
    strip_query_strings_from_access_log()

    filters = logging.getLogger(ACCESS_LOGGER).filters
    assert sum(isinstance(f, StripQueryString) for f in filters) == 1


def test_a_logged_request_has_no_location(caplog):
    logger = logging.getLogger(ACCESS_LOGGER)

    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        logger.info(UVICORN_FORMAT, "1.2.3.4:5678", "GET", "/api/search/nearby-bars?lat=37.4781&lng=126.959", "1.1", 200)

    assert caplog.messages == ['1.2.3.4:5678 - "GET /api/search/nearby-bars HTTP/1.1" 200']
