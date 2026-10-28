"""Who may call each implemented API (API spec, section 2.2), with both kinds of token.

Every `/api` route is listed below. A new route fails `test_every_api_route_is_classified`
until it is added, so its permission is decided on purpose. Bar-owner access is Iteration 3.

For an operator, "allowed" means the request got past the permission check: list routes answer
`200`, and routes that need an id are called with a missing one and answer its `404`. The real
operator flows are covered by each route's own tests.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import User, UserType

MISSING_ID = "99999999-9999-4999-8999-999999999999"
JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"


@dataclass(frozen=True)
class Route:
    method: str
    path: str  # as in the OpenAPI document, e.g. /api/bars/{barId}/menu-imports
    # Keyword arguments for TestClient.request, so the request is valid apart from the caller.
    request: dict[str, Any]
    allowed: tuple[int, str | None]  # what an operator gets: status and error code (None for success)

    @property
    def id(self) -> str:
        return f"{self.method.upper()} {self.path}"

    @property
    def url(self) -> str:
        return self.path.format(barId=MISSING_ID, menuImportId=MISSING_ID)


OPERATOR_ONLY = [
    Route("get", "/api/bars", {}, (200, None)),
    Route("get", "/api/bars/{barId}/menu-imports", {}, (404, "BAR_NOT_FOUND")),
    Route(
        "post",
        "/api/bars/{barId}/menu-imports",
        {
            "headers": {"Idempotency-Key": "permission-check"},
            "data": {"mode": "full_replace"},
            "files": [("images", ("page-1.jpg", JPEG, "image/jpeg"))],
        },
        (404, "BAR_NOT_FOUND"),
    ),
    Route("get", "/api/menu-imports/{menuImportId}", {}, (404, "MENU_IMPORT_NOT_FOUND")),
    Route(
        "post",
        "/api/menu-imports/{menuImportId}/review-and-apply",
        {"json": {"reviewVersion": 1, "itemDecisions": [], "changeDecisions": []}},
        (404, "MENU_IMPORT_NOT_FOUND"),
    ),
    Route("get", "/api/catalog/brands", {"params": {"query": "glen"}}, (200, None)),
    Route("get", "/api/catalog/products", {"params": {"query": "glen"}}, (200, None)),
]
# Any signed-in user, with or without a users row; tested in test_users_api.py, test_auth_api.py,
# test_business_certificate_api.py, test_my_bars_api.py and test_owner_applications_api.py (which also covers the
# applicant-or-operator rule of GET /api/owner-applications/{applicationId}).
SIGNED_IN = {
    ("get", "/api/me"),
    ("post", "/api/owner-applications/business-certificate-ocr"),
    ("post", "/api/owner-applications"),
    ("get", "/api/me/owner-applications"),
    ("get", "/api/owner-applications/{applicationId}"),
    ("post", "/api/owner-applications/{applicationId}/cancel"),
    ("get", "/api/me/bars"),
}
# No token needed; tested in test_search_api.py, test_nearby_bars_api.py, test_map_bars_api.py,
# test_bar_names_api.py, test_bar_menu_api.py and test_auth_api.py.
PUBLIC = {
    ("get", "/api/search/bars"),
    ("get", "/api/search/nearby-bars"),
    ("get", "/api/search/map-bars"),
    ("get", "/api/search/bar-names"),
    ("get", "/api/bars/{barId}/menu"),
    ("post", "/api/auth/temp-login"),
}

SUPABASE_SUBJECT = "0b6b3f5e-6f1f-4c2a-9a55-6d3e2f1a7c10"


def call(client: TestClient, route: Route, token: str | None):
    request = dict(route.request)
    headers = dict(request.pop("headers", {}))
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return client.request(route.method, route.url, headers=headers, **request)


def outcome(response) -> tuple[int, str | None]:
    code = response.json()["error"]["code"] if response.status_code >= 400 else None
    return response.status_code, code


def add_user(db_session, user_type: UserType) -> None:
    db_session.add(User(auth_subject=SUPABASE_SUBJECT, user_type=user_type))
    db_session.flush()


# Each returns a token for one kind of caller; the database rows it needs are added first.
Caller = Callable[..., str]


def temporary(user_type: str) -> Caller:
    return lambda token_for, supabase, db_session: token_for(user_type)


def supabase_user(user_type: UserType | None) -> Caller:
    def issue(token_for, supabase, db_session):
        if user_type is not None:
            add_user(db_session, user_type)
        return supabase.token(sub=SUPABASE_SUBJECT)

    return issue


NOT_OPERATORS = {
    "temporary customer": temporary("customer"),
    "Supabase customer": supabase_user(UserType.CUSTOMER),
    "Supabase user without a row": supabase_user(None),
}
OPERATORS = {
    "temporary operator": temporary("operator"),
    "Supabase operator": supabase_user(UserType.OPERATOR),
}


@pytest.mark.parametrize("route", OPERATOR_ONLY, ids=lambda route: route.id)
def test_guest_is_unauthenticated(client, route):
    response = call(client, route, None)

    assert outcome(response) == (401, "UNAUTHENTICATED")
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("caller", NOT_OPERATORS.values(), ids=NOT_OPERATORS.keys())
@pytest.mark.parametrize("route", OPERATOR_ONLY, ids=lambda route: route.id)
def test_non_operator_is_forbidden(client, token_for, supabase, db_session, route, caller):
    token = caller(token_for, supabase, db_session)

    assert outcome(call(client, route, token)) == (403, "FORBIDDEN")


@pytest.mark.parametrize("caller", OPERATORS.values(), ids=OPERATORS.keys())
@pytest.mark.parametrize("route", OPERATOR_ONLY, ids=lambda route: route.id)
def test_operator_is_allowed(client, token_for, supabase, db_session, route, caller):
    token = caller(token_for, supabase, db_session)

    assert outcome(call(client, route, token)) == route.allowed


def test_every_api_route_is_classified():
    classified = {(route.method, route.path) for route in OPERATOR_ONLY}
    documented = {
        (method, path)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/")
        for method in operations
    }

    assert documented == classified | SIGNED_IN | PUBLIC
