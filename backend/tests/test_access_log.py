# AI-generated with Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-19, 2026-10-21). Reviewed by Haeul Yang.
import logging

import pytest

import app.main  # noqa: F401  (importing the app installs the filter)
from app.core.access_log import ACCESS_LOGGER, StripLocation, strip_location_from_access_log, without_location

# The format uvicorn's HTTP protocols use for access lines.
UVICORN_FORMAT = '%s - "%s %s HTTP/%s" %d'


@pytest.mark.parametrize(
    ("path", "logged"),
    [
        ("/api/search/nearby-bars?lat=37.4781&lng=126.959&radiusMeters=500", "/api/search/nearby-bars?radiusMeters=500"),
        ("/api/search/nearby-bars?lat=37.4781&lng=126.959", "/api/search/nearby-bars"),
        ("/api/search/bars?query=%EA%B8%80&lat=37.478&lng=126.951&limit=20", "/api/search/bars?query=%EA%B8%80&limit=20"),
        # Repeated, empty or percent-encoded names are location too.
        ("/api/search/bars?lat=1&lat=2&query=x&lng=&l%61t=3", "/api/search/bars?query=x"),
        # Names that only contain lat or lng are kept.
        ("/api/search/bars?query=latte&latitude=1&flat=2", "/api/search/bars?query=latte&latitude=1&flat=2"),
        ("/api/search/map-bars?south=37.47&west=126.94&north=37.49&east=126.97", "/api/search/map-bars"),
        ("/api/search/bar-names?query=%EB%B3%B5&limit=20", "/api/search/bar-names?query=%EB%B3%B5&limit=20"),
        ("/api/bars/abc/menu", "/api/bars/abc/menu"),
        ("/api/bars?", "/api/bars?"),
    ],
)
def test_location_parameters_are_dropped_and_the_rest_kept(path, logged):
    assert without_location(path) == logged


def test_the_access_record_is_rewritten():
    record = logging.LogRecord(
        ACCESS_LOGGER,
        logging.INFO,
        __file__,
        1,
        UVICORN_FORMAT,
        ("1.2.3.4:5678", "GET", "/api/search/bars?query=x&lat=37.4&lng=126.9", "1.1", 200),
        None,
    )

    assert StripLocation().filter(record) is True
    assert record.getMessage() == '1.2.3.4:5678 - "GET /api/search/bars?query=x HTTP/1.1" 200'


def test_other_records_are_left_alone():
    record = logging.LogRecord(ACCESS_LOGGER, logging.INFO, __file__, 1, "plain %s", ("a?lat=1",), None)

    assert StripLocation().filter(record) is True
    assert record.getMessage() == "plain a?lat=1"


def test_the_app_installs_the_filter_once():
    strip_location_from_access_log()

    filters = logging.getLogger(ACCESS_LOGGER).filters
    assert sum(isinstance(f, StripLocation) for f in filters) == 1


def test_a_logged_request_has_no_location(caplog):
    logger = logging.getLogger(ACCESS_LOGGER)

    with caplog.at_level(logging.INFO, logger=ACCESS_LOGGER):
        logger.info(UVICORN_FORMAT, "1.2.3.4:5678", "GET", "/api/search/nearby-bars?lat=37.4781&lng=126.959", "1.1", 200)

    assert caplog.messages == ['1.2.3.4:5678 - "GET /api/search/nearby-bars HTTP/1.1" 200']
