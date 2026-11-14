"""Saving the review draft (API spec 5.9)."""

from datetime import datetime

import pytest

from app.models import MenuImport, UserType
from tests.factories import make_owner, make_user
from tests.review_support import make_glenfiddich, upload_sample_review

CONTENT = {
    "itemDecisions": [{"extractedItemId": "10000000-0000-4000-8000-000000000007", "correctedProductName": "딘스톤"}],
    "changeDecisions": [],
    "clientState": {"expandedItemIds": []},
}


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def glenfiddich(db_session):
    return make_glenfiddich(db_session)


@pytest.fixture
def sample(client, db_session, image_storage, operator, glenfiddich):
    return upload_sample_review(client, db_session, operator, glenfiddich)


def save(client, sample, headers, *, draft_version=0, review_version=1, content=CONTENT, **extra):
    body = {"draftVersion": draft_version, "reviewVersion": review_version, "content": content, **extra}
    return client.put(f"/api/menu-imports/{sample.menu_import.id}/review-draft", json=body, headers=headers)


def stored(db_session, sample) -> MenuImport:
    db_session.expire_all()
    return db_session.get(MenuImport, sample.menu_import.id)


def test_saving_raises_the_version_and_keeps_the_content_as_sent(client, db_session, sample, operator):
    # Unknown top-level fields of the content are kept, and the review version may be an old one.
    content = {**CONTENT, "futureField": {"anything": [1, 2]}}

    first = save(client, sample, operator, content=content, review_version=7)

    assert first.status_code == 200, first.text
    body = first.json()
    assert (body["menuImportId"], body["draftVersion"]) == (str(sample.menu_import.id), 1)
    datetime.fromisoformat(body["savedAt"].replace("Z", "+00:00"))
    menu_import = stored(db_session, sample)
    assert (menu_import.review_draft, menu_import.review_draft_review_version, menu_import.review_draft_version) == (
        content,
        7,
        1,
    )
    # A temporary-login operator has no users row to record.
    assert menu_import.review_draft_saved_by_user_id is None

    second = save(client, sample, operator, draft_version=1, content={})
    assert (second.status_code, second.json()["draftVersion"]) == (200, 2)
    assert stored(db_session, sample).review_draft == {}


def test_a_save_from_an_older_version_is_refused(client, db_session, sample, operator):
    first = save(client, sample, operator).json()

    response = save(client, sample, operator, draft_version=0, content={})

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "REVIEW_DRAFT_OUTDATED"
    assert error["details"]["currentDraftVersion"] == 1
    assert error["details"]["savedAt"].startswith(first["savedAt"][:19])
    assert error["details"]["reviewUrl"] == f"/api/menu-imports/{sample.menu_import.id}"
    assert stored(db_session, sample).review_draft == CONTENT


def test_the_owner_who_saved_is_recorded(client, db_session, sample, supabase):
    reviewer = make_user(db_session, "reviewer-subject", user_type=UserType.OPERATOR)
    owner = make_user(db_session, "owner-subject")
    make_owner(db_session, owner, sample.bar, reviewer)
    db_session.commit()

    response = save(client, sample, {"Authorization": f"Bearer {supabase.token(sub='owner-subject')}"})

    assert response.status_code == 200, response.text
    assert stored(db_session, sample).review_draft_saved_by_user_id == owner.id


def test_a_draft_over_256_kb_is_refused(client, db_session, sample, operator):
    content = {"clientState": {"note": "가" * 90_000}}  # 270 KB in UTF-8

    response = save(client, sample, operator, content=content)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REVIEW_DRAFT_TOO_LARGE"
    assert response.json()["error"]["details"] == {"maxBytes": 262_144}
    assert stored(db_session, sample).review_draft is None


@pytest.mark.parametrize(
    ("fields", "path"),
    [
        ({"draft_version": -1}, "draftVersion"),
        ({"review_version": 0}, "reviewVersion"),
        ({"content": ["not", "an", "object"]}, "content"),
        ({"extra": 1}, "extra"),
    ],
)
def test_the_request_shape_is_checked(client, sample, operator, fields, path):
    response = save(client, sample, operator, **fields)

    assert response.status_code == 422
    assert path in {e["path"] for e in response.json()["error"]["fieldErrors"]}


def test_only_an_import_in_review_takes_a_draft(client, db_session, sample, operator):
    canceled = client.post(f"/api/menu-imports/{sample.menu_import.id}/cancel", headers=operator)
    assert canceled.status_code == 200

    response = save(client, sample, operator)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_IMPORT_STATE"
    assert response.json()["error"]["details"]["status"] == "canceled"


def test_an_unknown_import_is_not_found(client, operator):
    response = client.put(
        "/api/menu-imports/not-a-uuid/review-draft",
        json={"draftVersion": 0, "reviewVersion": 1, "content": {}},
        headers=operator,
    )

    assert (response.status_code, response.json()["error"]["code"]) == (404, "MENU_IMPORT_NOT_FOUND")


def test_the_request_is_checked_before_the_import(client, operator):
    """Spec 5.9: the request's shape (422) and size (413) come before the import (404)."""
    url = "/api/menu-imports/not-a-uuid/review-draft"
    bad = client.put(url, json={"draftVersion": -1, "reviewVersion": 1, "content": {}}, headers=operator)
    big = client.put(url, json={"draftVersion": 0, "reviewVersion": 1, "content": {"x": "가" * 90_000}}, headers=operator)

    assert (bad.status_code, big.status_code) == (422, 413)
