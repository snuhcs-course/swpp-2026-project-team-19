# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #9); Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-18, 2026-10-20). Reviewed by Haeul Yang.
import importlib

import pytest
from fastapi import FastAPI, HTTPException, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError

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

    @app.get("/broken")
    def broken():
        raise RuntimeError("secret detail that must not reach the client")

    return TestClient(app, raise_server_exceptions=False)


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


# ---- unexpected errors (API spec, section 9.2) ----

INTERNAL_ERROR = {
    "error": {
        "code": "INTERNAL_ERROR",
        "message": "일시적인 서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        "details": None,
        "fieldErrors": [],
    }
}


def test_unexpected_error_uses_the_common_format_without_details():
    response = make_client().get("/broken")

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/json"
    assert response.json() == INTERNAL_ERROR
    assert "secret" not in response.text


def test_unexpected_error_still_reaches_the_server_log():
    # Starlette raises the exception again after sending the response, so uvicorn logs the traceback.
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/broken")
    def broken():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        TestClient(app).get("/broken")


def database_down(*args, **kwargs):
    raise OperationalError("SELECT secret_column FROM users", {}, Exception("password authentication failed"))


@pytest.mark.parametrize(
    ("route", "service", "url", "params"),
    [
        ("search", "search_bars", "/api/search/bars", {"query": "x"}),
        ("search", "find_nearby_bars", "/api/search/nearby-bars", {"lat": 37.478, "lng": 126.951}),
        ("bars", "get_bar_menu", "/api/bars/22222222-2222-4222-8222-222222222222/menu", {}),
    ],
)
def test_public_route_failure_is_an_internal_error(client, monkeypatch, route, service, url, params):
    monkeypatch.setattr(importlib.import_module(f"app.api.routes.{route}"), service, database_down)

    response = TestClient(main_app, raise_server_exceptions=False).get(url, params=params)

    assert (response.status_code, response.json()) == (500, INTERNAL_ERROR)
    assert "secret" not in response.text and "password" not in response.text


def test_protected_route_failure_is_an_internal_error(client, token_for, monkeypatch):
    import app.api.routes.catalog as catalog_route

    monkeypatch.setattr(catalog_route, "search_brands", database_down)
    operator = {"Authorization": f"Bearer {token_for('operator')}"}

    response = TestClient(main_app, raise_server_exceptions=False).get(
        "/api/catalog/brands", params={"query": "x"}, headers=operator
    )

    assert (response.status_code, response.json()) == (500, INTERNAL_ERROR)
