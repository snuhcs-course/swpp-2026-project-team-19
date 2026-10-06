"""The generated OpenAPI document serves as the API reference, so keep it matching real responses."""

import pytest

from app.main import app

ERROR_REF = "#/components/schemas/ErrorResponse"


@pytest.fixture(scope="module")
def schema():
    return app.openapi()


@pytest.mark.parametrize(
    ("path", "statuses"),
    [("/api/search/bars", {"422"}), ("/api/bars/{barId}/menu", {"401", "404", "422"})],
)
def test_error_responses_use_the_common_format(schema, path, statuses):
    responses = schema["paths"][path]["get"]["responses"]

    documented = {status for status, response in responses.items() if status != "200"}
    assert documented == statuses
    for status in statuses:
        assert responses[status]["content"]["application/json"]["schema"] == {"$ref": ERROR_REF}


def test_timestamps_are_documented_as_date_time(schema):
    properties = schema["components"]["schemas"]
    assert properties["SearchResultItem"]["properties"]["menuUpdatedAt"]["format"] == "date-time"
    assert {"type": "string", "format": "date-time"} in properties["BarMenuResponse"]["properties"]["publishedAt"]["anyOf"]
