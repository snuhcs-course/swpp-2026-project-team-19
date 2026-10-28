import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.matching import ExtractedProduct, resolve_product
from app.matching.db_catalog import CatalogSnapshot, DbCatalog
from app.matching.llm_layer import IB_BOTTLERS, ProductMeta
from app.matching.memory_catalog import InMemoryCatalog
from app.matching.staged import resolve_product_staged
from scripts.seed_catalog import seed
from tests.factories import make_brand, make_product

CATALOG_DIR = Path(__file__).resolve().parents[2] / "ai" / "catalog"
SEED_FILES = [CATALOG_DIR / name for name in ("catalog_v2_service.json", "bars_v2.json", "labels_v1_1.json")]


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
    # Order follows the database collation, so compare as sorted.
    assert sorted(catalog.get_normalized_aliases(black.id)) == ["johnniewalkerblack", "jonniewalkerblack", "조니워커블랙"]


def test_get_product_returns_none_for_inactive_or_missing(db_session):
    brand = make_brand(db_session, "Ardbeg")
    active = make_product(db_session, brand, "Ardbeg 10", age_years=10, edition_name=None)
    retired = make_product(db_session, brand, "Ardbeg Old", is_active=False)
    catalog = DbCatalog(db_session)

    info = catalog.get_product(active.id)
    assert (info.product_id, info.display_name, info.age_years, info.edition_name) == (active.id, "Ardbeg 10", 10, None)
    assert catalog.get_product(retired.id) is None
    assert catalog.get_product(brand.id) is None
    assert info.brand_id == brand.id


def test_brand_lookup_returns_active_products(db_session):
    brand = make_brand(db_session, "The Macallan", aliases=("맥캘란",))
    other = make_brand(db_session, "Kavalan")
    twelve = make_product(db_session, brand, "The Macallan 12 Double Cask", age_years=12)
    fifteen = make_product(db_session, brand, "The Macallan 15 Double Cask", age_years=15)
    make_product(db_session, brand, "The Macallan Old", is_active=False)
    catalog = DbCatalog(db_session)

    assert catalog.find_brand_ids_by_alias("맥캘란") == [brand.id]
    assert catalog.find_brand_ids_by_alias("themacallan") == [brand.id]
    assert catalog.find_brand_ids_by_alias("macallan") == []
    assert catalog.get_brand_product_ids(brand.id) == [twelve.id, fifteen.id]
    assert catalog.get_brand_product_ids(other.id) == []

    assert sorted(catalog.list_normalized_brand_aliases()) == sorted(
        [("themacallan", brand.id), ("맥캘란", brand.id), ("kavalan", other.id)]
    )
    # Aliases of the inactive product are left out.
    assert sorted(catalog.list_normalized_aliases()) == sorted(
        [("themacallan12doublecask", twelve.id), ("themacallan15doublecask", fifteen.id)]
    )


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


@pytest.mark.skipif(not all(path.exists() for path in SEED_FILES), reason="ai/catalog seed is not checked out")
def test_staged_matching_is_the_same_on_both_catalogs(db_session):
    catalog_json, bars_json, labels_json = (json.loads(path.read_text(encoding="utf-8")) for path in SEED_FILES)
    seed(db_session.connection(), catalog_json, bars_json)
    in_memory = InMemoryCatalog.from_seed(SEED_FILES[0])
    from_db = DbCatalog(db_session)
    names = [item["raw_name"] for photo in labels_json["photos"] for item in photo["items"]]
    names += ["맥캘란 더블캐스크 12Y", "Macallan 12yo", "Kavalan Solist", "아벨라워(Aberlour) 12년", "Talisker 10 / Ardbeg 10", "Dalwhinny 15yo", "Abelour A`bunadh"]

    for name in names:
        extracted = ExtractedProduct(product_name=name)
        stages = {"S1", "S2", "S2b", "S3"}
        expected = resolve_product_staged(extracted, in_memory, stages)
        assert resolve_product_staged(extracted, from_db, stages) == expected, name


# ---- CatalogSnapshot (I3: lookups for the LLM matching layer without an open transaction) ----


def assert_snapshot_answers_like_the_db(snapshot, from_db):
    assert snapshot.list_normalized_aliases() == from_db.list_normalized_aliases()
    assert snapshot.list_normalized_brand_aliases() == from_db.list_normalized_brand_aliases()
    for alias, product_id in from_db.list_normalized_aliases():
        assert snapshot.find_product_ids_by_alias(alias) == from_db.find_product_ids_by_alias(alias), alias
        assert snapshot.get_product(product_id) == from_db.get_product(product_id)
        assert snapshot.get_normalized_aliases(product_id) == from_db.get_normalized_aliases(product_id)
    for alias, brand_id in from_db.list_normalized_brand_aliases():
        assert snapshot.find_brand_ids_by_alias(alias) == from_db.find_brand_ids_by_alias(alias), alias
        assert snapshot.get_brand_product_ids(brand_id) == from_db.get_brand_product_ids(brand_id)
    assert snapshot.find_product_ids_by_alias("nosuchalias") == [] == snapshot.find_brand_ids_by_alias("nosuchbrand")


def test_snapshot_holds_active_products_and_their_meta(db_session):
    brand = make_brand(db_session, "Johnnie Walker", aliases=("조니워커",))
    signatory = make_brand(db_session, "Signatory Vintage")
    black = make_product(
        db_session, brand, "Johnnie Walker Black", aliases=("조니워커 블랙",), unsearchable_aliases=("Jonnie walker black",),
        age_years=12, edition_name="Black",
    )
    red = make_product(db_session, brand, "Johnnie Walker Red", aliases=("조니워커 블랙",), is_active=False)
    bottling = make_product(db_session, signatory, "Signatory Vintage Caol Ila 10", age_years=10)

    snapshot = CatalogSnapshot(db_session)

    assert_snapshot_answers_like_the_db(snapshot, DbCatalog(db_session))
    assert snapshot.get_product(red.id) is None and snapshot.get_normalized_aliases(red.id) == []
    assert set(snapshot.meta) == {black.id, bottling.id}
    # The alias order follows the database collation (CI's PostgreSQL returns the Hangul alias first,
    # a C-collation database last), and edition_check only tests membership, so compare them as a set.
    meta = snapshot.meta[black.id]
    assert replace(meta, aliases=()) == ProductMeta("Johnnie Walker Black", 12, "Black", None)
    assert sorted(meta.aliases) == sorted(a.alias_text for a in black.aliases)
    assert len(meta.aliases) == 3
    assert snapshot.meta[bottling.id].bottler == "Signatory"


@pytest.mark.skipif(not all(path.exists() for path in SEED_FILES), reason="ai/catalog seed is not checked out")
def test_snapshot_answers_like_the_db_on_the_seed_catalog(db_session):
    catalog_json, bars_json, _ = (json.loads(path.read_text(encoding="utf-8")) for path in SEED_FILES)
    seed(db_session.connection(), catalog_json, bars_json)

    snapshot = CatalogSnapshot(db_session)

    assert_snapshot_answers_like_the_db(snapshot, DbCatalog(db_session))
    # Independent bottlings: the products of the 12 P17 bottler brands (same rule as ai/eval/match_eval.py).
    bottler_brands = {b["id"] for b in catalog_json["brands"] if b["canonical_name"] in {
        alias for aliases in IB_BOTTLERS.values() for alias in aliases}}
    expected = {p["id"] for p in catalog_json["products"] if p["brand_id"] in bottler_brands and p.get("is_active", True)}
    assert {str(pid) for pid, meta in snapshot.meta.items() if meta.bottler is not None} == expected
    assert len(expected) > 0
