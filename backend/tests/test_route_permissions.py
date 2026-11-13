"""Who may call each implemented API (API spec, section 2.2), with both kinds of token.

Every `/api` route is listed below. A new route fails `test_every_api_route_is_classified`
until it is added, so its permission is decided on purpose.

For an operator-only route, "allowed" means the request got past the permission check: list routes
answer `200`, and routes that need an id are called with a missing one and answer its `404`. Routes
an owner may call check the target first, so they are also called on a real bar and import. The real
flows are covered by each route's own tests.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Bar, ImportMode, ImportStatus, MenuImport, UserType
from tests.factories import make_bar, make_owner, make_user

MISSING_ID = "99999999-9999-4999-8999-999999999999"
JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"


@dataclass(frozen=True)
class Route:
    method: str
    path: str  # as in the OpenAPI document, e.g. /api/bars/{barId}/menu-imports
    # Keyword arguments for TestClient.request, so the request is valid apart from the caller.
    request: dict[str, Any]
    allowed: tuple[int, str | None]  # what an operator gets: status and error code (None for success)
    # What a temporary-login operator, who has no users row, gets instead, when it differs.
    allowed_without_users_row: tuple[int, str | None] | None = None

    @property
    def id(self) -> str:
        return f"{self.method.upper()} {self.path}"

    @property
    def url(self) -> str:
        return self.path.format(
            barId=MISSING_ID, menuImportId=MISSING_ID,
            applicationId=MISSING_ID, localItemId=MISSING_ID,
        )


@dataclass(frozen=True)
class ManagerRoute:
    """A route for an operator or the target bar's current owner."""

    method: str
    path: str
    request: dict[str, Any]
    missing: tuple[int, str]  # what any signed-in caller gets for a missing id
    allowed: tuple[int, str | None]  # what a manager gets on the `target` bar and its uploaded import

    @property
    def id(self) -> str:
        return f"{self.method.upper()} {self.path}"

    def url(self, bar_id: str = MISSING_ID, menu_import_id: str = MISSING_ID) -> str:
        return self.path.format(barId=bar_id, menuImportId=menu_import_id, barMenuItemId=MISSING_ID, photoId=MISSING_ID)


UPLOAD = {
    "headers": {"Idempotency-Key": "permission-check"},
    "data": {"mode": "full_replace"},
    "files": [("images", ("page-1.jpg", JPEG, "image/jpeg"))],
}

