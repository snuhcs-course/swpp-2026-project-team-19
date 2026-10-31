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
        ("get", "/api/search/bars", {"422", "500"}),
        ("get", "/api/search/nearby-bars", {"422", "500"}),
        ("get", "/api/search/bar-names", {"422", "500"}),
        ("get", "/api/search/map-bars", {"422", "500"}),
        ("get", "/api/bars/{barId}/menu", {"401", "404", "422", "500"}),
        ("get", "/api/bars", {"401", "403", "422", "500", "503"}),
        ("get", "/api/bars/{barId}/menu-imports", {"401", "403", "404", "422", "500", "503"}),
        (
            "post",
            "/api/bars/{barId}/menu-imports",
            {"401", "403", "404", "409", "413", "415", "422", "500", "503"},
        ),
        ("get", "/api/menu-imports/{menuImportId}", {"401", "403", "404", "422", "500", "503"}),
        (
            "post",
            "/api/menu-imports/{menuImportId}/review-and-apply",
            {"401", "403", "404", "409", "422", "500", "503"},
        ),
        ("get", "/api/catalog/brands", {"401", "403", "422", "500", "503"}),
        ("get", "/api/catalog/products", {"401", "403", "422", "500", "503"}),
        (
            "post",
            "/api/owner-applications/business-certificate-ocr",
            {"401", "413", "415", "422", "429", "500", "503"},
        ),
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



@pytest.mark.parametrize("model", ["BarMenuResponse", "SearchResultItem", "BarListItem"])
def test_bar_coordinates_are_documented_as_required_with_their_ranges(schema, model):
    component = schema["components"]["schemas"][model]
    properties = component["properties"]
    assert {"latitude", "longitude"} <= set(component["required"])
    assert (properties["latitude"]["type"], properties["latitude"]["minimum"], properties["latitude"]["maximum"]) == (
        "number",
        -90,
        90,
    )
    assert (properties["longitude"]["minimum"], properties["longitude"]["maximum"]) == (-180, 180)

@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/bars"),
        ("get", "/api/bars/{barId}/menu-imports"),
        ("post", "/api/bars/{barId}/menu-imports"),
        ("get", "/api/menu-imports/{menuImportId}"),
        ("post", "/api/menu-imports/{menuImportId}/review-and-apply"),
        ("get", "/api/catalog/brands"),
        ("get", "/api/catalog/products"),
    ],
)
def test_operator_routes_document_that_tokens_may_not_be_checkable(schema, method, path):
    description = schema["paths"][path][method]["responses"]["503"]["description"]

    assert "`SERVICE_UNAVAILABLE`" in description


def test_menu_import_status_documents_every_response_shape(schema):
    success = schema["paths"]["/api/menu-imports/{menuImportId}"]["get"]["responses"]["200"]
    refs = {variant["$ref"].rsplit("/", 1)[-1] for variant in success["content"]["application/json"]["schema"]["anyOf"]}

    assert refs == {
        "ImportProcessingResponse",
        "ImportFailedResponse",
        "ImportReviewResponse",
        "ImportAppliedResponse",
        "ImportCanceledResponse",
    }


def test_upload_images_render_as_file_pickers(schema):
    """Swagger UI shows file inputs only for format: binary, not OpenAPI 3.1's contentMediaType."""
    body = schema["paths"]["/api/bars/{barId}/menu-imports"]["post"]["requestBody"]["content"]["multipart/form-data"]
    form = schema["components"]["schemas"][body["schema"]["$ref"].rsplit("/", 1)[-1]]

    assert form["properties"]["images"]["items"] == {"type": "string", "format": "binary"}
