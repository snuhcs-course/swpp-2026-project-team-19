from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import (
    ExtractedItem,
    ExtractedOption,
    ExtractionApproach,
    ExtractionRun,
    ImportMode,
    MatchMethod,
    MenuBoard,
    MenuImage,
    MenuImport,
    Product,
    ResolutionCandidate,
)
from tests.factories import make_bar, make_brand, make_product


def make_import(db_session, bar, key="key-1"):
    menu_import = MenuImport(
        idempotency_key=key, request_fingerprint="0" * 64, bar_id=bar.id, mode=ImportMode.FULL_REPLACE
    )
    db_session.add(menu_import)
    db_session.flush()
    return menu_import


def make_run(db_session, menu_import, order=1):
    image = MenuImage(menu_import_id=menu_import.id, storage_key=f"menus/x/page-{order}.jpg", image_order=order)
    db_session.add(image)
    db_session.flush()
    run = ExtractionRun(
        menu_image_id=image.id,
        approach=ExtractionApproach.VISION_LLM,
        provider="mock",
        model_name="mock",
        pipeline_version="test",
    )
    db_session.add(run)
    db_session.flush()
    return run


def test_database_defaults_set_the_initial_states(db_session):
    """Insert with plain SQL so the columns get the database defaults, not the ORM's."""
    bar = make_bar(db_session)
    ids = {name: uuid4() for name in ("import", "image", "run", "item", "change")}
    params = {**ids, "bar": bar.id}
    for statement in [
        "INSERT INTO menu_imports (id, idempotency_key, request_fingerprint, bar_id, mode) "
        "VALUES (:import, 'k', 'f', :bar, 'full_replace')",
        "INSERT INTO menu_images (id, menu_import_id, storage_key, image_order) VALUES (:image, :import, 's', 1)",
        "INSERT INTO extraction_runs (id, menu_image_id, approach, provider, model_name, pipeline_version) "
        "VALUES (:run, :image, 'vision_llm', 'p', 'm', 'v')",
        "INSERT INTO extracted_items (id, extraction_run_id, item_order, raw_text) VALUES (:item, :run, 1, 't')",
        "INSERT INTO menu_import_changes (id, menu_import_id, change_type) VALUES (:change, :import, 'remove')",
    ]:
        db_session.execute(text(statement), params)

    row = db_session.execute(
        text(
            "SELECT i.status, i.review_version, r.status, e.extracted_line_type, e.review_status, c.decision "
            "FROM menu_imports i JOIN extraction_runs r ON r.id = :run JOIN extracted_items e ON e.id = :item "
            "JOIN menu_import_changes c ON c.id = :change WHERE i.id = :import"
        ),
        ids,
    ).one()

    assert tuple(row) == ("uploaded", 0, "queued", "unknown", "pending", "pending")


def test_relationships_return_children_in_order(db_session):
    menu_import = make_import(db_session, make_bar(db_session))
    second, first = make_run(db_session, menu_import, order=2), make_run(db_session, menu_import, order=1)
    product = make_product(db_session, make_brand(db_session, "Ardbeg"), "Ardbeg 10")
    other = make_product(db_session, make_brand(db_session, "Lagavulin"), "Lagavulin 16")
    item = ExtractedItem(extraction_run_id=first.id, item_order=1, raw_text="아드벡 10")
    db_session.add(item)
    db_session.flush()
    db_session.add_all(
        [
            ExtractedOption(extracted_item_id=item.id, option_order=2, extracted_price_krw=200000),
            ExtractedOption(extracted_item_id=item.id, option_order=1, extracted_price_krw=15000),
            ResolutionCandidate(extracted_item_id=item.id, product_id=other.id, candidate_rank=2, method=MatchMethod.LLM),
            ResolutionCandidate(
                extracted_item_id=item.id, product_id=product.id, candidate_rank=1, method=MatchMethod.ALIAS,
                evidence={"aliasExact": True},
            ),
        ]
    )
    db_session.flush()
    db_session.expire_all()

    assert [image.image_order for image in menu_import.images] == [1, 2]
    assert menu_import.images[1].extraction_run.id == second.id
    assert [o.extracted_price_krw for o in item.options] == [15000, 200000]
    assert [c.product_id for c in item.candidates] == [product.id, other.id]
    assert item.candidates[0].evidence == {"aliasExact": True}


def test_idempotency_key_is_unique(db_session):
    bar = make_bar(db_session)
    make_import(db_session, bar, key="same")

    with pytest.raises(IntegrityError):
        make_import(db_session, bar, key="same")


def test_a_product_appears_once_per_item(db_session):
    run = make_run(db_session, make_import(db_session, make_bar(db_session)))
    product = make_product(db_session, make_brand(db_session, "Ardbeg"), "Ardbeg 10")
    item = ExtractedItem(extraction_run_id=run.id, item_order=1, raw_text="아드벡 10")
    db_session.add(item)
    db_session.flush()
    for rank in (1, 2):
        db_session.add(
            ResolutionCandidate(extracted_item_id=item.id, product_id=product.id, candidate_rank=rank, method=MatchMethod.ALIAS)
        )

    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize("model", ["product", "menu_board"])
def test_previously_deferred_foreign_keys_are_enforced(db_session, model):
    bar = make_bar(db_session)
    if model == "product":
        brand = make_brand(db_session, "Ardbeg")
        db_session.add(Product(brand_id=brand.id, display_name="X", created_from_extracted_item_id=uuid4()))
    else:
        db_session.add(MenuBoard(bar_id=bar.id, published_at=datetime.now(timezone.utc), last_import_id=uuid4()))

    with pytest.raises(IntegrityError):
        db_session.flush()
