# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-13, P22). Reviewed by Jinwoo Park.
from uuid import UUID

import pytest

from app.matching import ExtractedProduct, ProductInfo, resolve_product
from app.matching.memory_catalog import InMemoryCatalog
from app.matching.staged import resolve_product_staged


def _id(n: int) -> UUID:
    return UUID(int=n)


ABERLOUR, GLENFIDDICH, BUFFALO, MAKERS = (_id(100 + n) for n in range(4))
ABERLOUR_12, GLENFIDDICH_12, GLENFIDDICH_15, BUFFALO_TRACE, MAKERS_MARK = (_id(n) for n in range(1, 6))


@pytest.fixture
def catalog():
    products = [
        ProductInfo(ABERLOUR_12, "Aberlour 12", age_years=12, brand_id=ABERLOUR),
        ProductInfo(GLENFIDDICH_12, "Glenfiddich 12", age_years=12, brand_id=GLENFIDDICH),
        ProductInfo(GLENFIDDICH_15, "Glenfiddich 15", age_years=15, brand_id=GLENFIDDICH),
        ProductInfo(BUFFALO_TRACE, "Buffalo Trace", brand_id=BUFFALO),
        ProductInfo(MAKERS_MARK, "Maker's Mark", brand_id=MAKERS),
    ]
    aliases = [
        (ABERLOUR_12, "Aberlour 12"),
        (ABERLOUR_12, "아벨라워 12년"),
        (GLENFIDDICH_12, "Glenfiddich 12"),
        (GLENFIDDICH_12, "글렌피딕 12년"),
        (GLENFIDDICH_15, "Glenfiddich 15"),
        (BUFFALO_TRACE, "Buffalo Trace"),
        (MAKERS_MARK, "Maker's Mark"),
    ]
    return InMemoryCatalog(products, aliases)


def s1(name: str, catalog, **fields):
    return resolve_product_staged(ExtractedProduct(product_name=name, **fields), catalog, {"S1"})


def test_no_stages_is_resolve_product(catalog):
    for name in ("아벨라워(Aberlour) 12년", "Buffalo Trace / Maker's Mark", "Glenfiddich 12", None):
        item = ExtractedProduct(product_name=name)
        assert resolve_product_staged(item, catalog) == resolve_product(item, catalog)


def test_unknown_stage_is_rejected(catalog):
    with pytest.raises(ValueError):
        resolve_product_staged(ExtractedProduct(product_name="Aberlour 12"), catalog, {"S9"})


@pytest.mark.parametrize("name", ["아벨라워(Aberlour) 12년", "Aberlour (아벨라워) 12Y", "아벨라워 (Aberlour)12년"])
def test_parenthesized_name_is_looked_up_both_ways(catalog, name):
    assert resolve_product(ExtractedProduct(product_name=name), catalog).status == "unmatched"

    result = s1(name, catalog)

    assert result.status == "exact_match"
    assert result.proposed_product_id == ABERLOUR_12
    assert result.candidates[0].evidence["parenExpanded"] in ("아벨라워 12년", "Aberlour 12년", "Aberlour 12Y")


def test_parenthesized_name_keeps_the_age_conflict_check(catalog):
    result = s1("아벨라워(Aberlour) 12년", catalog, age_years=15)

    assert result.status == "ambiguous"
    assert result.candidates[0].evidence["ageConflict"] is True


def test_two_products_of_different_brands_are_multi(catalog):
    result = s1("Buffalo Trace / Maker's Mark", catalog)

    assert result.status == "multi"
    assert result.proposed_product_id is None
    assert [part.proposed_product_id for part in result.parts] == [BUFFALO_TRACE, MAKERS_MARK]
    assert [part.status for part in result.parts] == ["exact_match", "exact_match"]
    assert [c.product_id for c in result.candidates] == [BUFFALO_TRACE, MAKERS_MARK]
    assert result.candidates[1].evidence["multiProduct"] == "Maker's Mark"


def test_two_products_need_both_sides_exact(catalog):
    # A typo on one side: M0 behaviour (the side that matched) is kept.
    result = s1("Buffalo Trace / Makrt's Mark", catalog)

    assert result.status == "exact_match"
    assert result.proposed_product_id == BUFFALO_TRACE


def test_two_products_of_the_same_brand_are_not_multi(catalog):
    result = s1("Glenfiddich 12 / Glenfiddich 15", catalog)

    assert result.status == "ambiguous"
    assert result.parts == ()


def test_korean_english_pair_stays_one_product(catalog):
    result = s1("글렌피딕 12년 / Glenfiddich 12", catalog)

    assert result.status == "exact_match"
    assert result.proposed_product_id == GLENFIDDICH_12
    assert result.parts == ()


def test_korean_english_pair_of_different_products_is_not_multi(catalog):
    # Different scripts mean "Korean / English" of one line, never two products.
    result = s1("아벨라워 12년 / Glenfiddich 12", catalog)

    assert result.status == "ambiguous"