OPERATOR_ONLY = [
    Route("get", "/api/bars", {}, (200, None)),
    Route("get", "/api/owner-applications", {}, (200, None)),
    Route(
        "post",
        "/api/owner-applications/{applicationId}/approve",
        {},
        (404, "OWNER_APPLICATION_NOT_FOUND"),
        (404, "USER_NOT_FOUND"),
    ),
    Route(
        "post",
        "/api/owner-applications/{applicationId}/reject",
        {"json": {"reason": "확인할 수 없습니다."}},
        (404, "OWNER_APPLICATION_NOT_FOUND"),
        (404, "USER_NOT_FOUND"),
    ),
    Route(
        "post",
        "/api/bars/{barId}/menu/local-items/{localItemId}/approve",
        {"json": {"menuVersion": 1, "productId": MISSING_ID}},
        (404, "BAR_NOT_FOUND"),
    ),
    # Records no reviewer, so a temporary-login operator needs no users row.
    Route("post", "/api/owner-applications/{applicationId}/verify-business", {}, (404, "OWNER_APPLICATION_NOT_FOUND")),
    # Records who revoked the ownership, so a temporary-login operator needs a users row first.
    Route("delete", "/api/bars/{barId}/owner", {}, (404, "BAR_NOT_FOUND"), (404, "USER_NOT_FOUND")),
]
BAR_MANAGER = [
    ManagerRoute("get", "/api/bars/{barId}", {}, (404, "BAR_NOT_FOUND"), (200, None)),
    ManagerRoute("patch", "/api/bars/{barId}", {"json": {}}, (404, "BAR_NOT_FOUND"), (200, None)),
    ManagerRoute("get", "/api/bars/{barId}/menu-imports", {}, (404, "BAR_NOT_FOUND"), (200, None)),
    # The target bar has an unfinished import, so a manager's upload stops there.
    ManagerRoute(
        "post", "/api/bars/{barId}/menu-imports", UPLOAD, (404, "BAR_NOT_FOUND"), (409, "ACTIVE_IMPORT_EXISTS")
    ),
    ManagerRoute("get", "/api/menu-imports/{menuImportId}", {}, (404, "MENU_IMPORT_NOT_FOUND"), (200, None)),
    ManagerRoute(
        "post",
        "/api/menu-imports/{menuImportId}/review-and-apply",
        {"json": {"reviewVersion": 1, "itemDecisions": [], "changeDecisions": []}},
        (404, "MENU_IMPORT_NOT_FOUND"),
        (409, "INVALID_IMPORT_STATE"),
    ),
    ManagerRoute("post", "/api/menu-imports/{menuImportId}/cancel", {}, (404, "MENU_IMPORT_NOT_FOUND"), (200, None)),
    # Manual menu edits: the target bar has an unfinished import, so a manager's edit stops there.
    ManagerRoute(
        "post",
        "/api/bars/{barId}/menu/items",
        {"json": {"menuVersion": None, "productId": MISSING_ID, "options": [{"priceKrw": 10000}]}},
        (404, "BAR_NOT_FOUND"),
        (409, "ACTIVE_IMPORT_EXISTS"),
    ),
    ManagerRoute(
        "put",
        "/api/bars/{barId}/menu/items/{barMenuItemId}",
        {"json": {"menuVersion": 1, "displayName": "Glenfiddich 12", "options": [{"priceKrw": 10000}]}},
        (404, "BAR_NOT_FOUND"),
        (409, "ACTIVE_IMPORT_EXISTS"),
    ),
    ManagerRoute(
        "delete",
        "/api/bars/{barId}/menu/items/{barMenuItemId}",
        {"params": {"menuVersion": 1}},
        (404, "BAR_NOT_FOUND"),
        (409, "ACTIVE_IMPORT_EXISTS"),
    ),
    ManagerRoute(
        "post",
        "/api/bars/{barId}/menu/reset",
        {"json": {"menuVersion": None}},
        (404, "BAR_NOT_FOUND"),
        (409, "ACTIVE_IMPORT_EXISTS"),
    ),
    # Accepted during an import; the target bar has no menu, so a manager stops at the item or the menu.
    ManagerRoute(
        "put",
        "/api/bars/{barId}/menu/items/{barMenuItemId}/sold-out",
        {"json": {"soldOut": True}},
        (404, "BAR_NOT_FOUND"),
        (404, "MENU_ITEM_NOT_FOUND"),
    ),
    ManagerRoute(
        "post",
        "/api/bars/{barId}/menu/confirm",
        {"json": {"menuVersion": None}},
        (404, "BAR_NOT_FOUND"),
        (409, "NO_PUBLISHED_MENU"),
    ),
    # A vacation far ahead passes the date checks on any day.
    ManagerRoute(
        "put",
        "/api/bars/{barId}/operating-exception",
        {"json": {"kind": "vacation", "startDate": "2099-01-01", "endDate": "2099-01-02"}},
        (404, "BAR_NOT_FOUND"),
        (200, None),
    ),
    ManagerRoute("delete", "/api/bars/{barId}/operating-exception", {}, (404, "BAR_NOT_FOUND"), (200, None)),
    # Photos: a manager's upload of a file that is not an image stops at its type, so nothing is stored.
    ManagerRoute(
        "post",
        "/api/bars/{barId}/photos",
        {"files": [("image", ("photo.jpg", b"not an image", "image/jpeg"))]},
        (404, "BAR_NOT_FOUND"),
        (415, "UNSUPPORTED_IMAGE_TYPE"),
    ),
    ManagerRoute("delete", "/api/bars/{barId}/photos/{photoId}", {}, (404, "BAR_NOT_FOUND"), (404, "PHOTO_NOT_FOUND")),
    # The target bar has no photos.
    ManagerRoute(
        "put", "/api/bars/{barId}/photos/order", {"json": {"photoIds": []}}, (404, "BAR_NOT_FOUND"), (200, None)
    ),
]
# Operators and the owner of at least one bar.
CATALOG = [
    Route("get", "/api/catalog/brands", {"params": {"query": "glen"}}, (200, None)),
    Route("get", "/api/catalog/products", {"params": {"query": "glen"}}, (200, None)),
]
# Any signed-in user, with or without a users row; tested in test_users_api.py, test_me_update_api.py
# (PATCH /api/me answers USER_NOT_FOUND without a row), test_auth_api.py, test_business_certificate_api.py,
# test_business_check_api.py, test_my_bars_api.py, test_owner_applications_api.py (which also covers the
# applicant-or-operator rule of GET /api/owner-applications/{applicationId}),
# test_owner_application_menu_photos_api.py and test_owner_application_cover_photo_api.py.
SIGNED_IN = {
    ("get", "/api/me"),
    ("patch", "/api/me"),
    ("post", "/api/owner-applications/business-certificate-ocr"),
    ("post", "/api/owner-applications/business-verification"),
    ("post", "/api/owner-applications"),
    ("get", "/api/me/owner-applications"),
    ("get", "/api/owner-applications/{applicationId}"),
    ("post", "/api/owner-applications/{applicationId}/cancel"),
    ("put", "/api/owner-applications/{applicationId}/menu-photos"),
    ("put", "/api/owner-applications/{applicationId}/cover-photo"),
    ("delete", "/api/owner-applications/{applicationId}/cover-photo"),
    ("get", "/api/me/bars"),
}
# No token needed; tested in test_search_api.py, test_nearby_bars_api.py, test_map_bars_api.py,
# test_bar_names_api.py, test_popular_products_api.py, test_bar_menu_api.py (which also covers
# inactive bars for owners), test_bar_photos_api.py and test_auth_api.py.
PUBLIC = {
    ("get", "/api/search/bars"),
    ("get", "/api/search/nearby-bars"),
    ("get", "/api/search/map-bars"),
    ("get", "/api/search/bar-names"),
    ("get", "/api/search/popular-products"),
    ("get", "/api/bars/{barId}/menu"),
    ("get", "/api/bar-photos/{photoId}"),
    ("get", "/api/bar-photos/{photoId}/thumbnail"),
    ("post", "/api/auth/temp-login"),
}

