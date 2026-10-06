"""The generated OpenAPI document serves as the API reference, so keep it matching real responses."""

import pytest

from app.main import app

ERROR_REF = "#/components/schemas/ErrorResponse"


@pytest.fixture(scope="module")
def schema():
    return app.openapi()


@pytest.mark.parametrize(
    ("method", "path", "statuses"),
    [
        ("get", "/api/search/bars", {"422"}),
        ("get", "/api/bars/{barId}/menu", {"401", "404", "422"}),
        ("get", "/api/bars", {"401", "403", "422"}),
        ("get", "/api/bars/{barId}/menu-imports", {"401", "403", "404", "422"}),
        ("post", "/api/bars/{barId}/menu-imports", {"401", "403", "404", "409", "413", "415", "422"}),
        ("get", "/api/menu-imports/{menuImportId}", {"401", "403", "404", "422"}),
        ("post", "/api/menu-imports/{menuImportId}/review-and-apply", {"401", "403", "404", "409", "422", "503"}),
        ("get", "/api/catalog/brands", {"401", "403", "422"}),
        ("get", "/api/catalog/products", {"401", "403", "422"}),
    ],
)
def test_error_responses_use_the_common_format(schema, method, path, statuses):
    responses = schema["paths"][path][method]["responses"]

    documented = {status for status in responses if status not in {"200", "202"}}
    assert documented == statuses
    for status in statuses:
        assert responses[status]["content"]["application/json"]["schema"] == {"$ref": ERROR_REF}


def test_timestamps_are_documented_as_date_time(schema):
    properties = schema["components"]["schemas"]
    assert properties["SearchResultItem"]["properties"]["menuUpdatedAt"]["format"] == "date-time"
    assert {"type": "string", "format": "date-time"} in properties["BarMenuResponse"]["properties"]["publishedAt"]["anyOf"]


def test_menu_import_status_documents_every_response_shape(schema):
    success = schema["paths"]["/api/menu-imports/{menuImportId}"]["get"]["responses"]["200"]
    refs = {variant["$ref"].rsplit("/", 1)[-1] for variant in success["content"]["application/json"]["schema"]["anyOf"]}

    assert refs == {"ImportProcessingResponse", "ImportFailedResponse", "ImportReviewResponse", "ImportAppliedResponse"}


def test_upload_images_render_as_file_pickers(schema):
    """Swagger UI shows file inputs only for format: binary, not OpenAPI 3.1's contentMediaType."""
    body = schema["paths"]["/api/bars/{barId}/menu-imports"]["post"]["requestBody"]["content"]["multipart/form-data"]
    form = schema["components"]["schemas"][body["schema"]["$ref"].rsplit("/", 1)[-1]]

    assert form["properties"]["images"]["items"] == {"type": "string", "format": "binary"}
