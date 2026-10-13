# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-05, PR #5; 2026-10-13, P22). Reviewed by Jinwoo Park.
import json
from pathlib import Path
from uuid import UUID

import pytest

from app.matching import ProductInfo
from app.matching.memory_catalog import InMemoryCatalog

SEED_PATH = Path(__file__).resolve().parents[2] / "ai" / "catalog" / "catalog_v1_draft.json"


def test_aliases_are_normalized_and_deduplicated_per_product():
    product_id = UUID("00000000-0000-0000-0000-000000000001")
    catalog = InMemoryCatalog(
        [ProductInfo(product_id, "GlenDronach 12", age_years=12)],
        [(product_id, "글렌드로낙 12년"), (product_id, "글렌드로낙 12Y"), (product_id, "GlenDronach 12")],
    )

    assert catalog.get_normalized_aliases(product_id) == ["글렌드로낙12", "glendronach12"]
    assert catalog.find_product_ids_by_alias("글렌드로낙12") == [product_id]
    assert catalog.find_product_ids_by_alias("글렌드로낙 12년") == []


def test_alias_for_unknown_product_is_rejected():
    with pytest.raises(ValueError):
        InMemoryCatalog([], [(UUID(int=1), "x")])


@pytest.mark.skipif(not SEED_PATH.exists(), reason="ai/catalog seed is not checked out")
def test_seed_has_no_alias_shared_across_products():
    catalog = InMemoryCatalog.from_seed(SEED_PATH)

    assert catalog.shared_aliases() == {}


def test_from_seed_skips_inactive_products_and_excluded_sources(tmp_path):
    seed = {
        "products": [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "display_name": "Monkey Shoulder",
                "aliases": [
                    {"alias_text": "Monkey Shoulder", "sources": ["standard"]},
                    {"alias_text": "몽키숄더", "sources": ["menu:서로상"]},
                    {"alias_text": "몽키 숄더", "sources": ["menu:서로상", "template"]},
                ],
            },
            {
                "id": "00000000-0000-0000-0000-000000000002",
                "display_name": "Retired",
                "is_active": False,
                "aliases": [{"alias_text": "Retired", "sources": ["standard"]}],
            },
        ]
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")

    catalog = InMemoryCatalog.from_seed(path, exclude_sources={"menu:서로상"})

    product_id = UUID("00000000-0000-0000-0000-000000000001")
    # "몽키 숄더" is kept because one of its sources is not excluded; it normalizes to "몽키숄더".
    assert catalog.get_normalized_aliases(product_id) == ["monkeyshoulder", "몽키숄더"]
    assert catalog.get_product(UUID("00000000-0000-0000-0000-000000000002")) is None
    assert catalog.find_product_ids_by_alias("retired") == []


def test_brand_lookup():
    brand, other = UUID(int=100), UUID(int=101)
    first, second, unbranded = UUID(int=1), UUID(int=2), UUID(int=3)
    catalog = InMemoryCatalog(
        [
            ProductInfo(first, "Macallan 12", brand_id=brand),
            ProductInfo(second, "Macallan 15", brand_id=brand),
            ProductInfo(unbranded, "Unbranded"),
        ],
        [],
        [(brand, "The Macallan"), (brand, "맥캘란"), (other, "Other")],
    )

    assert catalog.find_brand_ids_by_alias("themacallan") == [brand]
    assert catalog.find_brand_ids_by_alias("맥캘란") == [brand]
    assert catalog.find_brand_ids_by_alias("macallan") == []
    assert catalog.get_brand_product_ids(brand) == [first, second]
    assert catalog.get_brand_product_ids(other) == []


@pytest.mark.skipif(not SEED_PATH.exists(), reason="ai/catalog seed is not checked out")
def test_from_seed_loads_brands():
    catalog = InMemoryCatalog.from_seed(SEED_PATH)

    [macallan] = catalog.find_brand_ids_by_alias("맥캘란")
    assert catalog.find_brand_ids_by_alias("themacallan") == [macallan]
    products = [catalog.get_product(pid) for pid in catalog.get_brand_product_ids(macallan)]
    assert {p.display_name for p in products} >= {"The Macallan 12 Double Cask", "The Macallan 15 Double Cask"}
    assert all(p.brand_id == macallan for p in products)