SUPABASE_SUBJECT = "0b6b3f5e-6f1f-4c2a-9a55-6d3e2f1a7c10"


@dataclass(frozen=True)
class Target:
    bar_id: str
    menu_import_id: str
    reviewer: Any  # the operator user who approved the owners


@pytest.fixture
def target(db_session) -> Target:
    """An active bar with an `uploaded` import and no owner yet."""
    bar = make_bar(db_session, "Target Bar")
    menu_import = MenuImport(
        idempotency_key="target-import",
        request_fingerprint="0" * 64,
        bar_id=bar.id,
        mode=ImportMode.FULL_REPLACE,
        status=ImportStatus.UPLOADED,
    )
    db_session.add(menu_import)
    reviewer = make_user(db_session, "reviewer-subject", user_type=UserType.OPERATOR)
    db_session.flush()
    return Target(str(bar.id), str(menu_import.id), reviewer)


def call(client: TestClient, method: str, url: str, request: dict[str, Any], token: str | None):
    request = dict(request)
    headers = dict(request.pop("headers", {}))
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return client.request(method, url, headers=headers, **request)


def outcome(response) -> tuple[int, str | None]:
    code = response.json()["error"]["code"] if response.status_code >= 400 else None
    return response.status_code, code


# Each returns a token for one kind of caller; the database rows it needs are added first.
Caller = Callable[..., str]


def temporary(user_type: str) -> Caller:
    return lambda token_for, supabase, db_session, target: token_for(user_type)


def supabase_user(user_type: UserType | None) -> Caller:
    def issue(token_for, supabase, db_session, target):
        if user_type is not None:
            make_user(db_session, SUPABASE_SUBJECT, user_type=user_type)
        return supabase.token(sub=SUPABASE_SUBJECT)

    return issue


def owner(*, of_target: bool, revoked: bool = False) -> Caller:
    """A Supabase customer who owns the target bar or another one, now or no longer."""

    def issue(token_for, supabase, db_session, target):
        user = make_user(db_session, SUPABASE_SUBJECT)
        bar = db_session.get(Bar, UUID(target.bar_id)) if of_target else make_bar(db_session, "Owned Bar")
        ownership = make_owner(db_session, user, bar, target.reviewer)
        if revoked:
            ownership.revoked_at = datetime(2026, 10, 20, tzinfo=timezone.utc)
            ownership.revoked_by_user_id = target.reviewer.id
            db_session.flush()
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
NOT_MANAGERS = {
    **NOT_OPERATORS,
    "owner of another bar": owner(of_target=False),
    "former owner of the bar": owner(of_target=True, revoked=True),
}
MANAGERS = {"owner of the bar": owner(of_target=True), **OPERATORS}
OWNERS_OF_A_BAR = {"owner of a bar": owner(of_target=False)}
NOT_OWNERS = {**NOT_OPERATORS, "former owner": owner(of_target=True, revoked=True)}


