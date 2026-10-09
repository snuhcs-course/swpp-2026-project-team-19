# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #9). Reviewed by Haeul Yang.
import pytest
from fastapi import FastAPI, HTTPException, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import ApiError, field_path, register_error_handlers
from app.main import app as main_app


class Option(BaseModel):
    price: int


class Payload(BaseModel):
    items: list[Option]


def make_client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/bars/{bar_id}")
    def read_bar(bar_id: str):
        raise ApiError(404, "BAR_NOT_FOUND", "업장을 찾을 수 없습니다.", details={"barId": bar_id})

    @app.get("/search")
    def search(query: str = Query(max_length=5), limit: int = Query(50, ge=1, le=100)):
        return {}

    @app.post("/items")
    def create(payload: Payload):
        return {}

    @app.get("/teapot")
    def teapot():
        raise HTTPException(status_code=418, detail="I'm a teapot")

    return TestClient(app)


def test_api_error_uses_the_common_format():
    response = make_client().get("/bars/bar-1")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "BAR_NOT_FOUND",
            "message": "업장을 찾을 수 없습니다.",
            "details": {"barId": "bar-1"},
            "fieldErrors": [],
        }
    }


def test_query_validation_errors_become_validation_failed():
    response = make_client().get("/search", params={"query": "too long", "limit": 0})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert error["details"] is None
    assert {(e["path"], e["code"]) for e in error["fieldErrors"]} == {
        ("query", "STRING_TOO_LONG"),
        ("limit", "GREATER_THAN_EQUAL"),
    }


def test_missing_query_parameter_is_reported():
    error = make_client().get("/search").json()["error"]

    assert [(e["path"], e["code"]) for e in error["fieldErrors"]] == [("query", "MISSING")]


def test_body_field_paths_use_index_notation():
    response = make_client().post("/items", json={"items": [{"price": 1}, {"price": "x"}]})

    assert [e["path"] for e in response.json()["error"]["fieldErrors"]] == ["items[1].price"]


def test_http_exception_without_known_code_falls_back():
    response = make_client().get("/teapot")

    assert response.status_code == 418
    assert response.json()["error"]["code"] == "HTTP_ERROR"
    assert response.json()["error"]["message"] == "I'm a teapot"


def test_unknown_route_returns_not_found_in_common_format():
    response = TestClient(main_app).get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_auth_errors_keep_status_and_headers(monkeypatch):
    monkeypatch.setenv("TEMP_AUTH_ENABLED", "true")

    response = TestClient(main_app).get("/api/me")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize(
    ("loc", "expected"),
    [
        (("query", "lat"), "lat"),
        (("body", "itemDecisions", 0, "optionDecisions", 1, "correctedPriceKrw"),
         "itemDecisions[0].optionDecisions[1].correctedPriceKrw"),
        (("body",), ""),
    ],
)
def test_field_path(loc, expected):
    assert field_path(loc) == expected
