# AI-generated with Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-17). Reviewed by Haeul Yang.
"""Every alias of the service catalog finds what it names (API spec, section 3.10.1).

The real catalog (`ai/catalog`) is loaded into the test database and every searchable alias is
searched. The expected results come from the catalog rows, not from the search code. A failure
lists the aliases that broke; it usually means a catalog change made two products or brands share
a name, so tell the catalog owner as well.

- A product alias finds that product (step `alias_exact`), and all such aliases of a product find
  the same products, whatever their language.
- An alias that equals a brand alias is a brand search instead: it gives the whole brand with the
  product among the exact matches listed first.
- All aliases of a brand give the same products: the brand's active products, plus any product of
  another brand whose alias is the same text.
- The spec relies on every product having a Korean and an English searchable alias.
"""

import json
from collections import defaultdict
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select

from app.models import Brand, BrandAlias, Product, ProductAlias
from app.services.search_query import resolve_search_query
from scripts.seed_catalog import seed

CATALOG_DIR = Path(__file__).resolve().parents[2] / "ai" / "catalog"
SEED_FILES = [CATALOG_DIR / name for name in ("catalog_v2_service.json", "bars_v2.json")]

pytestmark = pytest.mark.skipif(
    not all(path.exists() for path in SEED_FILES), reason="ai/catalog seed is not checked out"
)


@pytest.fixture
def catalog(db_session):
    catalog_json, bars_json = (json.loads(path.read_text(encoding="utf-8")) for path in SEED_FILES)
    seed(db_session.connection(), catalog_json, bars_json)
    return db_session


def searchable_product_aliases(session) -> dict[UUID, list[ProductAlias]]:
    rows = session.scalars(
        select(ProductAlias).join(Product).where(Product.is_active, ProductAlias.is_searchable)
    ).all()
    by_product: dict[UUID, list[ProductAlias]] = defaultdict(list)
    for alias in rows:
        by_product[alias.product_id].append(alias)
    return by_product


def products_by_alias(session) -> dict[str, set[UUID]]:
    """Normalized alias -> active products that have it as a searchable alias."""
    found: dict[str, set[UUID]] = defaultdict(set)
    for product_id, aliases in searchable_product_aliases(session).items():
        for alias in aliases:
            found[alias.normalized_alias].add(product_id)
    return found


def brand_alias_keys(session) -> set[str]:
    return set(session.scalars(select(BrandAlias.normalized_alias)))


def found_ids(session, text: str):
    resolution = resolve_search_query(session, text)
    return resolution, {product.id for product in resolution.products}


def test_every_product_alias_finds_its_product(catalog):
    brand_keys = brand_alias_keys(catalog)
    failures = []
    checked = 0

    for product_id, aliases in searchable_product_aliases(catalog).items():
        results = set()
        for alias in aliases:
            resolution, ids = found_ids(catalog, alias.alias_text)
            checked += 1
            if alias.normalized_alias in brand_keys:
                # A brand search: the whole brand, with this product among the exact matches first.
                if resolution.match_type != "brand" or product_id not in resolution.exact_product_ids:
                    failures.append((alias.alias_text, "brand search without the product first"))
                elif resolution.products[0].id not in resolution.exact_product_ids:
                    failures.append((alias.alias_text, "exact matches are not listed first"))
                continue
            if resolution.match_type != "alias_exact" or product_id not in ids:
                failures.append((alias.alias_text, f"{resolution.match_type}, product not found"))
            results.add(frozenset(ids))
        if len(results) > 1:
            failures.append((str(product_id), f"aliases find {len(results)} different product sets"))

    assert failures == []
    assert checked > 2000  # the whole service catalog was searched


def test_every_brand_alias_gives_the_same_brand_result(catalog):
    by_alias = products_by_alias(catalog)
    active_by_brand: dict[UUID, set[UUID]] = defaultdict(set)
    for product in catalog.scalars(select(Product).where(Product.is_active)):
        active_by_brand[product.brand_id].add(product.id)
    failures = []
    checked = 0

    for brand in catalog.scalars(select(Brand)):
        if not active_by_brand[brand.id]:
            continue  # nothing to show: the search moves on to product aliases
        results = set()
        for alias in catalog.scalars(select(BrandAlias).where(BrandAlias.brand_id == brand.id)):
            resolution, ids = found_ids(catalog, alias.alias_text)
            checked += 1
            expected = active_by_brand[brand.id] | by_alias.get(alias.normalized_alias, set())
            if resolution.match_type != "brand" or ids != expected:
                failures.append((alias.alias_text, resolution.match_type, len(ids), len(expected)))
            results.add(frozenset(ids))
        if len(results) > 1:
            failures.append((brand.canonical_name, f"aliases give {len(results)} different product sets"))

    assert failures == []
    assert checked > 400


def test_every_product_has_korean_and_english_search_names(catalog):
    missing = []
    for product_id, aliases in searchable_product_aliases(catalog).items():
        languages = {alias.language_code for alias in aliases}
        if not {"ko", "en"} <= languages:
            missing.append((str(product_id), sorted(language or "?" for language in languages)))

    assert missing == []
