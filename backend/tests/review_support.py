"""Shared setup for review submission tests: a sample import ready for review and a valid body."""

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import Bar, ExtractedItem, MenuBoard, MenuChangeType, MenuImport, MenuImportChange, Product
from app.services.menu_review_validation import load_items, pending_changes
from tests.factories import make_bar, make_brand, make_product, publish_menu

JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-body"


def make_glenfiddich(session: Session) -> dict:
    brand = make_brand(session, "Glenfiddich", aliases=("글렌피딕",))
    return {
        "brand": brand,
        12: make_product(session, brand, "Glenfiddich 12", aliases=("글렌피딕 12년",), age_years=12),
        15: make_product(session, brand, "Glenfiddich 15", aliases=("글렌피딕 15년",), age_years=15),
        21: make_product(session, brand, "Glenfiddich 21", age_years=21, is_active=False),
    }


@dataclass
class SampleReview:
    """The sample mock menu uploaded with full_replace to a bar selling Glenfiddich 12 at an
    older price, then Glenfiddich 15.

    items: header, 글렌피딕 12년 (exact), Glenfiddich 12 with age 15 (ambiguous), Unknown
    Distillery 25 (unmatched), description. changes: update 12, add unknown, remove 15.
    """

    menu_import: MenuImport
    bar: Bar
    board: MenuBoard
    items: list[ExtractedItem]
    changes: dict[MenuChangeType, MenuImportChange]


def upload_sample_review(client, session: Session, operator: dict, glenfiddich: dict) -> SampleReview:
    bar = make_bar(session)
    board = publish_menu(
        session,
        bar,
        [
            (glenfiddich[12], "글렌피딕 12년", [(None, 15, 8000), (None, 30, 17000)]),
            (glenfiddich[15], "글렌피딕 15년", [(None, 30, 21000)]),
        ],
    )
    response = client.post(
        f"/api/bars/{bar.id}/menu-imports",
        headers={**operator, "Idempotency-Key": str(uuid4())},
        data={"mode": "full_replace"},
        files=[("images", ("sample.jpg", JPEG, "image/jpeg"))],
    )
    assert response.status_code == 202, response.text
    session.expire_all()
    menu_import = session.get(MenuImport, response.json()["menuImportId"])
    changes = {c.change_type: c for c in pending_changes(session, menu_import)}
    assert set(changes) == {MenuChangeType.UPDATE, MenuChangeType.ADD, MenuChangeType.REMOVE}
    return SampleReview(menu_import, bar, board, load_items(session, menu_import), changes)


def valid_body(sample: SampleReview, glenfiddich: dict[int, Product]) -> dict:
    """Keep 12 (exact), reject the ambiguous line, create Unknown Distillery 25 with a new
    brand, confirm the header and description, and apply every change."""
    header, exact, conflict, unknown, description = sample.items
    return {
        "reviewVersion": 1,
        "itemDecisions": [
            {"action": "confirm_non_product", "extractedItemId": str(header.id), "finalLineType": "section_header"},
            {
                "action": "select_existing_product",
                "extractedItemId": str(exact.id),
                "finalLineType": "product",
                "productId": str(glenfiddich[12].id),
            },
            {"action": "reject", "extractedItemId": str(conflict.id), "finalLineType": "product"},
            {
                "action": "create_product",
                "extractedItemId": str(unknown.id),
                "finalLineType": "product",
                "brand": {"type": "new", "canonicalName": "Unknown Distillery"},
                "product": {"displayName": "Unknown Distillery 25", "ageYears": 25},
            },
            {"action": "confirm_non_product", "extractedItemId": str(description.id), "finalLineType": "description"},
        ],
        "changeDecisions": [{"changeId": str(c.id), "decision": "apply"} for c in sample.changes.values()],
    }