# ---- operator only ----


@pytest.mark.parametrize("route", OPERATOR_ONLY + CATALOG, ids=lambda route: route.id)
def test_guest_is_unauthenticated(client, route):
    response = call(client, route.method, route.url, route.request, None)

    assert outcome(response) == (401, "UNAUTHENTICATED")
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("caller", {**NOT_OPERATORS, **OWNERS_OF_A_BAR}.values(), ids=[*NOT_OPERATORS, *OWNERS_OF_A_BAR])
@pytest.mark.parametrize("route", OPERATOR_ONLY, ids=lambda route: route.id)
def test_non_operator_is_forbidden(client, token_for, supabase, db_session, target, route, caller):
    token = caller(token_for, supabase, db_session, target)

    assert outcome(call(client, route.method, route.url, route.request, token)) == (403, "FORBIDDEN")


@pytest.mark.parametrize("caller", OPERATORS.keys())
@pytest.mark.parametrize("route", OPERATOR_ONLY + CATALOG, ids=lambda route: route.id)
def test_operator_is_allowed(client, token_for, supabase, db_session, target, route, caller):
    token = OPERATORS[caller](token_for, supabase, db_session, target)
    expected = route.allowed
    if caller == "temporary operator" and route.allowed_without_users_row is not None:
        expected = route.allowed_without_users_row

    assert outcome(call(client, route.method, route.url, route.request, token)) == expected


# ---- the catalog: operators and bar owners ----


@pytest.mark.parametrize("caller", NOT_OWNERS.values(), ids=NOT_OWNERS.keys())
@pytest.mark.parametrize("route", CATALOG, ids=lambda route: route.id)
def test_catalog_needs_an_operator_or_a_bar_owner(client, token_for, supabase, db_session, target, route, caller):
    token = caller(token_for, supabase, db_session, target)

    assert outcome(call(client, route.method, route.url, route.request, token)) == (403, "FORBIDDEN")


@pytest.mark.parametrize("route", CATALOG, ids=lambda route: route.id)
def test_a_bar_owner_may_search_the_catalog(client, token_for, supabase, db_session, target, route):
    token = OWNERS_OF_A_BAR["owner of a bar"](token_for, supabase, db_session, target)

    assert outcome(call(client, route.method, route.url, route.request, token)) == route.allowed


# ---- operator or the bar's owner ----


@pytest.mark.parametrize("route", BAR_MANAGER, ids=lambda route: route.id)
def test_guest_is_unauthenticated_for_bar_management(client, target, route):
    response = call(client, route.method, route.url(target.bar_id, target.menu_import_id), route.request, None)

    assert outcome(response) == (401, "UNAUTHENTICATED")


@pytest.mark.parametrize("caller", {**NOT_MANAGERS, **MANAGERS}.values(), ids=[*NOT_MANAGERS, *MANAGERS])
@pytest.mark.parametrize("route", BAR_MANAGER, ids=lambda route: route.id)
def test_a_missing_target_is_not_found_before_permission(client, token_for, supabase, db_session, target, route, caller):
    token = caller(token_for, supabase, db_session, target)

    assert outcome(call(client, route.method, route.url(), route.request, token)) == route.missing


@pytest.mark.parametrize("caller", NOT_MANAGERS.values(), ids=NOT_MANAGERS.keys())
@pytest.mark.parametrize("route", BAR_MANAGER, ids=lambda route: route.id)
def test_only_a_manager_may_manage_the_bar(client, token_for, supabase, db_session, target, route, caller):
    token = caller(token_for, supabase, db_session, target)
    url = route.url(target.bar_id, target.menu_import_id)

    assert outcome(call(client, route.method, url, route.request, token)) == (403, "FORBIDDEN")


@pytest.mark.parametrize("caller", MANAGERS.values(), ids=MANAGERS.keys())
@pytest.mark.parametrize("route", BAR_MANAGER, ids=lambda route: route.id)
def test_a_manager_may_manage_the_bar(client, token_for, supabase, db_session, target, route, caller):
    token = caller(token_for, supabase, db_session, target)
    url = route.url(target.bar_id, target.menu_import_id)

    assert outcome(call(client, route.method, url, route.request, token)) == route.allowed


def test_every_api_route_is_classified():
    classified = {(route.method, route.path) for route in OPERATOR_ONLY + BAR_MANAGER + CATALOG}
    documented = {
        (method, path)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api/")
        for method in operations
    }

    assert documented == classified | SIGNED_IN | PUBLIC
