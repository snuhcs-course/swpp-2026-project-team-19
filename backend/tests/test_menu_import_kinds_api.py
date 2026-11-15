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
    # Not a whisky to create (spec 5.4); the whisky line keeps its draft.
    assert lines[str(items[3].id)]["newProductDraft"] is None
    assert lines[str(items[1].id)]["newProductDraft"]["displayName"] == "글렌피딕 12년"
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


def test_a_photo_read_with_prompt_v2_gives_the_other_lines_in_menu_order_with_their_boxes(
    client, db_session, image_storage, operator, glenfiddich, monkeypatch
):
    """The real hybrid extractor with prompt v2 (CLOVA and Gemini faked) through the import: the
    non-whisky lines of the photo are stored as kind other where the menu has them, are not matched,
    and the review shows each line's box."""
    import json
    from types import SimpleNamespace

    from app.adapters.hybrid_extraction import HybridMenuExtractor
    from app.api.deps import get_menu_extractor
    from app.extraction import gemini, hybrid
    from app.main import app
    from tests.test_hybrid_extraction_adapter import CLOVA, OCR_RESPONSE, SETTINGS, FakeInteractions, jpeg

    def row(name, category, price, name_lines=(), price_lines=()):
        return {"raw_name": name, "price_krw": price, "pour_ml": 30 if category == "whisky" else None, "unit": "glass",
                "source_lines": {"name": list(name_lines), "price": list(price_lines)}, "category": category}

    output = {"items": [row("치즈 플래터", "food", 25000, ["L001"]),
                        row("글렌피딕 12년", "whisky", 15000, ["L002"], ["L003"]),
                        row("글렌피딕 하이볼", "cocktail", 12000)]}
    fake = SimpleNamespace(interactions=FakeInteractions(json.dumps(output)))
    monkeypatch.setattr(gemini, "make_client", lambda settings: fake)
    monkeypatch.setattr(hybrid, "call_ocr", lambda *args, **kwargs: {
        "response": OCR_RESPONSE, "sentSize": [1000, 2000], "latencyMs": 900, "attempts": 1})
    app.dependency_overrides[get_menu_extractor] = lambda: HybridMenuExtractor(SETTINGS, CLOVA, prompt="v2")
    bar = make_bar(db_session)
    db_session.commit()
    try:
        response = client.post(
            f"/api/bars/{bar.id}/menu-imports",
            headers={**operator, "Idempotency-Key": str(uuid4())},
            data={"mode": "full_replace"},
            files=[("images", ("menu.jpg", jpeg(), "image/jpeg"))],  # a picture the extractor can open
        )
    finally:
        app.dependency_overrides.pop(get_menu_extractor, None)
    assert response.status_code == 202, response.text

    review = client.get(f"/api/menu-imports/{response.json()['menuImportId']}", headers=operator).json()

    assert review.get("status") == "ready_for_review", review
    [image] = review["images"]
    assert [(line["itemOrder"], line["rawText"], line["extractedKind"]) for line in image["items"]] == [
        (1, "치즈 플래터", "other"), (2, "글렌피딕 12년", "whisky"), (3, "글렌피딕 하이볼", "other")]
    cheese, whisky, highball = image["items"]
    assert cheese["sourceBox"] == [100, 10, 260, 30] and whisky["sourceBox"] == [100, 100, 880, 120]
    assert highball["sourceBox"] is None and highball["options"][0]["extractedPriceKrw"] == 12000
    assert (cheese["proposedProductId"], cheese["candidates"], cheese["newProductDraft"]) == (None, [], None)
    assert (highball["initialResolutionStatus"], highball["candidates"]) == (None, [])  # names the brand, not matched
    assert whisky["proposedProductId"] == str(glenfiddich[12].id)
