"""A menu whose non-whisky lines the AI marks kind other (flow doc 4.3, schema guide 573, spec 8.10).

The mock extractor's "mixed" photo: a header, 글렌피딕 12년 (whisky), and 글렌피딕 하이볼 and 치즈 플래터
(other).
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import MenuImport, MenuItemCheck, MenuItemKind, ResolutionCandidate
from tests.factories import make_bar
from tests.review_support import JPEG, make_glenfiddich


@pytest.fixture
def operator(token_for):
    return {"Authorization": f"Bearer {token_for('operator')}"}


@pytest.fixture
def glenfiddich(db_session):
    return make_glenfiddich(db_session)


@pytest.fixture
def imported(client, db_session, image_storage, operator, glenfiddich):
    bar = make_bar(db_session)
    db_session.commit()
    response = client.post(
        f"/api/bars/{bar.id}/menu-imports",
        headers={**operator, "Idempotency-Key": str(uuid4())},
        data={"mode": "full_replace"},
        files=[("images", ("mixed.jpg", JPEG, "image/jpeg"))],
    )
    assert response.status_code == 202, response.text
    db_session.expire_all()
    menu_import = db_session.get(MenuImport, response.json()["menuImportId"])
    return bar, menu_import, [item for image in menu_import.images for item in image.extraction_run.items]


def test_the_ai_kind_is_stored_and_other_lines_are_not_matched(db_session, imported):
    _, _, items = imported

    assert [(item.extracted_product_name, item.extracted_kind) for item in items] == [
        (None, None),
        ("글렌피딕 12년", MenuItemKind.WHISKY),
        (None, None),
        ("글렌피딕 하이볼", MenuItemKind.OTHER),
        ("치즈 플래터", MenuItemKind.OTHER),
    ]
    statuses = [item.initial_resolution_status for item in items]
    assert statuses[1] is not None and statuses[3:] == [None, None]
    # "글렌피딕 하이볼" names the brand, but a non-whisky line gets no candidate.
    others = [items[3].id, items[4].id]
    assert db_session.scalars(select(ResolutionCandidate).where(ResolutionCandidate.extracted_item_id.in_(others))).all() == []


def test_the_review_proposes_other_lines_as_non_whisky_menus(client, operator, imported):
    _, menu_import, items = imported

    review = client.get(f"/api/menu-imports/{menu_import.id}", headers=operator).json()

    lines = {line["extractedItemId"]: line for image in review["images"] for line in image["items"]}
    assert lines[str(items[3].id)]["extractedKind"] == "other"
    assert lines[str(items[3].id)]["proposedProductId"] is None
    adds = {c["extractedItemId"]: c["after"] for c in review["proposedChanges"] if c["changeType"] == "add"}
    assert (adds[str(items[3].id)]["productId"], adds[str(items[3].id)]["kind"]) == (None, "other")
    assert adds[str(items[1].id)]["kind"] == "whisky"


def test_other_lines_are_published_without_a_product_and_unchecked(
    client, db_session, operator, imported, glenfiddich
):
    bar, menu_import, items = imported
    review = client.get(f"/api/menu-imports/{menu_import.id}", headers=operator).json()

    def options(item):
        return [
            {"extractedOptionId": str(o.id), "optionLabel": o.extracted_option_label, "pourMl": o.extracted_pour_ml,
             "priceKrw": o.extracted_price_krw}
            for o in item.options
        ]

    decisions = []
    for item in items:
        base = {"extractedItemId": str(item.id)}
        if item.extracted_kind is None:
            decisions.append({**base, "action": "confirm_non_product", "finalLineType": "section_header"})
        elif item.extracted_kind == MenuItemKind.WHISKY:
            decisions.append(
                {**base, "action": "select_existing_product", "finalLineType": "product",
                 "productId": str(glenfiddich[12].id), "options": options(item)}
            )
        else:
            decisions.append(
                {**base, "action": "publish_without_product", "finalLineType": "product", "kind": "other",
                 "options": options(item)}
            )
    body = {
        "reviewVersion": review["reviewVersion"],
        "itemDecisions": decisions,
        "changeDecisions": [{"changeId": c["changeId"], "decision": "apply"} for c in review["proposedChanges"]],
    }

    response = client.post(f"/api/menu-imports/{menu_import.id}/review-and-apply", json=body, headers=operator)

    assert response.status_code == 200, response.text
    assert (response.json()["result"]["added"], response.json()["result"]["unlinkedWhisky"]) == (3, 0)
    menu = client.get(f"/api/bars/{bar.id}/menu").json()["items"]
    assert [(i["displayName"], i["kind"], i["productId"] is None) for i in menu] == [
        ("글렌피딕 12년", "whisky", False),
        ("글렌피딕 하이볼", "other", True),
        ("치즈 플래터", "other", True),
    ]
    # A non-whisky menu waits for no operator (spec 3.18.1).
    db_session.expire_all()
    assert db_session.scalars(select(MenuItemCheck).where(MenuItemCheck.bar_id == bar.id)).all() == []
    # The AI's kind was kept, so nothing is recorded as corrected.
    db_session.expire_all()
    stored = db_session.get(MenuImport, menu_import.id)
    lines = [item for image in stored.images for item in image.extraction_run.items]
    assert [line.corrected_kind for line in lines] == [None] * 5
