import json
from pathlib import Path

import pytest

from app.matching import ExtractedProduct, resolve_product
from app.matching.db_catalog import DbCatalog
from app.matching.memory_catalog import InMemoryCatalog
from scripts.seed_catalog import seed
from tests.factories import make_brand, make_product

CATALOG_DIR = Path(__file__).resolve().parents[2] / "ai" / "catalog"
SEED_FILES = [CATALOG_DIR / name for name in ("catalog_v1_draft.json", "bars_v1.json", "labels_v1_1.json")]


def test_lookup_uses_active_products_and_every_alias(db_session):
    brand = make_brand(db_session, "Johnnie Walker")
    black = make_product(
        db_session, brand, "Johnnie Walker Black", aliases=("조니워커 블랙",), unsearchable_aliases=("Jonnie walker black",)
    )
    make_product(db_session, brand, "Johnnie Walker Red", aliases=("조니워커 블랙",), is_active=False)
    catalog = DbCatalog(db_session)

    assert catalog.find_product_ids_by_alias("조니워커블랙") == [black.id]
    # Hidden from customer search, but still used to match menu lines.
    assert catalog.find_product_ids_by_alias("jonniewalkerblack") == [black.id]
    assert catalog.get_normalized_aliases(black.id) == ["johnniewalkerblack", "jonniewalkerblack", "조니워커블랙"]


def test_get_product_returns_none_for_inactive_or_missing(db_session):
    brand = make_brand(db_session, "Ardbeg")
    active = make_product(db_session, brand, "Ardbeg 10", age_years=10, edition_name=None)
    retired = make_product(db_session, brand, "Ardbeg Old", is_active=False)
    catalog = DbCatalog(db_session)

    info = catalog.get_product(active.id)
    assert (info.product_id, info.display_name, info.age_years, info.edition_name) == (active.id, "Ardbeg 10", 10, None)
    assert catalog.get_product(retired.id) is None
    assert catalog.get_product(brand.id) is None


@pytest.mark.skipif(not all(path.exists() for path in SEED_FILES), reason="ai/catalog seed is not checked out")
def test_matches_the_in_memory_catalog_on_the_labeled_menu_items(db_session):
    catalog_json, bars_json, labels_json = (json.loads(path.read_text(encoding="utf-8")) for path in SEED_FILES)
    seed(db_session.connection(), catalog_json, bars_json)
    in_memory = InMemoryCatalog.from_seed(SEED_FILES[0])
    from_db = DbCatalog(db_session)
    items = [item for photo in labels_json["photos"] for item in photo["items"]]

    statuses = []
    for item in items:
        extracted = ExtractedProduct(product_name=item["raw_name"])
        expected, actual = resolve_product(extracted, in_memory), resolve_product(extracted, from_db)
        assert actual == expected, item["raw_name"]
        statuses.append(actual.status)

    assert (statuses.count("exact_match"), statuses.count("unmatched"), len(statuses)) == (215, 4, 219)
